"""Temporary entry point: print detected games every 5 seconds.

Will become the menu bar app (rumps) with the watcher on a worker thread.
"""

import time

from .demo.fake_game import FAKE_GAME_NAME
from .detectors import default_detectors, get_running_games


def main() -> None:
    detectors = default_detectors(tagged_names=[FAKE_GAME_NAME])
    print("Detectors:", ", ".join(d.name for d in detectors))
    while True:
        games = get_running_games(detectors)
        print(time.strftime("%H:%M:%S"), [g.name for g in games] or "no games")
        time.sleep(5)


if __name__ == "__main__":
    main()
