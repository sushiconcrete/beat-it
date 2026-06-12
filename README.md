# Beat It

A tiny Agent Skill for pulling music from a YouTube link and estimating BPM/key with `libraz/bpm-detector`.

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
- Analyze a local audio file for BPM, key, and duration.
- Try smart-parallel comprehensive analysis for up to 10 seconds.
- Write full `metadata.json` only when comprehensive analysis finishes within the threshold.
- Print compact core output directly in chat-friendly text.

## Use It

Install from GitHub as a root-level Agent Skill. The repo itself is the skill directory: `SKILL.md` lives at the root, with `scripts/` beside it.

Set up task-local dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install "git+https://github.com/libraz/bpm-detector.git" yt-dlp
```

Make sure `ffmpeg` is on your `PATH`, then run from the skill directory:

```bash
python3 scripts/audio_tool.py youtube "https://www.youtube.com/watch?v=..." --format mp3
python3 scripts/audio_tool.py analyze ./audio/song.mp3
python3 scripts/audio_tool.py --core-only analyze ./audio/song.mp3
```

YouTube links with playlist parameters stay focused on the single requested video. When no `--output-dir` is provided, YouTube downloads go into a new `beat-it-...` folder under `~/Downloads`; if comprehensive analysis is fast enough, `metadata.json` is written into that same folder.

Default comprehensive analysis is bounded by `--full-threshold-seconds 10`. If that run takes longer, the tool reports only core BPM/key/duration and prints that metadata was skipped so full analysis can be requested explicitly.

The agent-facing instructions live in `SKILL.md`. The README is just the human-friendly stage door.
