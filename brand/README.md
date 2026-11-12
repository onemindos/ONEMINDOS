# OneMind brand: the logo

![The four logo variants](logo/preview.png)

**The mark:** a split brain. The left half is a human brain and the right half is a circuit. Mind and machine are two halves of one whole, which is the "one mind" idea behind OneMind OS.

**Status:** this is the founder's existing logo (2026-11-12), the same mark the earlier OneMind portal used. It replaces the teal placeholder icon in `site/`, which was never the brand. The trademark clearance for the "OneMind" name (Z-29 in `research-output/26-…`) is still open, so a name change could still affect the wordmark later. The mark itself stays.

## Files
Every file has a **transparent background**.

| Variant | Use it on | Colours | Vector | PNG sizes |
|---|---|---|---|---|
| `color` (primary) | light backgrounds | brain black, circuit red | `logo/svg/onemind-mark-color.svg` | `logo/png/color/` |
| `on-dark` | dark backgrounds: dark mode, boot screen, dashboard dark theme | brain red, circuit white | `logo/svg/onemind-mark-on-dark.svg` | `logo/png/on-dark/` |
| `white` | one-colour on dark: boot splash, engraving, stickers on dark | all white | `logo/svg/onemind-mark-white.svg` | `logo/png/white/` |
| `black` | one-colour on light: print, fax-style docs, laser marks | all black | `logo/svg/onemind-mark-black.svg` | `logo/png/black/` |

- PNG sizes in each folder: 1191 (master), 1024, 512, 256, 128, 64 and 32 px, all square.
- Use the **SVG** wherever possible (website, dashboard, phone apps, docs). Use the PNGs where a format needs pixels: favicons, app-store icons, the boot splash, GRUB and Plymouth themes.

## Colours
| Name | Hex | Where |
|---|---|---|
| OneMind Red | `#FF333A` | circuit (primary), brain (on-dark) |
| Black | `#000000` | brain (primary) |
| White | `#FFFFFF` | circuit (on-dark), mono white |

These were measured from the founder's master file. The portal's dark logo used `#FF333A` too.

## Where it goes in the OS (for the build and UI streams)
- **Boot:** a Plymouth theme and the GRUB background use `white` or `on-dark` PNGs (owner: `os/`, image stream).
- **Dashboard and rescue console:** use the `color` and `on-dark` SVGs; the favicon uses `color` 32/64 (owners: `dashboard/`, `ui/`).
- **Phone apps:** the app icon comes from `color` 1024 on a white tile, or `on-dark` on a black tile (owner: `mobile/`).
- **Website:** `site/src/assets/mark.svg` and `site/public/favicon.svg` should become `onemind-mark-color.svg` (owner: `site/`).

The swap in each place is left to the stream that owns that folder, so this PR does not touch their files.

## How these were made (reproducible)
- **Source:** the founder's transparent master PNG of the mark (3000×2000).
- **Steps:**
  1. Cropped to the mark plus a 6 % margin on each side, giving a square master of 1191×1191.
  2. Split the pixels by colour into "brain" (black) and "circuit" (red) layers. The variants recolour those two layers; the shape is unchanged.
  3. Resized the PNGs with Lanczos.
  4. Traced the SVGs with potrace (the `potracer` Python port), one path per layer.
- **Checks:** a visual check against the original at 400 px, and the on-dark scheme matches the portal's existing dark logo.

## Licence
The logo is a **trademark of OneMind**, not code. The repo's Apache-2.0 licence does **not** grant use of the name or logo; Apache-2.0 §6 excludes trademarks. Third parties may use the logo only to refer to OneMind factually, unchanged.
