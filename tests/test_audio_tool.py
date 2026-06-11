import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "audio-key-bpm" / "scripts" / "audio_tool.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("audio_tool", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AudioToolTests(unittest.TestCase):
    def test_detects_c_major_from_pitch_class_energy(self):
        tool = load_tool()

        key = tool.detect_key_from_chroma_sums([8, 0, 1, 0, 7, 1, 0, 5, 0, 1, 0, 0])

        self.assertEqual(key, "Cmaj")

    def test_formats_bpm_and_key_for_terminal_output(self):
        tool = load_tool()

        output = tool.format_analysis(127.6, "Cmaj")

        self.assertEqual(output, "BPM: 128\nKey: Cmaj")

    def test_download_youtube_audio_uses_requested_format_and_returns_file(self):
        tool = load_tool()

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            completed = SimpleNamespace(stdout=str(output_dir / "song.mp3") + "\n")

            with mock.patch.object(tool.subprocess, "run", return_value=completed) as run:
                path = tool.download_youtube_audio(
                    "https://www.youtube.com/watch?v=abc123",
                    "mp3",
                    output_dir,
                )

        self.assertEqual(path, output_dir / "song.mp3")
        command = run.call_args.args[0]
        self.assertIn("--audio-format", command)
        self.assertEqual(command[command.index("--audio-format") + 1], "mp3")
        self.assertIn("https://www.youtube.com/watch?v=abc123", command)

    def test_analyze_command_prints_bpm_and_key(self):
        with tempfile.TemporaryDirectory() as directory:
            audio_file = Path(directory) / "song.mp3"
            audio_file.write_bytes(b"fake mp3")

            tool = load_tool()
            with mock.patch.object(tool, "analyze_audio_file", return_value=(120.2, "Cmaj")):
                with mock.patch("builtins.print") as print_:
                    result = tool.main(["analyze", str(audio_file)])

        self.assertEqual(result, 0)
        print_.assert_called_once_with("BPM: 120\nKey: Cmaj")

    def test_cli_rejects_unsupported_youtube_format(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "youtube",
                    "https://www.youtube.com/watch?v=abc123",
                    "--format",
                    "flac",
                    "--output-dir",
                    directory,
                ],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid choice", result.stderr)


if __name__ == "__main__":
    unittest.main()
