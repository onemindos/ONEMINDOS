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

## How to change the brand (one place, one command)
Everything that shows the name, the colours or the logo is **generated** from this folder. To change the brand:

1. Edit `brand/brand.json` (name, tagline, colours, which logo variant goes where), and/or replace the files in `brand/logo/` (keep the file names; each variant needs the PNG sizes listed in `logo.sizes`).
2. Run, from the repository root:
   ```sh
   python3 -I scripts/brand-sync.py
   ```
   It needs only Python 3.11+ (standard library). If Node 22.6+ is installed it also refreshes `ui/src/tokens/tokens.css`; if not, run `npm run tokens` in `ui/`.
3. Commit what changed. CI (`.github/workflows/brand.yml`) runs `python3 -I scripts/brand-sync.py --check` and fails if a derived file was not regenerated.

**Never edit a generated file by hand.** Each one says "Generated from brand/brand.json" at the top (or between the `brand:start` / `brand:end` comments in `dashboard/index.html`). The copied logo files (SVG, PNG) and `dashboard/public/manifest.webmanifest` (plain JSON) have no room for that note; the table in "Where the brand goes" lists them.

### What `brand.json` holds
| Key | Meaning |
|---|---|
| `name`, `shortName`, `tagline`, `description`, `homepage` | Product name ("OneMind OS"), short name ("OneMind") for tight spaces, one-line tagline, longer description, project URL |
| `trademark` | The trademark note (see Licence below) |
| `colors` | The brand colours by name (`red` is OneMind Red `#FF333A`, `black`, `white`). Other keys refer to them by name |
| `accent` | The default UI accent: preset id `onemind`, its display name and the colour it is derived from (`seed`) |
| `logo` | Alt text, the PNG sizes that exist, and for each variant its SVG, PNG pattern and which colour each layer (brain, circuit) has |
| `favicon` | Variant for light and for dark browser themes, and the PNG favicon sizes |
| `webManifest` | Theme and background colour and the icon variant/sizes for the dashboard's web-app manifest |
| `appIcon` | Phone and desktop app icon: variant on a coloured tile, light and dark |
| `splash` | Phone app splash: variant, background colour and size |
| `os` | OS names for `os-release`, terminal colour, and the boot (Plymouth) and GRUB logo/colours |

### The derived colours (why the UI red is not exactly `#FF333A`)
Text and controls must stay readable: WCAG 2.2 AA needs a contrast of at least 4.5:1. `#FF333A` on white is only about 3.6:1, so the generator moves the red's **lightness** (keeping its hue) until every pair passes: darker on light backgrounds, lighter on dark ones. It uses the same maths as the UI's Appearance settings (OKLCH lightness), so the accent a new box starts with is exactly the "OneMind Red" preset. The numbers, with their contrast ratios, are in `brand/generated/brand.tokens.json`:

| Where | Light theme | Dark theme |
|---|---|---|
| UI accent (`ui/`, `dashboard/`) | `#d11826` (white text on it) | `#fb605a` (near-black text on it) |
| Website accent (`site/`) | `#d11826` | `#fe726a` |

The logo itself always uses the exact `#FF333A`; only text and controls use the adjusted shades.

## Where the brand goes
| Surface | Generated files (by `scripts/brand-sync.py`) | What reads them |
|---|---|---|
| UI kit `ui/` | `ui/src/tokens/brand.generated.ts` | `tokens.ts` (accent roles and the `logo-brain` / `logo-circuit` roles, then `tokens.css` via `npm run tokens`), `customize/accents.ts` (the `onemind` preset, default), `BrandMark` (the logo drawn inline, colour variant in light, on-dark in dark), `AppShell` and onboarding headers, the OS name in Settings (About, Updates) and the Home updates widget |
| Dashboard `dashboard/` | `src/brand.generated.ts`, `src/brand.generated.css`, `src/assets/brand/*.svg`, `public/brand/*` (favicons, manifest icons), `public/manifest.webmanifest`, the `brand:start…brand:end` block in `index.html` | `main.tsx` (CSS), top bar (on-dark logo), sign-in card (colour logo), home page fallback name |
| Website `site/` | `src/brand.generated.json`, `src/styles/brand.generated.css`, `src/assets/brand/*.svg`, `public/favicon.svg`, `public/favicon-*.png` | `astro.config.mjs` (title, description, Starlight logo light/dark, PNG favicons), landing page (title, nav, theme colour, accent), blog byline fallback |
| OS image | `brand/generated/os/*` (below) | the image stream, see next section |
| Phone app `mobile/` | not wired yet | see "Not wired yet" |
| Desktop app `desktop/` | not wired yet | see "Not wired yet" |
| Icon sizes not in `logo/png/` | made in CI by `scripts/brand-icons.py` (Pillow), artifact `brand-icons` of the `brand` workflow | iOS `AppIcon-1024.png` (opaque), Android adaptive foreground and monochrome (inside the 66/108 safe zone), `apple-touch-icon-180.png`, `desktop/app-icon-1024.png` (the source for `tauri icon`) |

The favicon (`favicon.svg`) is generated from the logo paths: the colour variant, switching to the on-dark variant when the browser is in dark mode.

## What the image stream must wire (`os/`)
`brand-sync.py` never writes into `os/` (the image stream owns it). It writes a ready-to-use file set to `brand/generated/os/`; the image build should copy it in like this:

| Generated file | Put it at (in the image) | How |
|---|---|---|
| `os-release` | merge its keys into `/usr/lib/os-release` | In `os/assemble/assemble.py` `finalize()`, next to the existing `ONEMIND_VERSION` lines: drop existing `NAME=`, `PRETTY_NAME=`, `HOME_URL=`, `ANSI_COLOR=` lines and append these. Keep Debian's `ID=` and `VERSION_ID=` (tools such as apt and k3s read them) |
| `motd` | `/etc/motd` | copy (replaces Debian's default text) |
| `plymouth/onemind/onemind.plymouth`, `onemind.script` | `/usr/share/plymouth/themes/onemind/` | copy, then copy the PNG named by `ONEMIND_BRAND_BOOT_LOGO` in `brand.env` there as `logo.png`; install `plymouth` + `plymouth-themes`, run `plymouth-set-default-theme onemind` and rebuild the initramfs; add `splash quiet` to the kernel command line in `os/assemble/grub.cfg.in` |
| `grub/onemind-brand.cfg` | `/boot/grub/onemind-brand.cfg` (or inline) | `source` it from `os/assemble/grub.cfg.in` before the first `menuentry`. For a logo, load `gfxterm` + `png` and use `ONEMIND_BRAND_GRUB_LOGO` as `background_image` |
| `brand.env` | build-time only | shell-sourceable names, colour and the repo paths of the boot/GRUB logos |

None of this has been booted yet: the Plymouth script and GRUB colours need a test on the VM board.

## Not wired yet
- **Phone app (`mobile/`)** and **desktop app (`desktop/`)**: #34 (photos backup, changes `mobile/app.json`) merged into `main` after this branch was cut; #33 (adds `desktop/`) is not on `main` yet. Wire each one after this branch is rebased on a `main` that has it, by adding to `scripts/brand-sync.py`:
  - `mobile/src/brand.generated.ts` (name, accent from `brand.tokens.json`) for `mobile/src/ui/theme.ts`, which still uses a blue accent;
  - copies of `appIcon.light` 1024 and the `splash` PNG into `mobile/assets/brand/`, and in `mobile/app.json`: `expo.name` = `shortName`, `expo.icon`, the splash (Expo 58: the `expo-splash-screen` config plugin with `image`, `backgroundColor`, `imageWidth`; UNVERIFIED, check the Expo 58 docs), `android.adaptiveIcon` (`foregroundImage`, `monochromeImage`, `backgroundColor`) from the CI `brand-icons` artifact;
  - `desktop/src-tauri/tauri.conf.json` `productName` = `name`, and run `npx tauri icon <brand-icons>/desktop/app-icon-1024.png` in the desktop CI to replace `desktop/src-tauri/icons/` and `desktop/assets/app-icon.svg` / `tray-icon.svg`.
- **Product wording**: sentences such as "this OneMind" or "Welcome to OneMind" in the UI text still name the product in prose. Headers, titles and logos come from `brand.json`; a rename would also need a copy pass over the prose.
- **Design docs**: `docs/design/PRINCIPLES.md` and `docs/design/TOKENS.md` still say the accent is teal and red is only for status. The red default accent is the founder's decision (2026-11-12); those docs need a founder-approved update (see "Open questions").

## Testing still to do (not run in this change)
- Look at the UI, dashboard and site in a browser, light and dark: the logo, favicon (both themes), the red accent next to the red "danger"/"bad" status colours.
- Dashboard: the manifest is served as `application/manifest+json` by the gateway (`core/`), and the web app installs with the right icon.
- `scripts/brand-icons.py` in CI (`brand` workflow) and the artifact's icons on a real phone home screen (iOS mask, Android adaptive mask).
- OS: Plymouth theme and GRUB colours on the VM board (above).
- Mobile and desktop, once wired.

## Open questions for the founder
- **Red accent vs. red status.** The UI rule (PRINCIPLES P3) kept red for errors and danger. The UI accent is now `#d11826` and the danger colour is `#b42318`, close in hue. Status pills always carry a text label, so meaning does not depend on colour alone, but a "Delete" button and a primary button will look alike. Options: keep it, use a darker or more orange danger red, or keep red only for the logo and pick another accent default.

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
