---
name: beat-it
description: Use when an agent needs to download audio from a YouTube URL as MP3 or WAV, or analyze an MP3/audio file for tempo/BPM and musical key such as Cmaj, Amin, F#maj, or Bbmin.
---

# Audio Key BPM

## Overview

Use `scripts/audio_tool.py` for repeatable audio extraction and music analysis. The script uses `libraz/bpm-detector` for core BPM/key detection. Local verification showed smart-parallel comprehensive analysis taking longer than 10 seconds on the attached test file, so the default command reports core analysis only; full metadata is opt-in. This skill follows the Agent Skills layout used by Anthropic Claude Code and OpenAI Codex: root `SKILL.md`, optional `scripts/`, and optional product metadata under `agents/`.

When the skill is installed into an agent skills directory, the active user workspace may not be a Git checkout. That is fine: read this `SKILL.md` from the installed skill path and run the bundled script directly.

## Quick Start

Analyze an existing MP3 or other librosa-readable audio file:

```bash
python3 scripts/audio_tool.py analyze /path/to/song.mp3
```

Download a YouTube URL as MP3 and analyze it:

```bash
python3 scripts/audio_tool.py youtube "https://www.youtube.com/watch?v=..." --format mp3
```

Download as WAV instead:

```bash
python3 scripts/audio_tool.py youtube "https://www.youtube.com/watch?v=..." --format wav
```

Request full metadata explicitly:

```bash
python3 scripts/audio_tool.py --full analyze /path/to/song.mp3
```

## Dependencies

Install Python dependencies in a local virtual environment for the current task, not into the system Python:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install "git+https://github.com/libraz/bpm-detector.git" yt-dlp
```

YouTube extraction also requires `ffmpeg` on `PATH` because `yt-dlp -x --audio-format` uses it for conversion.

## Output

The command always prints core information:

```text
BPM: 128
Key: Cmaj
Duration: 180.0s
Analysis took: 1.23s
Would you like full metadata or a specific metric?
```

By default the script reports only core BPM/key/duration, then asks whether the user wants full metadata or a specific metric. Use `--full` to request comprehensive smart-parallel analysis and wait for it to complete. When full analysis completes, the script writes `metadata.json` with full `bpm-detector` output.

For YouTube input without `--output-dir`, the downloaded audio is saved inside a new folder under `~/Downloads`; explicit comprehensive metadata is written to the same folder after it completes. The YouTube command prints the saved audio path first, then the same analysis:

```text
Audio: /Users/me/Downloads/beat-it-youtube-audio-20260612-120000/example.mp3
BPM: 128
Key: Cmaj
Duration: 180.0s
```

With `--full`, full analysis also reports metadata:

```text
Analysis took: 45.25s
Metadata: /Users/me/Downloads/beat-it-youtube-audio-20260612-120000/metadata.json
```

## Notes

- Use `mp3` or `wav` only for `--format`.
- YouTube playlist URLs are treated as single-video downloads; the script strips `list=` and also passes `--no-playlist`.
- Treat BPM/key output as algorithmic estimates, not authoritative musicological annotation.
- If dependencies are missing, install them rather than reimplementing YouTube download or audio feature extraction.
- Use `--full` to request full metadata and wait for it to complete.
