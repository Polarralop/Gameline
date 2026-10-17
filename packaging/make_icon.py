"""Build Gameline's app icon the macOS 26 way.

packaging/AppIcon.icon is an Icon Composer document: a gradient fill plus the
logo glyph (logo.svg without its rounded tile). Xcode's actool compiles it to
Assets.car + AppIcon.icns, and macOS applies the system shape and glass itself.
A hand-made .icns with its own rounded corners gets shrunk onto a white tile
("icon jail") on macOS 26, which is why it's done this way.

Output: packaging/icon-build/{Assets.car, AppIcon.icns}. Needs Xcode.
"""

import re
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
ICON = ROOT / "packaging" / "AppIcon.icon"
OUT = ROOT / "packaging" / "icon-build"


def render_glyph() -> None:
    """The logo minus its background tile, on a transparent 1024 canvas."""
    svg = re.sub(r'<rect x="4"[^>]*/>', "", (ROOT / "assets/icons/logo.svg").read_text())
    img = QImage(1024, 1024, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(svg.encode()).render(p, QRectF(0, 0, 1024, 1024))
    p.end()
    (ICON / "Assets").mkdir(parents=True, exist_ok=True)
    img.save(str(ICON / "Assets" / "glyph.png"))


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841 (Qt needs an app to render)
    render_glyph()
    OUT.mkdir(exist_ok=True)
    subprocess.run(
        ["xcrun", "actool", str(ICON), "--compile", str(OUT), "--platform", "macosx",
         "--minimum-deployment-target", "13.0", "--app-icon", "AppIcon",
         "--output-partial-info-plist", str(OUT / "partial.plist")],
        check=True, stdout=subprocess.DEVNULL,
    )
    print(OUT / "AppIcon.icns")


if __name__ == "__main__":
    main()
