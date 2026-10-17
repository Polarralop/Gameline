"""Trim the full Gameline.app: PySide6 ships every Qt module (3D, WebEngine,
QML...), about 1.2 GB. Gameline only uses Core, Gui, Widgets and Svg, so the
rest is removed after py2app copies it in. Dependencies were checked with
`otool -L`: Gui also links DBus, so that stays too."""

import shutil
import sys
from pathlib import Path

KEEP_MODULES = {"QtCore", "QtGui", "QtWidgets", "QtSvg"}
KEEP_FRAMEWORKS = KEEP_MODULES | {"QtDBus"}
KEEP_PLUGINS = {"platforms", "imageformats", "iconengines", "styles"}
DROP_DIRS = ["qml", "translations", "metatypes", "libexec"]


def prune(app: Path) -> int:
    root = next(app.glob("Contents/Resources/lib/python3*/PySide6"))
    before = sum(f.stat().st_size for f in root.rglob("*") if f.is_file())
    for so in root.glob("Qt*.abi3.so"):
        if so.name.split(".")[0] not in KEEP_MODULES:
            so.unlink()
    for fw in (root / "Qt" / "lib").glob("*.framework"):
        if fw.stem not in KEEP_FRAMEWORKS:
            shutil.rmtree(fw)
    for plugin in (root / "Qt" / "plugins").iterdir():
        if plugin.name not in KEEP_PLUGINS:
            shutil.rmtree(plugin)
    for name in DROP_DIRS:
        shutil.rmtree(root / "Qt" / name, ignore_errors=True)
    for extra in root.glob("*.app"):  # Designer, Assistant, Linguist...
        shutil.rmtree(extra)
    after = sum(f.stat().st_size for f in root.rglob("*") if f.is_file())
    return before - after


if __name__ == "__main__":
    saved = prune(Path(sys.argv[1]))
    print(f"Trimmed {saved / 1e6:.0f} MB of unused Qt modules")
