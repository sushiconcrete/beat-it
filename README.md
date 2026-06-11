# Beat It

A tiny Agent Skill for pulling music from a YouTube link and estimating the beat and key.

`beat-it` follows the portable skill layout used by Anthropic Claude Code and OpenAI Codex:

```text
beat-it/
├── SKILL.md
├── scripts/
│   └── audio_tool.py
└── agents/
    └── openai.yaml
```

## What It Does

- Download YouTube audio as `mp3` or `wav`.
- Analyze a local audio file for BPM and key.
- Print compact output like `BPM: 128` and `Key: Cmaj`.

## Use It

Install from GitHub as a root-level Agent Skill. The repo itself is the skill directory: `SKILL.md` lives at the root, with `scripts/` beside it.

Set up task-local dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install librosa numpy yt-dlp
```

Make sure `ffmpeg` is on your `PATH`, then run from the skill directory:

```bash
python3 scripts/audio_tool.py youtube "https://www.youtube.com/watch?v=..." --format mp3 --output-dir ./audio
python3 scripts/audio_tool.py analyze ./audio/song.mp3
```

YouTube links with playlist parameters stay focused on the single requested video.

The agent-facing instructions live in `SKILL.md`. The README is just the human-friendly stage door.
