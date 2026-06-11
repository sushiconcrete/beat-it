#!/usr/bin/env python3
import argparse
import math
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


PITCH_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


def rotate(values, steps):
    return values[-steps:] + values[:-steps]


def cosine_similarity(left, right):
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0
    return numerator / (left_norm * right_norm)


def detect_key_from_chroma_sums(chroma_sums):
    scores = (
        (cosine_similarity(chroma_sums, rotate(profile, index)), f"{pitch}{mode}")
        for index, pitch in enumerate(PITCH_NAMES)
        for profile, mode in ((MAJOR_PROFILE, "maj"), (MINOR_PROFILE, "min"))
    )
    return max(scores, key=lambda item: item[0])[1]


def format_analysis(bpm, key):
    return f"BPM: {round(float(bpm))}\nKey: {key}"


def single_video_url(url):
    parsed = urlparse(url)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "list"]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def analyze_audio_file(path):
    try:
        import librosa
    except ImportError as exc:
        raise RuntimeError("Install librosa and numpy to analyze BPM/key: python3 -m pip install librosa numpy") from exc

    audio_path = Path(path)
    if not audio_path.exists():
        raise FileNotFoundError(audio_path)

    y, sr = librosa.load(audio_path, mono=True)
    tempo, _beats = librosa.beat.beat_track(y=y, sr=sr)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    key = detect_key_from_chroma_sums(chroma.sum(axis=1).tolist())
    return float(tempo), key


def download_youtube_audio(url, audio_format, output_dir):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    command = [
        "yt-dlp",
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


def build_parser():
    parser = argparse.ArgumentParser(description="Download YouTube audio and detect BPM/key.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="Analyze BPM and key for a local audio file.")
    analyze.add_argument("file", type=Path)

    youtube = subparsers.add_parser("youtube", help="Download YouTube audio, then analyze BPM and key.")
    youtube.add_argument("url")
    youtube.add_argument("--format", choices=["mp3", "wav"], default="mp3")
    youtube.add_argument("--output-dir", type=Path, default=Path.cwd())

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        audio_path = args.file
        if args.command == "youtube":
            audio_path = download_youtube_audio(args.url, args.format, args.output_dir)
            print(f"Audio: {audio_path}")
        bpm, key = analyze_audio_file(audio_path)
        print(format_analysis(bpm, key))
        return 0
    except (FileNotFoundError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
