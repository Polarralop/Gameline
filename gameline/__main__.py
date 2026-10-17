"""Entry point: python -m gameline starts the menu bar app.

python -m gameline --detect prints detected games every 5 seconds instead,
which is handy for checking detectors without the UI.
"""

import logging
import sys
import time


def detect_loop() -> None:
    from .context import AppContext
    from .detectors import get_running_games

    ctx = AppContext()
    while True:
        games = get_running_games(ctx.detectors())
        print(time.strftime("%H:%M:%S"), [g.name for g in games] or "no games")
        time.sleep(5)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    if "--detect" in sys.argv:
        detect_loop()
    else:
        from .ui.app import run

        run()


if __name__ == "__main__":
    main()
