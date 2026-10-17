"""Render assets/icons/logo.svg into packaging/Gameline.icns (needs macOS iconutil)."""

import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]


def render(size: int) -> QImage:
    """The logo already is a rounded tile; size it to Apple's icon grid
    (tile = 824/1024 of the icon). Same maths as dock_icon() in gameline/ui/app.py."""
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    drawn = size * (824 / 1024) / (120 / 128)
    inset = (size - drawn) / 2
    QSvgRenderer(str(ROOT / "assets/icons/logo.svg")).render(p, QRectF(inset, inset, drawn, drawn))
    p.end()
    return img


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841 (Qt needs an app for fonts/rendering)
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "Gameline.iconset"
        iconset.mkdir()
        for base in (16, 32, 128, 256, 512):
            render(base).save(str(iconset / f"icon_{base}x{base}.png"))
            render(base * 2).save(str(iconset / f"icon_{base}x{base}@2x.png"))
        out = ROOT / "packaging" / "Gameline.icns"
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)], check=True)
        print(out)


if __name__ == "__main__":
    main()
