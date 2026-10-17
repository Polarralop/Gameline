# Gameline

A lightweight menu bar app that tracks your deadlines, notices when you launch a PC game, and reminds you only when you're actually behind. Built at Hack the Valley 11.

## Run

```bash
./run.sh                 # menu bar app + dashboard at http://127.0.0.1:5157
./run.sh --detect        # just print detected games every 5s
.venv/bin/python -m pytest -q
```

Put `ANTHROPIC_API_KEY=...` in `.env` for real estimates, or set `GAMELINE_LLM=stub` to run offline.

## Demo flow

1. Dashboard → **Load sample week** (one deadline at risk, one on track).
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
  dashboard/   Flask + plain HTML forms
  tray.py      rumps menu bar app (main thread)
```

## Detector notes

- Steam on macOS: `registry.vdf` has no `RunningAppID` while idle (checked 2026-10-16). Still to verify while a game is running. Process paths under `steamapps/common/` already identify Steam games.
- Windows detectors (registry `RunningAppID`, Epic manifests) are planned but untested.
