"""A stand-in 'game' for demos: python -m gameline.demo.fake_game

macOS reports a Python script's process name as "Python", so the fake game
is a tiny compiled binary inside GamelineDemoGame.app in the data folder.
It is built with clang (Xcode Command Line Tools) on first run. Ctrl+C to 'quit the game'.
"""

import subprocess
from pathlib import Path

FAKE_GAME_NAME = "GamelineDemoGame"


def _binary() -> Path:
    from ..paths import data_dir

    return data_dir() / f"{FAKE_GAME_NAME}.app" / "Contents" / "MacOS" / FAKE_GAME_NAME


_SOURCE = b'#include <unistd.h>\nint main(void){for(;;)pause();}\n'


def build() -> Path:
    binary = _binary()
    if not binary.exists():
        binary.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["/usr/bin/cc", "-x", "c", "-o", str(binary), "-"], input=_SOURCE, check=True)
    return binary


def main() -> None:
    binary = build()
    print(f"{FAKE_GAME_NAME} running. Ctrl+C to quit.")
    try:
        subprocess.run([str(binary)])
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
