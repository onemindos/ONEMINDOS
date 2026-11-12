#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Make the raster icon sizes brand/logo/png/ does not have. Runs in CI (.github/workflows/brand.yml),
never on a developer machine: it needs Pillow (Debian/Ubuntu package python3-pil).

  python3 scripts/brand-icons.py OUT_DIR

Reads brand/brand.json and the 1024 px PNGs, and writes:
  ios/AppIcon-1024.png                 opaque (no alpha, App Store rule), light variant on its tile
  android/adaptive-foreground-1024.png transparent, mark inside the 66/108 adaptive-icon safe zone
  android/adaptive-monochrome-1024.png white mark, same safe zone (Android 13 themed icons)
  android/adaptive-background.txt      the tile colour for adaptiveIcon.backgroundColor
  web/apple-touch-icon-180.png         opaque, light variant on its tile
  desktop/app-icon-1024.png            opaque, dark variant on its tile: the source for `tauri icon`
  manifest.json                        what was made, with sha256
The output is an artifact for the mobile and desktop builds; nothing here is committed.
"""
import hashlib
import json
import os
import sys

from PIL import Image  # CI only: apt-get install python3-pil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = os.path.join(ROOT, "brand")
MARK_ON_TILE = 0.80      # the 1024 master already has a 6 % margin; iOS and macOS round the corners
ADAPTIVE_SAFE = 66 / 108  # Android adaptive icon: 108 dp canvas, 66 dp safe circle


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def main(out):
    b = json.load(open(os.path.join(BRAND, "brand.json"), encoding="utf-8"))
    cols = {k: v["hex"] for k, v in b["colors"].items()}
    col = lambda ref: rgb(cols.get(ref, ref))
    src = lambda variant: Image.open(os.path.join(
        BRAND, b["logo"]["variants"][variant]["png"].format(size=1024))).convert("RGBA")

    def on_tile(variant, tile, size, scale):
        canvas = Image.new("RGBA", (size, size), col(tile) + (255,))
        m = src(variant).resize((round(size * scale),) * 2, Image.LANCZOS)
        canvas.alpha_composite(m, ((size - m.width) // 2, (size - m.height) // 2))
        return canvas.convert("RGB")

    def transparent(variant, size, scale):
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        m = src(variant).resize((round(size * scale),) * 2, Image.LANCZOS)
        canvas.alpha_composite(m, ((size - m.width) // 2, (size - m.height) // 2))
        return canvas

    ai = b["appIcon"]
    lt, dk = ai["light"], ai["dark"]
    made = {
        "ios/AppIcon-1024.png": on_tile(lt["variant"], lt["tile"], 1024, MARK_ON_TILE),
        "android/adaptive-foreground-1024.png": transparent(lt["variant"], 1024, ADAPTIVE_SAFE),
        "android/adaptive-monochrome-1024.png": transparent("white", 1024, ADAPTIVE_SAFE),
        "web/apple-touch-icon-180.png": on_tile(lt["variant"], lt["tile"], 180, MARK_ON_TILE),
        "desktop/app-icon-1024.png": on_tile(dk["variant"], dk["tile"], 1024, MARK_ON_TILE),
    }
    manifest = {}
    for rel, img in made.items():
        p = os.path.join(out, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        img.save(p, "PNG", optimize=True)
        manifest[rel] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    bg = os.path.join(out, "android/adaptive-background.txt")
    with open(bg, "w") as f:
        f.write(cols.get(lt["tile"], lt["tile"]) + "\n")
    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump({"source": "brand/brand.json", "files": manifest}, f, indent=2)
        f.write("\n")
    for rel in sorted(manifest):
        print(f"wrote {rel}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
