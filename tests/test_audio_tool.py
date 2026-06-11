import io
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import audio_tool


class AudioToolTests(unittest.TestCase):
    def test_youtube_command_downloads_then_analyzes_audio(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        downloaded = Path("song.mp3")

        with (
            patch.object(audio_tool, "download_youtube_audio", return_value=downloaded) as download,
            patch.object(audio_tool, "analyze_audio_file", return_value=(136, "Fmin")) as analyze,
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
        analyze.assert_called_once_with(downloaded)
        self.assertEqual(stdout.getvalue(), "Audio: song.mp3\nBPM: 136\nKey: Fmin\n")
        self.assertEqual(stderr.getvalue(), "")

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

    def test_analyze_audio_file_accepts_array_like_tempo(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "song.mp3"
            audio_path.touch()

            fake_librosa = types.SimpleNamespace(
                load=lambda path, mono: ("samples", 44100),
                beat=types.SimpleNamespace(beat_track=lambda y, sr: ([135.7], "beats")),
                feature=types.SimpleNamespace(
                    chroma_cqt=lambda y, sr: types.SimpleNamespace(
                        sum=lambda axis: types.SimpleNamespace(tolist=lambda: [1] * 12)
                    )
                ),
            )

            with (
                patch.dict(sys.modules, {"librosa": fake_librosa}),
                patch.object(audio_tool, "detect_key_from_chroma_sums", return_value="Fmin"),
            ):
                bpm, key = audio_tool.analyze_audio_file(audio_path)

        self.assertEqual(bpm, 135.7)
        self.assertEqual(key, "Fmin")


if __name__ == "__main__":
    unittest.main()
