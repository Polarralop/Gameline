# Gameline build plan

The build is about 19 hours of work plus buffer, against roughly 24–30 hours available. Milestones are listed in build order. Hours are estimates.

## Done
- **M0 Scaffold (about 1h):** repo, the detector interface, the macOS process detector, a swappable LLM interface, the demo fake game, and tests.

## Core path
1. **Notification smoke test (0.5h).** Fire one test notification through `desktop-notifier`, then accept the macOS permission prompt and test it with Gaming Focus on. This goes first because it is the biggest demo risk. If Focus blocks it, the fallback is a rumps alert window.
2. **Data model and storage (1h).** A `Deadline` (title, due, notes), a `WorkingStyle` (short bursts or long sessions, plus max session length) and an `Estimate` (hours, importance, chunk plan), saved in `data/state.json`.
3. **LLM estimation (2h).** A prompt plus a JSON schema go through `EstimatorLLM.complete_json()`. It runs only when a deadline is added or edited, and the result is cached in state. A stub provider lets tests run offline.
4. **Slack planner (1.5h, plain code).** Slack is time left minus the remaining estimated work, adjusted for working style. The planner returns the deadlines at risk, sorted. It is unit tested.
5. **Watcher (2h).** A polling loop on a worker thread every 5–10s. It emits `game_started` and `game_stopped` events and tracks session length. A clock is injected so that demo mode can speed time up.
6. **Reminder logic (1.5h).** At launch, it notifies only if you are behind, naming the at-risk deadlines and any planned work block that overlaps. In a long session, it alerts at your limit, tightened by the prep time still needed. It has a cooldown so it never nags twice.
7. **Menu bar app (1.5h, rumps).** The menu shows status (on track or N deadlines at risk), Open dashboard, Demo mode and Quit. rumps owns the main thread and the watcher runs on a worker thread.
8. **Flask dashboard (3h).** Plain HTML forms to add or edit deadlines, set working style and limits, and tag apps as games. It also shows each LLM estimate and chunk plan, and a slack bar for every deadline.
9. **Demo mode (1.5h).** Seed deadlines, a "launch fake game" button, and time acceleration (a 3h session alert fires in 30s).
10. **End-to-end run (1.5h).** A full run-through on a clean venv, a `run.sh` script, and a fix list.
11. **Devpost and demo script (2h).** Pitch it on the FDM criteria (impact, the technical pipeline, not a chatbot). Describe the cross-platform plug-in architecture, list the Windows detectors as future work, and record a backup demo video.

## Changed after the core build
- Steps 1–10 are done. The dashboard and menu bar moved from Flask + rumps to a native PySide6 (Qt) app, which also runs on Windows and Linux.

## Stretch (only if core is done)
1. Syllabus reader: PDF to LLM to deadlines JSON, reusing step 3 (2–3h).
2. Steam `registry.vdf` detector: launch a game and check whether `RunningAppID` appears.
3. Windows detectors, written and marked untested.
4. A Discord bot as a channel for phone notifications.

## Cut line
If steps 1–7 aren't done by Saturday evening, the dashboard shrinks to a single form plus a list (step 8 becomes 1h), and every stretch goal is skipped. Steps 9 and 11 are never cut, because the demo depends on them.
