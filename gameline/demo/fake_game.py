"""A stand-in 'game' for demos: python -m gameline.demo.fake_game

macOS reports a Python script's process name as "Python", so the fake game
is a tiny compiled binary inside data/GamelineDemoGame.app. It is built with
clang (Xcode Command Line Tools) on first run. Ctrl+C to 'quit the game'.
"""

import subprocess
from pathlib import Path

FAKE_GAME_NAME = "GamelineDemoGame"

APP_DIR = Path(__file__).resolve().parents[2] / "data" / f"{FAKE_GAME_NAME}.app"
BINARY = APP_DIR / "Contents" / "MacOS" / FAKE_GAME_NAME

_SOURCE = b'#include <unistd.h>\nint main(void){for(;;)pause();}\n'


def build() -> Path:
    if not BINARY.exists():
        BINARY.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["cc", "-x", "c", "-o", str(BINARY), "-"], input=_SOURCE, check=True)
    return BINARY


def main() -> None:
    binary = build()
    print(f"{FAKE_GAME_NAME} running. Ctrl+C to quit.")
    try:
        subprocess.run([str(binary)])
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
