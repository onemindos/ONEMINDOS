#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Brand at one point: write every derived brand file from brand/brand.json.

The founder edits brand/ only (brand.json, the logo files) and runs:

  python3 -I scripts/brand-sync.py           # write every derived file
  python3 -I scripts/brand-sync.py --check   # exit 1 if any derived file is out of date (CI)

Stdlib only. Deterministic: the same brand.json and logo files give byte-identical output.
It never resizes images; it copies the PNG sizes that exist in brand/logo/png/. Sizes it
cannot copy (iOS/Android/Tauri icon sets) are made in CI by scripts/brand-icons.py.

What it writes (brand/README.md "Where the brand goes" has the full table):
  brand/generated/brand.tokens.json     derived colour ramps with their contrast ratios
  brand/generated/os/...                os-release keys, motd, Plymouth theme, GRUB colours
  ui/src/tokens/brand.generated.ts      name, accent ramp and logo paths the design tokens import
  dashboard/...                         brand.generated.ts/.css, logo SVGs, favicons, manifest, index.html block
  site/...                              brand.generated.json/.css, logo SVGs, favicons
After writing, it re-runs ui/scripts/gen-tokens.ts (Node >= 22.6) so ui/src/tokens/tokens.css follows.

Colour maths is a port of ui/src/customize/color.ts and accents.ts (WCAG 2.2 contrast,
OKLab by Bjorn Ottosson, public-domain matrices), so the accent written here is exactly the
one the Appearance engine derives from the same seed.
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = os.path.join(ROOT, "brand")
AA = 4.5
GEN_NOTE = "Generated from brand/brand.json by scripts/brand-sync.py. Do not edit by hand."
INDEX_START = "<!-- brand:start ("
INDEX_END = "<!-- brand:end -->"
GRUB_COLOURS = {"black", "blue", "green", "cyan", "red", "magenta", "brown", "light-gray", "dark-gray",
                "light-blue", "light-green", "light-cyan", "light-red", "light-magenta", "yellow", "white"}


class BrandError(Exception):
    pass


# ----------------------------------------------------------------------------- colour maths
# Mirrors ui/src/customize/color.ts line for line. js_round() is JavaScript's Math.round.

def js_round(v):
    return math.floor(v + 0.5)


def norm_hex(v):
    m = re.fullmatch(r"#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", v.strip())
    if not m:
        raise BrandError(f"not a hex colour: {v!r}")
    h = m.group(1).lower()
    if len(h) == 3:
        h = "".join(c + c for c in h)
    return "#" + h


def hex_rgb(h):
    h = norm_hex(h)
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def rgb_hex(r, g, b):
    return "#" + "".join(f"{min(255, max(0, js_round(v))):02x}" for v in (r, g, b))


def _lin(c):
    s = c / 255
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def _unlin(c):
    s = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return s * 255


def luminance(h):
    r, g, b = hex_rgb(h)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = (la, lb) if la > lb else (lb, la)
    return (hi + 0.05) / (lo + 0.05)


def mix(top, bottom, alpha):
    t, u = hex_rgb(top), hex_rgb(bottom)
    a = min(1, max(0, alpha))
    return rgb_hex(*(t[i] * a + u[i] * (1 - a) for i in range(3)))


def to_oklch(h):
    R, G, B = (_lin(c) for c in hex_rgb(h))
    l = math.cbrt(0.4122214708 * R + 0.5363325363 * G + 0.0514459929 * B)
    m = math.cbrt(0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B)
    s = math.cbrt(0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B)
    L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s
    A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s
    Bb = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s
    return L, math.sqrt(A * A + Bb * Bb), (math.atan2(Bb, A) * 180 / math.pi + 360) % 360


def _oklch_linear(L, c, h):
    hr = h * math.pi / 180
    A, B = c * math.cos(hr), c * math.sin(hr)
    l = (L + 0.3963377774 * A + 0.2158037573 * B) ** 3
    m = (L - 0.1055613458 * A - 0.0638541728 * B) ** 3
    s = (L - 0.0894841775 * A - 1.291485548 * B) ** 3
    return (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s)


def from_oklch(L, c, h):
    for _ in range(40):
        rgb = _oklch_linear(L, c, h)
        if all(-0.0005 <= v <= 1.0005 for v in rgb):
            return rgb_hex(*(_unlin(max(0, v)) for v in rgb))
        c *= 0.9
    return rgb_hex(*(_unlin(v) for v in _oklch_linear(L, 0, h)))


def with_lightness(h, l):
    _, c, hue = to_oklch(h)
    return from_oklch(min(1, max(0, l)), c, hue)


# ----------------------------------------------------------------------------- ui accent
# Mirrors deriveAccent()/build() in ui/src/customize/accents.ts.

def ui_neutrals():
    """The ui neutral ramp, read from ui/src/tokens/tokens.ts (surfaces the accent must pass on)."""
    src = read_text(os.path.join(ROOT, "ui/src/tokens/tokens.ts"))
    m = re.search(r"neutral:\s*\{(.*?)\}", src, re.S)
    if not m:
        raise BrandError("ui/src/tokens/tokens.ts: neutral palette not found")
    ramp = {int(k): v for k, v in re.findall(r"(\d+):\s*'(#[0-9a-f]{6})'", m.group(1))}
    for k in (0, 25, 850, 900, 950):
        if k not in ramp:
            raise BrandError(f"ui/src/tokens/tokens.ts: neutral[{k}] missing")
    return ramp


def ui_theme_refs(n):
    # Same roles tokens.ts uses: light bg/surface/raised and accent-text; same for dark.
    return {
        "light": {"surfaces": [n[25], n[0], n[0]], "surface": n[0], "text": n[0], "soft": 0.1},
        "dark": {"surfaces": [n[950], n[900], n[850]], "surface": n[900], "text": n[950], "soft": 0.18},
    }


def accent_set(accent, theme, ref):
    l = to_oklch(accent)[0]
    hover = with_lightness(accent, l - 0.06 if theme == "light" else min(0.96, l + 0.07))
    return {"accent": accent, "hover": hover, "text": ref["text"], "soft": mix(accent, ref["surface"], ref["soft"])}


def worst(s, ref):
    return min([contrast(s["accent"], x) for x in ref["surfaces"]] +
               [contrast(s["accent"], s["soft"]), contrast(s["text"], s["accent"]), contrast(s["text"], s["hover"])])


def derive_accent(seed, theme, ref):
    requested = norm_hex(seed)
    start = to_oklch(requested)[0]
    step = -0.01 if theme == "light" else 0.01
    for i in range(101):
        l = start + step * i
        if l < 0.05 or l > 0.97:
            break
        cand = requested if i == 0 else with_lightness(requested, l)
        s = accent_set(cand, theme, ref)
        r = worst(s, ref)
        if r >= AA:
            return s, r
    raise BrandError(f"accent seed {seed} cannot reach WCAG AA in the {theme} theme at any lightness")


def ensure(colour, backgrounds, darker):
    """Move OKLCH lightness until `colour` reaches AA on every background."""
    start = to_oklch(colour)[0]
    for i in range(101):
        c = colour if i == 0 else with_lightness(colour, start + (-0.01 if darker else 0.01) * i)
        if min(contrast(c, b) for b in backgrounds) >= AA:
            return c
    raise BrandError(f"{colour} cannot reach AA on {backgrounds}")


def best_foreground(bg):
    k, w = contrast("#000000", bg), contrast("#ffffff", bg)
    return ("#000000", k) if k >= w else ("#ffffff", w)


# ----------------------------------------------------------------------------- brand model

def read_text(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def read_bytes(p):
    with open(p, "rb") as f:
        return f.read()


def load_brand():
    b = json.loads(read_text(os.path.join(BRAND, "brand.json")))
    for k in ("name", "shortName", "tagline", "description", "homepage", "trademark", "colors", "accent", "logo"):
        if k not in b:
            raise BrandError(f"brand.json: missing {k}")
    cols = {k: norm_hex(v["hex"]) for k, v in b["colors"].items()}

    def col(ref):
        if ref in cols:
            return cols[ref]
        return norm_hex(ref)
    b["_col"] = col
    for vid, v in b["logo"]["variants"].items():
        for p in [v["svg"]] + [v["png"].format(size=s) for s in b["logo"]["sizes"]]:
            if not os.path.isfile(os.path.join(BRAND, p)):
                raise BrandError(f"brand.json: logo {vid}: {p} does not exist under brand/")
    return b


def png(b, variant, size):
    v = b["logo"]["variants"][variant]
    if size not in b["logo"]["sizes"]:
        raise BrandError(f"no {size}px PNG of {variant}; sizes are {b['logo']['sizes']} (other sizes: CI)")
    return os.path.join("brand", v["png"].format(size=size))


def svg_paths(b, variant="color"):
    """viewBox and the brain/circuit path data of a variant (paths are the same in every variant)."""
    v = b["logo"]["variants"][variant]
    src = read_text(os.path.join(BRAND, v["svg"]))
    vb = re.search(r'viewBox="([^"]+)"', src)
    paths = re.findall(r'<path\s+fill="(#[0-9A-Fa-f]{6})"\s+fill-rule="evenodd"\s+d="([^"]+)"\s*/>', src)
    if not vb or len(paths) != 2:
        raise BrandError(f"{v['svg']}: expected a viewBox and two <path fill=... fill-rule=evenodd d=...> layers")
    want = {k: b["_col"](c) for k, c in v["fills"].items()}
    out = {}
    if want["brain"] == want["circuit"]:
        out = {"brain": paths[0][1], "circuit": paths[1][1]}
    else:
        for fill, d in paths:
            role = next((r for r, c in want.items() if c == norm_hex(fill)), None)
            if role is None:
                raise BrandError(f"{v['svg']}: fill {fill} matches neither brain nor circuit in brand.json")
            out[role] = d
    return vb.group(1), out


def fills(b, variant):
    return {k: b["_col"](c) for k, c in b["logo"]["variants"][variant]["fills"].items()}


def dual_favicon(b):
    """One SVG favicon that follows the browser theme: light variant, dark variant in dark mode."""
    vb, d = svg_paths(b)
    lf, df = fills(b, b["favicon"]["light"]), fills(b, b["favicon"]["dark"])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" role="img" aria-label="{b["logo"]["alt"]}">\n'
            f'<!-- {GEN_NOTE} Trademark: see brand/README.md. -->\n'
            f'<title>{b["logo"]["alt"]}</title>\n'
            f'<style>.b{{fill:{lf["brain"]}}}.c{{fill:{lf["circuit"]}}}'
            f'@media (prefers-color-scheme: dark){{.b{{fill:{df["brain"]}}}.c{{fill:{df["circuit"]}}}}}</style>\n'
            f'<path class="b" fill-rule="evenodd" d="{d["brain"]}"/>\n'
            f'<path class="c" fill-rule="evenodd" d="{d["circuit"]}"/>\n'
            f'</svg>\n')


def derive(b):
    n = ui_neutrals()
    refs = ui_theme_refs(n)
    seed = b["_col"](b["accent"]["seed"])
    ui = {}
    for t in ("light", "dark"):
        s, r = derive_accent(seed, t, refs[t])
        ui[t] = dict(s, ratio=round(r, 2))
    # Website (Starlight + landing page). Backgrounds: Starlight's own and the landing page's.
    site_bg = {"light": ["#ffffff", "#fbfbf9"], "dark": ["#17181c", "#0b0f14", "#121821"]}
    low_d = mix(seed, "#17181c", 0.3)
    low_l = mix(seed, "#ffffff", 0.12)
    site = {
        "dark": {"low": low_d,
                 "accent": ensure(ui["dark"]["accent"], site_bg["dark"] + [low_d], darker=False),
                 "high": ensure(with_lightness(seed, 0.88), site_bg["dark"] + [low_d], darker=False)},
        "light": {"low": low_l,
                  "accent": ensure(ui["light"]["accent"], site_bg["light"] + [low_l], darker=True),
                  "high": ensure(with_lightness(seed, 0.35), site_bg["light"] + [low_l], darker=True)},
    }
    fg = {k: dict(zip(("foreground", "ratio"), best_foreground(norm_hex(v["hex"])))) for k, v in b["colors"].items()}
    for v in fg.values():
        v["ratio"] = round(v["ratio"], 2)
    return {"seed": seed, "ui": ui, "site": site, "foregrounds": fg}


# ----------------------------------------------------------------------------- outputs

def ts_str(v):
    return json.dumps(v, ensure_ascii=False)


def jdump(v):
    return json.dumps(v, indent=2, ensure_ascii=False) + "\n"


def outputs(b):
    """Return {repo-relative path: bytes} for every derived file."""
    out = {}
    d = derive(b)
    seed, ui, site = d["seed"], d["ui"], d["site"]
    vb, paths = svg_paths(b)
    light_f, dark_f = fills(b, "color"), fills(b, "on-dark")
    col = b["_col"]

    def text(p, s):
        out[p] = s.encode("utf-8")

    def copy(p, src):
        out[p] = read_bytes(os.path.join(ROOT, src))

    # --- brand/generated: the derived ramps, so anyone can read the numbers.
    text("brand/generated/brand.tokens.json", jdump({
        "_note": GEN_NOTE,
        "name": b["name"], "shortName": b["shortName"],
        "colors": {k: col(k) for k in b["colors"]},
        "foregrounds": d["foregrounds"],
        "accent": {"id": b["accent"]["id"], "name": b["accent"]["name"], "seed": seed,
                   "ui": ui, "site": site},
        "rule": "WCAG 2.2 AA: accent >= 4.5:1 on its surfaces and on accent-soft; accent-text >= 4.5:1 on accent and hover",
    }))

    # --- ui: the design tokens import this file.
    acc = lambda t: {k: ui[t][k] for k in ("accent", "hover", "text", "soft")}
    text("ui/src/tokens/brand.generated.ts",
         "// SPDX-License-Identifier: Apache-2.0\n"
         f"// {GEN_NOTE}\n"
         "// The logo paths are the OneMind trademark (brand/README.md), not Apache-2.0 artwork.\n"
         "export const brand = {\n"
         f"  name: {ts_str(b['name'])},\n"
         f"  shortName: {ts_str(b['shortName'])},\n"
         f"  tagline: {ts_str(b['tagline'])},\n"
         f"  description: {ts_str(b['description'])},\n"
         "  accent: {\n"
         f"    id: {ts_str(b['accent']['id'])},\n"
         f"    name: {ts_str(b['accent']['name'])},\n"
         f"    seed: {ts_str(seed)},\n"
         f"    light: {ts_str(acc('light'))},\n"
         f"    dark: {ts_str(acc('dark'))},\n"
         "  },\n"
         "  logo: {\n"
         f"    alt: {ts_str(b['logo']['alt'])},\n"
         f"    viewBox: {ts_str(vb)},\n"
         f"    light: {ts_str(light_f)},\n"
         f"    dark: {ts_str(dark_f)},\n"
         f"    brain: {ts_str(paths['brain'])},\n"
         f"    circuit: {ts_str(paths['circuit'])},\n"
         "  },\n"
         "} as const;\n")

    # --- dashboard
    for v in ("color", "on-dark"):
        copy(f"dashboard/src/assets/brand/onemind-mark-{v}.svg", os.path.join("brand", b["logo"]["variants"][v]["svg"]))
    text("dashboard/src/brand.generated.ts",
         "// SPDX-License-Identifier: Apache-2.0\n"
         f"// {GEN_NOTE}\n"
         "import markColor from './assets/brand/onemind-mark-color.svg';\n"
         "import markOnDark from './assets/brand/onemind-mark-on-dark.svg';\n\n"
         "export const brand = {\n"
         f"  name: {ts_str(b['name'])},\n"
         f"  shortName: {ts_str(b['shortName'])},\n"
         f"  tagline: {ts_str(b['tagline'])},\n"
         f"  logo: {{ alt: {ts_str(b['logo']['alt'])}, color: markColor, onDark: markOnDark }},\n"
         "} as const;\n")
    text("dashboard/src/brand.generated.css",
         "/* SPDX-License-Identifier: Apache-2.0 */\n"
         f"/* {GEN_NOTE} */\n"
         ":root {\n"
         f"  --brand-red: {seed};\n"
         f"  --accent: {ui['light']['accent']};\n"
         f"  --accent-hover: {ui['light']['hover']};\n"
         f"  --accent-ink: {ui['light']['text']};\n"
         f"  --accent-soft: {ui['light']['soft']};\n"
         "}\n")
    fav = b["favicon"]
    text("dashboard/public/brand/favicon.svg", dual_favicon(b))
    for s in fav["png"]["sizes"]:
        copy(f"dashboard/public/brand/favicon-{s}.png", png(b, fav["png"]["variant"], s))
    wm = b["webManifest"]
    icons = []
    for s in wm["icons"]["sizes"]:
        name = f"brand/onemind-mark-{wm['icons']['variant']}-{s}.png"
        copy(f"dashboard/public/{name}", png(b, wm["icons"]["variant"], s))
        icons.append({"src": name, "sizes": f"{s}x{s}", "type": "image/png", "purpose": "any"})
    icons.append({"src": "brand/favicon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"})
    text("dashboard/public/manifest.webmanifest", jdump({
        "name": b["name"], "short_name": b["shortName"], "description": b["description"],
        "start_url": ".", "scope": ".", "display": "standalone",
        "theme_color": col(wm["themeColor"]), "background_color": col(wm["backgroundColor"]), "icons": icons}))
    idx = "dashboard/index.html"
    block = (f"    {INDEX_START}{GEN_NOTE}) -->\n"
             f"    <title>{b['shortName']}</title>\n"
             f"    <meta name=\"description\" content=\"{b['name']} dashboard\" />\n"
             f"    <meta name=\"theme-color\" content=\"{col(wm['themeColor'])}\" />\n"
             "    <link rel=\"icon\" href=\"/brand/favicon.svg\" type=\"image/svg+xml\" />\n"
             + "".join(f"    <link rel=\"icon\" href=\"/brand/favicon-{s}.png\" sizes=\"{s}x{s}\" type=\"image/png\" />\n"
                       for s in fav["png"]["sizes"])
             + "    <link rel=\"manifest\" href=\"/manifest.webmanifest\" />\n"
             f"    {INDEX_END}\n")
    text(idx, replace_block(read_text(os.path.join(ROOT, idx)), block, idx))

    # --- site
    for v in ("color", "on-dark"):
        copy(f"site/src/assets/brand/onemind-mark-{v}.svg", os.path.join("brand", b["logo"]["variants"][v]["svg"]))
    text("site/public/favicon.svg", dual_favicon(b))
    for s in fav["png"]["sizes"]:
        copy(f"site/public/favicon-{s}.png", png(b, fav["png"]["variant"], s))
    text("site/src/brand.generated.json", jdump({
        "_note": GEN_NOTE, "name": b["name"], "shortName": b["shortName"], "tagline": b["tagline"],
        "description": b["description"], "homepage": b["homepage"], "logoAlt": b["logo"]["alt"],
        "themeColor": col(wm["themeColor"]), "faviconPngSizes": fav["png"]["sizes"]}))
    text("site/src/styles/brand.generated.css",
         "/* SPDX-License-Identifier: Apache-2.0 */\n"
         f"/* {GEN_NOTE} */\n"
         "/* Starlight accent (dark is Starlight's default theme) and the landing page accent. */\n"
         ":root {\n"
         f"  --sl-color-accent-low: {site['dark']['low']};\n"
         f"  --sl-color-accent: {site['dark']['accent']};\n"
         f"  --sl-color-accent-high: {site['dark']['high']};\n"
         f"  --om-brand-red: {seed};\n"
         f"  --om-brand-accent-dark: {site['dark']['accent']};\n"
         f"  --om-brand-accent-light: {site['light']['accent']};\n"
         "}\n"
         ":root[data-theme='light'] {\n"
         f"  --sl-color-accent-low: {site['light']['low']};\n"
         f"  --sl-color-accent: {site['light']['accent']};\n"
         f"  --sl-color-accent-high: {site['light']['high']};\n"
         "}\n")

    # --- os: a file set the image stream wires in (brand/README.md). Never written into os/.
    osb = b["os"]
    r, g, bl = hex_rgb(col(osb["ansiColor"]))
    text("brand/generated/os/os-release",
         f"# {GEN_NOTE}\n"
         "# Keys to merge into /usr/lib/os-release (brand/README.md, \"What the image stream wires\").\n"
         f"NAME=\"{osb['name']}\"\n"
         f"PRETTY_NAME=\"{osb['prettyName']}\"\n"
         f"HOME_URL=\"{b['homepage']}\"\n"
         f"ANSI_COLOR=\"38;2;{r};{g};{bl}\"\n")
    text("brand/generated/os/motd", f"\n  {osb['prettyName']}\n  {b['tagline']}\n\n")
    boot, grub = osb["boot"], osb["grub"]
    for k in ("foreground", "background", "highlight"):
        if grub[k] not in GRUB_COLOURS:
            raise BrandError(f"brand.json os.grub.{k}: {grub[k]!r} is not a GRUB colour name {sorted(GRUB_COLOURS)}")
    text("brand/generated/os/brand.env",
         f"# {GEN_NOTE}\n"
         "# Shell-sourceable. Paths are relative to the repository root.\n"
         f"ONEMIND_BRAND_NAME=\"{b['name']}\"\n"
         f"ONEMIND_BRAND_SHORT_NAME=\"{b['shortName']}\"\n"
         f"ONEMIND_BRAND_PRETTY_NAME=\"{osb['prettyName']}\"\n"
         f"ONEMIND_BRAND_RED=\"{seed}\"\n"
         f"ONEMIND_BRAND_BOOT_LOGO=\"{png(b, boot['variant'], boot['size'])}\"\n"
         f"ONEMIND_BRAND_BOOT_BACKGROUND=\"{col(boot['background'])}\"\n"
         f"ONEMIND_BRAND_GRUB_LOGO=\"{png(b, grub['variant'], grub['size'])}\"\n"
         f"ONEMIND_BRAND_PLYMOUTH_THEME=\"brand/generated/os/plymouth/onemind\"\n")
    text("brand/generated/os/plymouth/onemind/onemind.plymouth",
         f"# {GEN_NOTE}\n"
         "[Plymouth Theme]\n"
         f"Name={osb['prettyName']}\n"
         f"Description={osb['prettyName']} boot splash: the logo centred on a plain background\n"
         "ModuleName=script\n\n"
         "[script]\n"
         "ImageDir=/usr/share/plymouth/themes/onemind\n"
         "ScriptFile=/usr/share/plymouth/themes/onemind/onemind.script\n")
    br, bg_, bb = (c / 255 for c in hex_rgb(col(boot["background"])))
    text("brand/generated/os/plymouth/onemind/onemind.script",
         f"# {GEN_NOTE}\n"
         f"# logo.png is {png(b, boot['variant'], boot['size'])}, copied in by the image build.\n"
         f"Window.SetBackgroundTopColor({br:.3f}, {bg_:.3f}, {bb:.3f});\n"
         f"Window.SetBackgroundBottomColor({br:.3f}, {bg_:.3f}, {bb:.3f});\n"
         "logo.image = Image(\"logo.png\");\n"
         "logo.sprite = Sprite(logo.image);\n"
         "logo.sprite.SetX(Window.GetX() + Window.GetWidth() / 2 - logo.image.GetWidth() / 2);\n"
         "logo.sprite.SetY(Window.GetY() + Window.GetHeight() / 2 - logo.image.GetHeight() / 2);\n\n"
         "message_sprite = Sprite();\n"
         "message_sprite.SetPosition(Window.GetX() + Window.GetWidth() / 2, "
         "Window.GetY() + Window.GetHeight() * 0.8, 1);\n"
         "fun message_callback(text) {\n"
         "  message_image = Image.Text(text, 1, 1, 1);\n"
         "  message_sprite.SetImage(message_image);\n"
         "  message_sprite.SetX(Window.GetX() + Window.GetWidth() / 2 - message_image.GetWidth() / 2);\n"
         "}\n"
         "Plymouth.SetMessageFunction(message_callback);\n")
    text("brand/generated/os/grub/onemind-brand.cfg",
         f"# {GEN_NOTE}\n"
         "# Source from the image's grub.cfg before the menu entries (brand/README.md).\n"
         f"set color_normal={grub['foreground']}/{grub['background']}\n"
         f"set color_highlight={grub['background']}/{grub['highlight']}\n"
         f"set menu_color_normal={grub['foreground']}/{grub['background']}\n"
         f"set menu_color_highlight={grub['background']}/{grub['highlight']}\n"
         f"# Logo for a gfxterm background: {png(b, grub['variant'], grub['size'])}\n")
    return out


def replace_block(src, block, where):
    s = src.find(INDEX_START)
    e = src.find(INDEX_END)
    if s < 0 or e < 0:
        raise BrandError(f"{where}: add the lines '{INDEX_START}...) -->' and '{INDEX_END}' around the brand tags")
    s = src.rfind("\n", 0, s) + 1
    e = src.find("\n", e) + 1
    return src[:s] + block + src[e:]


# ----------------------------------------------------------------------------- main

def run_tokens(check):
    ui = os.path.join(ROOT, "ui")
    node = shutil.which("node")
    if not node:
        print("note: node not found; run `npm run tokens` in ui/ to refresh tokens.css", file=sys.stderr)
        return True
    cmd = [node, "--experimental-strip-types", "--no-warnings", "scripts/gen-tokens.ts"] + (["--check"] if check else [])
    p = subprocess.run(cmd, cwd=ui, capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stdout + p.stderr, file=sys.stderr, end="")
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="fail if any derived file is out of date; write nothing")
    ap.add_argument("--no-tokens", action="store_true", help="skip re-running ui/scripts/gen-tokens.ts")
    a = ap.parse_args()
    try:
        b = load_brand()
        files = outputs(b)
    except (BrandError, KeyError, ValueError) as e:
        print(f"brand-sync: {e}", file=sys.stderr)
        return 2
    stale = []
    for rel in sorted(files):
        p = os.path.join(ROOT, rel)
        cur = read_bytes(p) if os.path.isfile(p) else None
        if cur == files[rel]:
            continue
        stale.append(rel)
        if not a.check:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(files[rel])
    ok = True if a.no_tokens else run_tokens(a.check)
    if a.check:
        for rel in stale:
            print(f"out of date: {rel}")
        if stale or not ok:
            print("brand-sync: run `python3 -I scripts/brand-sync.py` and commit the result", file=sys.stderr)
            return 1
        print(f"brand-sync: {len(files)} derived files match brand/brand.json")
        return 0
    for rel in stale:
        print(f"wrote {rel}")
    print(f"brand-sync: {len(stale)} of {len(files)} derived files changed")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
