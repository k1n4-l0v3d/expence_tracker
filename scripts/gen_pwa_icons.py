#!/usr/bin/env python3
"""Generate PWA icons: static/icons/icon-192.png and static/icons/icon-512.png.

Run from project root: python scripts/gen_pwa_icons.py
Requires Pillow (pip install pillow).
"""
import os
from PIL import Image


ICONS_DIR = os.path.join(os.path.dirname(__file__), '..', 'static', 'icons')


def gen_png(size: int, path: str) -> None:
    img = Image.new('RGBA', (size, size))
    pixels = img.load()

    # Diagonal gradient: #4361ee → #e8115b
    r1, g1, b1 = 0x43, 0x61, 0xee  # top-left colour
    r2, g2, b2 = 0xe8, 0x11, 0x5b  # bottom-right colour

    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            r = int(r1 + (r2 - r1) * t)
            g = int(g1 + (g2 - g1) * t)
            b = int(b1 + (b2 - b1) * t)
            pixels[x, y] = (r, g, b, 255)

    img.save(path, 'PNG')
    print(f"  ✓ {os.path.basename(path)} ({size}×{size})")


def main() -> None:
    os.makedirs(ICONS_DIR, exist_ok=True)
    print("Generating PWA icons...")
    gen_png(192, os.path.join(ICONS_DIR, 'icon-192.png'))
    gen_png(512, os.path.join(ICONS_DIR, 'icon-512.png'))
    print("Done.")


if __name__ == '__main__':
    main()
