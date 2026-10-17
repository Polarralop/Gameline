# Gameline

A lightweight menu bar app that tracks your deadlines, notices when you launch a PC game, and reminds you only when you're actually behind. Built at Hack the Valley 11.

## Layout

```
gameline/
  detectors/      # plug-in game detectors behind GameDetector.get_running_games()
    base.py         # DetectedGame + GameDetector interface
    macos_process.py# psutil scan: Steam/Epic library paths + user-tagged apps
  llm/            # provider-agnostic EstimatorLLM; Claude now, Gemini later
  demo/           # fake game for reliable live demos
  __main__.py     # temporary: prints detected games every 5s
tests/
```

Planned modules: `planner/` (slack math, plain code), `watcher.py` (poll loop on a worker thread), `notify.py`, `tray.py` (rumps), `dashboard/` (Flask).

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m gameline              # watch for games
.venv/bin/python -m gameline.demo.fake_game   # in another tab: launch the fake game
```

## Detector notes

- Steam on macOS: `registry.vdf` has no `RunningAppID` while idle (checked 2026-10-16). Still to verify while a game is running. Process paths under `steamapps/common/` already identify Steam games.
- Windows detectors (registry `RunningAppID`, Epic manifests) are planned but untested.
