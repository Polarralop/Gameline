"""A stand-in 'game' for demos: python -m gameline.demo.fake_game

macOS reports a Python script's process name as "Python", so the fake game
is a tiny compiled binary. Gameline.app ships it prebuilt (see build_app.sh);
from source it is compiled with clang on first run into the data folder.
Ctrl+C to 'quit the game'.
"""

import subprocess
from pathlib import Path

FAKE_GAME_NAME = "GamelineDemoGame"


def _binary() -> Path:
    from ..paths import data_dir

    return data_dir() / f"{FAKE_GAME_NAME}.app" / "Contents" / "MacOS" / FAKE_GAME_NAME


_SOURCE = b'#include <unistd.h>\nint main(void){for(;;)pause();}\n'


def _bundled() -> Path | None:
    """The prebuilt copy inside Gameline.app, if running packaged."""
    from ..paths import FROZEN, resources_dir

    path = resources_dir() / "demo" / FAKE_GAME_NAME
    return path if FROZEN and path.exists() else None


def build() -> Path:
    bundled = _bundled()
    if bundled:
        return bundled
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
