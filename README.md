# Gameline

A desktop app that tracks your deadlines, notices when you launch a PC game, and nudges you only when you're actually behind. An AI estimates how much work each deadline needs and splits it into work blocks; plain code works out whether you have the time. Built at Hack the Valley 11.

## Features

- **Deadlines with AI estimates.** Add a deadline (or bulk-add from a **syllabus PDF**) and an AI estimates effort and importance and plans work blocks around your working style. Estimates run in the background; the card shows a spinner until they land.
- **Slack, not guesswork.** A deadline is *at risk* when the work left doesn't fit in the realistic hours before it's due. That's plain code, not AI.
- **Game-aware reminders.** Launch a game while behind and you get one notification naming the deadlines at risk. Play past your session limit and you get a break alert, sooner when work is due soon, repeating at an interval you choose.
- **Notification levels.** Silent, Standard, or Interrupting (brings Gameline to the front for long sessions, after you confirm).
- **Recap.** Weekly and monthly view of work done vs. time gaming, a light/medium/heavy rating, and which games took the time.
- **Tasks you can tick off,** collapse, and complete; sort by due date or group by course.
- **First-launch onboarding** that sets up working style, games, notifications and the AI.

## AI options

Pick in **Preferences → AI estimates** (or onboarding). Keys go in `.env` (see `.env.example`).

| Option | Model | Needs |
|---|---|---|
| Gemini API key | Gemini 3.8 Flash | `GEMINI_API_KEY` |
| Claude API key | Claude Sonnet 5.5 | `ANTHROPIC_API_KEY` |
| Offline | none (rough guesses from the title) | nothing |
| Claude subscription | Claude Opus 5.5 | Claude Code installed and logged in; **developer only** |

The Claude subscription option runs your local Claude Code login, so it's hidden unless `GAMELINE_ENABLE_CLAUDE_SUBSCRIPTION=1` is set. Don't enable it in builds for other people. `GAMELINE_LLM` sets the default option.

## Run from source

```bash
cp .env.example .env     # then add your API key(s)
./run.sh                 # window + menu bar icon (creates the venv on first run)
./run.sh --detect        # just print detected games every 5 seconds
.venv/bin/python -m pytest -q
```

## Gameline.app (macOS)

```bash
./build_app.sh           # standalone build, installed to /Applications (~1 min, ~300 MB)
./build_app.sh --alias   # dev build in dist/ that runs this source folder
open -a Gameline
```

- The full build is installed to `/Applications` because macOS asks for Documents access whenever an app stored in `~/Documents` reads its own files.
- The app icon is compiled from `packaging/AppIcon.icon` with Xcode's `actool`, so macOS 26 applies its own shape. Building needs Xcode.
- Each build copies your repo `.env` into the data folder (below) so the app has your keys.
- The first notification asks to allow "Gameline". For Gaming Focus, add Gameline under Allowed Apps.

## Where data lives

One folder, shared by `./run.sh` and the app (run only one at a time, or notifications arrive twice):

- macOS: `~/Library/Application Support/Gameline`
- Windows: `%APPDATA%\Gameline`
- Linux: `~/.local/share/gameline`

It holds `state.json` (deadlines, settings, game history), `.env`, the cached Claude login status, and the demo game. **Preferences → Danger zone** can delete deadlines, game history, or everything.

## Demo

The **Demo** page has everything for a live demo:

1. **Load sample week**: one deadline at risk, one on track, plus five weeks of history for Recap.
2. **Launch fake game**: a stand-in game process; the launch reminder names CSCA48 A2 and the planned work block.
3. **Speed up time** (1 second = 6 minutes): the break alert fires within seconds.
4. **Replay onboarding**: shows the first-launch setup again.

## How it fits together

```
gameline/
  detectors/    plug-in game detectors behind GameDetector.get_running_games()
  watcher.py    polling thread: game started / stopped / tick events
  reminders.py  launch reminders and break alerts, per notification level
  planner.py    slack maths: which deadlines are at risk (plain code)
  estimator.py  AI effort, importance and work blocks; runs only on add or edit
  syllabus.py   PDF -> text -> AI -> proposed deadlines, with duplicate flags
  recap.py      weekly/monthly totals and the game-session recorder
  llm/          one EstimatorLLM interface: gemini, claude, claude_cli, stub
  context.py    every user action, shared by the UI and the tests
  store.py      JSON state; paths.py picks the data folder
  clock.py      wall-clock time that demo mode can speed up
  notify.py     desktop notifications (works through Gaming Focus)
  ui/           PySide6 (Qt) window, menu bar icon, onboarding, recap
packaging/      app icon, py2app launcher, Qt trimming; setup.py + build_app.sh build the .app
```

The UI is Qt, so it runs on macOS, Windows and Linux. Game detection is plug-in based: each platform adds detectors without touching the rest.

## Platform status

- **macOS:** built and tested. The process detector finds Steam and Epic games by install path, plus any app you tag in Preferences.
- **Windows and Linux:** the app and data folder work. Steam's `RunningAppID` registry detector and Epic manifest detection for Windows are future work, as is a Windows version of the Claude Code login button.
- **Steam `registry.vdf` on macOS** has no `RunningAppID` while idle (checked 2026-10-16); still to verify while a game is running. Install paths already identify Steam games.
