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
    """Full-bleed, opaque square artwork. macOS 26 (Tahoe) applies the rounded
    mask itself; an icon that arrives already rounded, with transparent
    margins, gets shrunk onto a white tile ("icon jail"). So the logo's
    rounded tile is swapped for a square that fills the canvas."""
    svg = (ROOT / "assets/icons/logo.svg").read_text()
    svg = svg.replace('<rect x="4" y="4" width="120" height="120" rx="28" fill="url(#bg)"/>',
                      '<rect x="0" y="0" width="128" height="128" fill="url(#bg)"/>')
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(svg.encode()).render(p, QRectF(0, 0, size, size))
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
