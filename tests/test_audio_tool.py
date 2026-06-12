import io
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import audio_tool


class AudioToolTests(unittest.TestCase):
    def test_default_analysis_uses_core_only_after_slow_local_benchmark(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "Ophelia.mp3"
            audio_path.touch()
            downloads_dir = Path(temp_dir) / "Downloads"
            ticks = iter([4.0, 4.42])

            basic_analyzer = types.SimpleNamespace(
                analyze_file=lambda path, detect_key, comprehensive: {
                    "basic_info": {"bpm": 175.0, "key": "Bb Major", "duration": 15.0}
                }
            )

            outcome = audio_tool.analyze_audio_file(
                audio_path,
                downloads_dir=downloads_dir,
                basic_analyzer=basic_analyzer,
                clock=lambda: next(ticks),
            )

            self.assertEqual(outcome.analysis_level, "core")
            self.assertEqual(outcome.bpm, 175.0)
            self.assertEqual(outcome.analysis_seconds, 0.42)
            self.assertIsNone(outcome.metadata_path)
            self.assertFalse(downloads_dir.exists())

    def test_explicit_full_analysis_writes_metadata_json_under_downloads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "Ophelia.mp3"
            audio_path.touch()
            downloads_dir = Path(temp_dir) / "Downloads"
            ticks = iter([10.0, 18.5])

            class ScalarLike:
                def item(self):
                    return 0.875

            class ArrayLike:
                def tolist(self):
                    return [0.1, 0.2]

            basic_analyzer = types.SimpleNamespace(
                analyze_file=lambda path, detect_key, comprehensive: {
                    "basic_info": {"bpm": 175.2, "key": "Bb Major", "duration": 15.0}
                }
            )
            parallel_analyzer = types.SimpleNamespace(
                analyze_file=lambda path, comprehensive, detailed_progress: {
                    "basic_info": {"bpm": 175.2, "key": "Bb Major", "duration": 15.0},
                    "rhythm": {"time_signature": "4/4", "groove_type": "straight", "confidence": ScalarLike()},
                    "energy_profile": ArrayLike(),
                }
            )

            outcome = audio_tool.analyze_audio_file(
                audio_path,
                downloads_dir=downloads_dir,
                full_analysis=True,
                basic_analyzer=basic_analyzer,
                parallel_analyzer=parallel_analyzer,
                clock=lambda: next(ticks),
            )

            self.assertEqual(outcome.analysis_level, "full")
            self.assertEqual(outcome.bpm, 175.2)
            self.assertEqual(outcome.key, "Bb Major")
            self.assertIsNotNone(outcome.metadata_path)
            self.assertEqual(outcome.metadata_path.name, "metadata.json")
            self.assertEqual(outcome.metadata_path.parent.parent, downloads_dir)

            metadata = json.loads(outcome.metadata_path.read_text())
            self.assertEqual(metadata["basic_info"]["bpm"], 175.2)
            self.assertEqual(metadata["basic_info"]["key"], "Bb Major")
            self.assertEqual(metadata["analysis_seconds"], 8.5)
            self.assertEqual(metadata["analysis_level"], "full")
            self.assertEqual(metadata["full_analysis"]["rhythm"]["time_signature"], "4/4")
            self.assertEqual(metadata["full_analysis"]["rhythm"]["confidence"], 0.875)
            self.assertEqual(metadata["full_analysis"]["energy_profile"], [0.1, 0.2])

    def test_real_attached_file_detects_core_bpm_and_key(self):
        attached_audio = Path('/Users/delphia/Downloads/"Ophelia" Bb Maj 175.mp3')
        if not attached_audio.exists():
            self.skipTest(f"Attached audio file not found: {attached_audio}")
        try:
            audio_tool.load_bpm_detector_analyzers(include_parallel=False)
        except RuntimeError as exc:
            self.skipTest(str(exc))

        outcome = audio_tool.analyze_audio_file(attached_audio)

        self.assertGreater(outcome.bpm, 0)
        self.assertLess(outcome.bpm, 300)
        self.assertTrue(outcome.key)
        self.assertEqual(outcome.analysis_level, "core")
        self.assertIsNone(outcome.metadata_path)

    def test_core_only_analysis_does_not_create_parallel_analyzer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "song.mp3"
            audio_path.touch()

            class FakeAudioAnalyzer:
                def analyze_file(self, path, detect_key, comprehensive):
                    return {"basic_info": {"bpm": 120.0, "key": "C Major", "duration": 5.0}}

            class ExplodingParallelAnalyzer:
                def __init__(self, auto_parallel):
                    raise AssertionError("parallel analyzer should not be created for core-only analysis")

            fake_module = types.SimpleNamespace(
                AudioAnalyzer=FakeAudioAnalyzer,
                SmartParallelAudioAnalyzer=ExplodingParallelAnalyzer,
            )

            with patch.dict(sys.modules, {"bpm_detector": fake_module}):
                outcome = audio_tool.analyze_audio_file(audio_path)

        self.assertEqual(outcome.analysis_level, "core")
        self.assertEqual(outcome.bpm, 120.0)

    def test_youtube_command_downloads_then_analyzes_audio(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        downloaded = Path("song.mp3")
        outcome = types.SimpleNamespace(
            audio_path=downloaded,
            bpm=136,
            key="Fmin",
            duration_seconds=120.0,
            analysis_level="core",
            analysis_seconds=0.25,
            metadata_path=None,
        )

        with (
            patch.object(audio_tool, "download_youtube_audio", return_value=downloaded) as download,
            patch.object(audio_tool, "analyze_audio_file", return_value=outcome) as analyze,
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = audio_tool.main(
                [
                    "youtube",
                    "https://www.youtube.com/watch?v=ALynBhLO3Uk&list=playlist",
                    "--output-dir",
                    "audio",
                ]
            )

        self.assertEqual(exit_code, 0)
        download.assert_called_once_with(
            "https://www.youtube.com/watch?v=ALynBhLO3Uk&list=playlist",
            "mp3",
            Path("audio"),
        )
        analyze.assert_called_once_with(
            downloaded,
            metadata_dir=Path("audio"),
            full_analysis=False,
        )
        self.assertEqual(
            stdout.getvalue(),
            "Audio: song.mp3\nBPM: 136\nKey: Fmin\nDuration: 120.0s\n"
            "Analysis took: 0.25s\n"
            "Would you like full metadata or a specific metric?\n",
        )
        self.assertEqual(stderr.getvalue(), "")

    def test_full_youtube_command_requests_full_analysis(self):
        stdout = io.StringIO()
        downloaded = Path("song.mp3")
        outcome = types.SimpleNamespace(
            audio_path=downloaded,
            bpm=136,
            key="Fmin",
            duration_seconds=120.0,
            analysis_level="full",
            analysis_seconds=45.25,
            metadata_path=Path("audio/metadata.json"),
        )

        with (
            patch.object(audio_tool, "download_youtube_audio", return_value=downloaded),
            patch.object(audio_tool, "analyze_audio_file", return_value=outcome) as analyze,
            redirect_stdout(stdout),
        ):
            exit_code = audio_tool.main(
                [
                    "--full",
                    "youtube",
                    "https://www.youtube.com/watch?v=ALynBhLO3Uk",
                    "--output-dir",
                    "audio",
                ]
            )

        self.assertEqual(exit_code, 0)
        analyze.assert_called_once_with(downloaded, metadata_dir=Path("audio"), full_analysis=True)
        self.assertIn("Metadata: audio/metadata.json", stdout.getvalue())

    def test_download_uses_yt_dlp_from_current_python_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bin_dir = Path(temp_dir) / "bin"
            bin_dir.mkdir()
            yt_dlp = bin_dir / "yt-dlp"
            yt_dlp.touch()
            python = bin_dir / "python"
            output_dir = Path(temp_dir) / "audio"

            completed = types.SimpleNamespace(stdout="/tmp/song.mp3\n")

            with (
                patch.object(sys, "executable", str(python)),
                patch.object(audio_tool.subprocess, "run", return_value=completed) as run,
            ):
                path = audio_tool.download_youtube_audio(
                    "https://www.youtube.com/watch?v=ALynBhLO3Uk&list=playlist",
                    "mp3",
                    output_dir,
                )

        command = run.call_args.args[0]
        self.assertEqual(path, Path("/tmp/song.mp3"))
        self.assertEqual(command[0], str(yt_dlp))
        self.assertIn("--no-playlist", command)
        self.assertEqual(command[-1], "https://www.youtube.com/watch?v=ALynBhLO3Uk")

    def test_load_bpm_detector_analyzers_reports_missing_dependency(self):
        with patch.dict(sys.modules, {"bpm_detector": None}):
            with self.assertRaisesRegex(RuntimeError, "bpm-detector"):
                audio_tool.load_bpm_detector_analyzers()


if __name__ == "__main__":
    unittest.main()
