#!/usr/bin/env python3
import argparse
import json
import multiprocessing
import os
import re
import shutil
import subprocess
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


DEFAULT_FULL_THRESHOLD_SECONDS = 10.0


@dataclass
class AnalysisOutcome:
    audio_path: Path
    bpm: float
    key: str
    duration_seconds: float | None
    analysis_level: str
    parallel_analysis_seconds: float | None
    parallel_analysis_timed_out: bool
    metadata_path: Path | None


def single_video_url(url):
    parsed = urlparse(url)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "list"]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def yt_dlp_executable():
    venv_executable = Path(sys.executable).with_name("yt-dlp")
    if venv_executable.exists():
        return str(venv_executable)
    return shutil.which("yt-dlp") or "yt-dlp"


def download_youtube_audio(url, audio_format, output_dir):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    command = [
        yt_dlp_executable(),
        "-x",
        "--audio-format",
        audio_format,
        "--paths",
        str(output_path),
        "-o",
        "%(title)s.%(ext)s",
        "--print",
        "after_move:filepath",
        "--no-playlist",
        single_video_url(url),
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    paths = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not paths:
        raise RuntimeError("yt-dlp did not report an output file")
    return Path(paths[-1])


def default_downloads_dir():
    return Path.home() / "Downloads"


def analysis_output_dir(downloads_dir, audio_path):
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(audio_path).stem).strip("-") or "audio"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path(downloads_dir) / f"beat-it-{slug}-{stamp}"


def load_bpm_detector_analyzers(*, include_parallel=True):
    try:
        from bpm_detector import AudioAnalyzer, SmartParallelAudioAnalyzer
    except ImportError as exc:
        raise RuntimeError(
            "Install bpm-detector from libraz/bpm-detector to analyze audio: "
            "python3 -m pip install git+https://github.com/libraz/bpm-detector.git yt-dlp"
        ) from exc

    parallel = SmartParallelAudioAnalyzer(auto_parallel=True) if include_parallel else None
    return AudioAnalyzer(), parallel


def _basic_info(results):
    if not isinstance(results, dict) or "basic_info" not in results:
        raise RuntimeError("bpm-detector returned an unexpected analysis result")
    info = results["basic_info"]
    return {
        "bpm": float(info["bpm"]),
        "key": str(info.get("key") or "Unknown"),
        "duration": _optional_float(info.get("duration")),
    }


def _optional_float(value):
    if value is None:
        return None
    return float(value)


def _rounded_seconds(seconds):
    return round(float(seconds), 2)


def _json_ready(value):
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "tolist"):
        return _json_ready(value.tolist())
    if hasattr(value, "item"):
        try:
            return _json_ready(value.item())
        except ValueError:
            pass
    return value


def write_metadata(output_dir, audio_path, basic_info, full_analysis, parallel_seconds):
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = output_dir / "metadata.json"
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_audio": str(Path(audio_path).expanduser()),
        "analysis_level": "full",
        "parallel_analysis_seconds": _rounded_seconds(parallel_seconds),
        "basic_info": _json_ready(basic_info),
        "full_analysis": _json_ready(full_analysis),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return metadata_path


def _parallel_analysis_worker(audio_path, queue):
    try:
        with open(os.devnull, "w") as devnull, redirect_stdout(devnull), redirect_stderr(devnull):
            _basic_analyzer, parallel_analyzer = load_bpm_detector_analyzers(include_parallel=True)
            results = parallel_analyzer.analyze_file(str(audio_path), comprehensive=True, detailed_progress=False)
        queue.put({"ok": True, "results": results})
    except BaseException as exc:
        queue.put({"ok": False, "error": str(exc)})


def run_parallel_analysis_with_timeout(audio_path, threshold_seconds, clock=time.perf_counter):
    start = clock()
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    process = context.Process(target=_parallel_analysis_worker, args=(str(audio_path), queue))
    process.start()
    process.join(threshold_seconds)
    parallel_seconds = _rounded_seconds(clock() - start)

    if process.is_alive():
        process.terminate()
        process.join()
        return None, parallel_seconds, True

    if queue.empty():
        raise RuntimeError("bpm-detector did not return a parallel analysis result")

    payload = queue.get()
    if not payload["ok"]:
        raise RuntimeError(f"bpm-detector parallel analysis failed: {payload['error']}")
    return payload["results"], parallel_seconds, False


def run_parallel_analysis_synchronously(audio_path, threshold_seconds, clock, parallel_analyzer):
    del threshold_seconds
    start = clock()
    results = parallel_analyzer.analyze_file(str(audio_path), comprehensive=True, detailed_progress=False)
    return results, _rounded_seconds(clock() - start), False


def analyze_audio_file(
    path,
    *,
    downloads_dir=None,
    metadata_dir=None,
    full_threshold_seconds=DEFAULT_FULL_THRESHOLD_SECONDS,
    basic_analyzer=None,
    parallel_analyzer=None,
    parallel_runner=None,
    clock=time.perf_counter,
):
    audio_path = Path(path)
    if not audio_path.exists():
        raise FileNotFoundError(audio_path)

    needs_parallel = full_threshold_seconds >= 0
    if basic_analyzer is None:
        basic_analyzer, _parallel_analyzer = load_bpm_detector_analyzers(include_parallel=False)

    basic_results = basic_analyzer.analyze_file(str(audio_path), detect_key=True, comprehensive=False)
    info = _basic_info(basic_results)

    if full_threshold_seconds < 0:
        return AnalysisOutcome(
            audio_path=audio_path,
            bpm=info["bpm"],
            key=info["key"],
            duration_seconds=info["duration"],
            analysis_level="core",
            parallel_analysis_seconds=None,
            parallel_analysis_timed_out=False,
            metadata_path=None,
        )

    if parallel_runner is None:
        if parallel_analyzer is None:
            parallel_runner = run_parallel_analysis_with_timeout
        else:
            parallel_runner = lambda audio_path, threshold_seconds, clock: run_parallel_analysis_synchronously(
                audio_path, threshold_seconds, clock, parallel_analyzer
            )
    full_results, parallel_seconds, timed_out = parallel_runner(audio_path, full_threshold_seconds, clock)

    if timed_out or parallel_seconds > full_threshold_seconds:
        return AnalysisOutcome(
            audio_path=audio_path,
            bpm=info["bpm"],
            key=info["key"],
            duration_seconds=info["duration"],
            analysis_level="core",
            parallel_analysis_seconds=parallel_seconds,
            parallel_analysis_timed_out=timed_out,
            metadata_path=None,
        )

    output_dir = Path(metadata_dir) if metadata_dir is not None else analysis_output_dir(
        downloads_dir or default_downloads_dir(), audio_path
    )
    metadata_path = write_metadata(
        output_dir,
        audio_path,
        info,
        full_results,
        parallel_seconds,
    )
    return AnalysisOutcome(
        audio_path=audio_path,
        bpm=info["bpm"],
        key=info["key"],
        duration_seconds=info["duration"],
        analysis_level="full",
        parallel_analysis_seconds=parallel_seconds,
        parallel_analysis_timed_out=False,
        metadata_path=metadata_path,
    )


def format_analysis(outcome):
    lines = [
        f"BPM: {round(float(outcome.bpm))}",
        f"Key: {outcome.key}",
    ]
    if outcome.duration_seconds is not None:
        lines.append(f"Duration: {outcome.duration_seconds:.1f}s")
    if outcome.parallel_analysis_seconds is not None:
        lines.append(f"Parallel analysis: {outcome.parallel_analysis_seconds:.2f}s")
    if outcome.metadata_path is not None:
        lines.append(f"Metadata: {outcome.metadata_path}")
    elif outcome.analysis_level == "core" and outcome.parallel_analysis_seconds is not None:
        lines.append("Metadata: skipped; request full analysis if needed")
    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(description="Download YouTube audio and analyze it with libraz/bpm-detector.")
    parser.add_argument(
        "--full-threshold-seconds",
        type=float,
        default=DEFAULT_FULL_THRESHOLD_SECONDS,
        help="Write full metadata only when smart-parallel comprehensive analysis finishes within this many seconds.",
    )
    parser.add_argument(
        "--core-only",
        action="store_true",
        help="Skip comprehensive analysis and report only BPM/key/duration.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="Analyze a local audio file.")
    analyze.add_argument("file", type=Path)

    youtube = subparsers.add_parser("youtube", help="Download YouTube audio, then analyze it.")
    youtube.add_argument("url")
    youtube.add_argument("--format", choices=["mp3", "wav"], default="mp3")
    youtube.add_argument("--output-dir", type=Path, default=None)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    full_threshold_seconds = -1.0 if args.core_only else args.full_threshold_seconds

    try:
        if args.command == "youtube":
            output_dir = args.output_dir or analysis_output_dir(default_downloads_dir(), "youtube-audio")
            audio_path = download_youtube_audio(args.url, args.format, output_dir)
            print(f"Audio: {audio_path}")
        else:
            audio_path = args.file

        metadata_dir = output_dir if args.command == "youtube" else None
        outcome = analyze_audio_file(
            audio_path,
            metadata_dir=metadata_dir,
            full_threshold_seconds=full_threshold_seconds,
        )
        print(format_analysis(outcome))
        return 0
    except (FileNotFoundError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
