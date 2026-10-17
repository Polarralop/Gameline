# Gameline

A lightweight menu bar app that tracks your deadlines, notices when you launch a PC game, and reminds you only when you're actually behind. Built at Hack the Valley 11.

## Run

```bash
./run.sh                 # desktop app: window + menu bar icon
./run.sh --detect        # just print detected games every 5s
.venv/bin/python -m pytest -q
```

Pick how estimates are made in Preferences → AI estimates (or set `GAMELINE_LLM`):

- `gemini`: Gemini API (gemini-3.8-flash), needs `GEMINI_API_KEY=...` in `.env`
- `claude`: Claude API, needs `ANTHROPIC_API_KEY=...` in `.env`
- `claude-cli`: your Claude subscription through the local Claude Code CLI; log in from Preferences. Personal use only.
- `stub`: offline rough guesses

## Gameline.app

```bash
./build_app.sh --alias   # quick: the .app runs this source folder; restart it to pick up code changes
./build_app.sh           # standalone build, installed to /Applications (about a minute, ~300 MB)
open -a Gameline
```

Both builds and `./run.sh` share one data folder, `~/Library/Application Support/Gameline`
(`state.json`, `.env`, the demo game). Run only one of them at a time, or you'll get every
notification twice. The first time the app sends a notification, macOS asks to allow
"Gameline"; for Gaming Focus, add Gameline under Allowed Apps.

## Demo flow

1. Demo tab → **Load sample week** (one deadline at risk, one on track).
2. **Launch fake game** → launch reminder names CSCA48 A2 and the planned work block.
3. **Speed up time** (1s = 6 min) → long-session alert after about 10 seconds.

## Layout

```
gameline/
  detectors/   plug-in game detectors behind GameDetector.get_running_games()
  llm/         provider-agnostic EstimatorLLM: claude (default), stub; add gemini here
  estimator.py LLM effort/importance/chunk plan, only on add or edit
  planner.py   slack math (plain code): who is at risk
  watcher.py   polling thread -> game start/stop/tick events
  reminders.py launch reminder + long-session alert
  clock.py     accelerable clock for demo mode
  notify.py    desktop notifications with osascript fallback
  context.py   user actions shared by the UI and tests
  ui/          PySide6 (Qt) window + menu bar icon; runs on macOS/Windows/Linux
```

## Detector notes

- Steam on macOS: `registry.vdf` has no `RunningAppID` while idle (checked 2026-10-16). Still to verify while a game is running. Process paths under `steamapps/common/` already identify Steam games.
- Windows detectors (registry `RunningAppID`, Epic manifests) are planned but untested.
