from pathlib import Path
from types import SimpleNamespace

from gameline.detectors import get_running_games
from gameline.detectors.macos_process import MacProcessDetector, bundle_name

STEAM = Path("/Users/me/Library/Application Support/Steam/steamapps/common")


def fake_procs(*procs):
    return lambda attrs: [SimpleNamespace(info=p) for p in procs]


def proc(pid, name, exe=None, t=100.0):
    return {"pid": pid, "name": name, "exe": exe, "create_time": t}


def test_bundle_name():
    assert bundle_name("/Applications/Foo Bar.app/Contents/MacOS/foo") == "Foo Bar"
    assert bundle_name("/usr/bin/python3") is None


def test_steam_library_game_detected_and_deduped():
    d = MacProcessDetector(
        library_roots=[STEAM],
        process_iter=fake_procs(
            proc(2, "factorio", str(STEAM / "Factorio/factorio.app/Contents/MacOS/factorio"), t=50),
            proc(3, "crash", str(STEAM / "Factorio/crash_handler"), t=60),
            proc(4, "Safari", "/Applications/Safari.app/Contents/MacOS/Safari"),
        ),
    )
    games = d.get_running_games()
    assert [(g.name, g.pid) for g in games] == [("Factorio", 2)]


def test_tagged_bundle_and_process_name():
    d = MacProcessDetector(
        tagged_names=["Minecraft", "GamelineDemoGame"],
        library_roots=[],
        process_iter=fake_procs(
            proc(5, "java", "/Applications/Minecraft.app/Contents/MacOS/launcher"),
            proc(6, "GamelineDemoGame", None),
            proc(7, "zsh", "/bin/zsh"),
        ),
    )
    assert sorted(g.name for g in d.get_running_games()) == ["GamelineDemoGame", "Minecraft"]


def test_detector_never_raises():
    def boom(attrs):
        raise OSError("denied")

    assert MacProcessDetector(process_iter=boom).get_running_games() == []


def test_real_process_table_runs():
    # Smoke test against the real machine: should not raise.
    assert isinstance(get_running_games([MacProcessDetector()]), list)
