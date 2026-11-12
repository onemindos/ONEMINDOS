# Design tokens

**Serves:** backlog item 7 (UX-P1). **Source of truth:** [`ui/src/tokens/tokens.ts`](../../ui/src/tokens/tokens.ts). `npm run tokens` writes [`ui/src/tokens/tokens.css`](../../ui/src/tokens/tokens.css); a unit test fails if the two drift. The library build also writes `dist/tokens.json` for non-CSS consumers (the native mobile app).

**Plain English:** a *token* is a named design value, such as "the colour of muted text" or "the medium corner radius". Components use the names, never raw values, so changing a theme or fixing a contrast problem is a one-line change in one file.

## 1. Layers
Pattern from Home Assistant's frontend (`src/resources/theme/core.globals.ts` → `semantic.globals.ts`, Apache-2.0; structure only, no code copied):
1. **Palette** (`palette`): raw ramps: neutral (cool grey with a hint of teal), teal (brand accent), green, amber, red, blue, violet. Components never use these.
2. **Semantic roles** (`light`, `dark`): what a colour *means*. Every role exists in both themes.
3. **Scales** (`scale`, `shadow`): type, space, radius, elevation, motion, layout, z-index.

CSS custom properties are named `--om-<group>-<name>`, for example `--om-color-text-muted`, `--om-space-4`, `--om-radius-lg`.

## 2. Colour roles

| Role | Light | Dark | Use |
|---|---|---|---|
| `bg` | `#f7f9f9` | `#0c1214` | page background |
| `surface` | `#ffffff` | `#131a1d` | cards, sidebar |
| `surface-sunken` | `#f0f3f3` | `#0f1517` | wells, code, hover rows |
| `surface-raised` | `#ffffff` | `#1a2226` | dialogs, toasts, menus |
| `border` / `border-strong` | `#e3e8e9` / `#cdd5d7` | `#222b2f` / `#343f44` | dividers / control outlines |
| `text` | `#131a1d` | `#e8eeef` | body text |
| `text-muted` | `#475459` | `#a9b6b9` | secondary text, labels |
| `text-subtle` | `#5e6b70` | `#8a989c` | tertiary; still ≥ 4.5:1 on surface |
| `accent` / `accent-hover` | `#1f6a66` / `#1b5653` | `#6db8b0` / `#9fd2cc` | primary buttons, links, current nav |
| `accent-text` | `#ffffff` | `#0c1214` | text on accent |
| `accent-soft` | `#e8f4f3` | `#12302e` | current nav background |
| `focus` | `#2f5bea` | `#9bb5ff` | focus ring (blue, deliberately not the accent) |
| `danger` / `danger-text` | `#b42318` / `#ffffff` | `#ff9087` / `#0c1214` | destructive buttons |
| `overlay` | 48 % ink | 60 % black | dialog backdrop |

**Status tones**, each with `-fg`, `-bg` and `-border`:
| Tone | Meaning | Light fg | Dark fg |
|---|---|---|---|
| `ok` | healthy, done, verified, online | `#166236` | `#7ad69c` |
| `warn` | needs attention, waiting, stale | `#6b4500` | `#f2c661` |
| `bad` | failed, offline with impact, blocked | `#8f1c13` | `#ff9087` |
| `info` | in progress, system-initiated | `#2447b8` | `#9bb5ff` |
| `neutral` | off, unknown, expired, person | `#475459` | `#b5c0c3` |
| `agent` | anything an AI agent did or asked | `#47359c` | `#b9a9ff` |

`agent` has its own colour so a person can tell at a glance which requests came from an AI (P1). It is never used for anything else.

**Tested contrast** (`ui/src/tokens/tokens.test.ts`, both themes): text, muted and subtle text ≥ 4.5:1 on every surface; accent ≥ 4.5:1 on bg, surface and accent-soft; button text ≥ 4.5:1 on accent and danger; every tone's fg ≥ 4.5:1 on its own bg and on surface; focus ≥ 3:1 on bg and surface (WCAG 2.2 SC 1.4.3, 1.4.11, 2.4.13).

## 3. Type
System font stack (`--om-font-sans`) and system monospace (`--om-font-mono`): no web-font download, native on every OS, and no font licence to track.

| Token | Size | Use |
|---|---|---|
| `font-size-xs` | 12 px | pills, table headers, metadata |
| `font-size-sm` | 14 px | body in cards, buttons, nav |
| `font-size-md` | 16 px | default body |
| `font-size-lg` | 18 px | card titles, section headings |
| `font-size-xl` | 20 px | dialog titles |
| `font-size-2xl` | 24 px | stat values, page title on phones |
| `font-size-3xl` | 30 px | page title |
| `font-size-4xl` | 36 px | reserved (onboarding) |

Weights 400 / 500 / 600 / 700; line heights 1.25 (headings) and 1.5 (text). Sizes are in `rem`, so the browser's text-size setting scales everything.

## 4. Space, radius, elevation, layout
- **Space:** a 4 px grid: `0, 0-5 (2), 1 (4), 2 (8), 3 (12), 4 (16), 5 (20), 6 (24), 8 (32), 10 (40), 12 (48), 16 (64)`.
- **Radius:** `xs 4 · sm 6 · md 10 (buttons, inputs) · lg 14 (cards) · xl 20 (dialogs) · pill`.
- **Elevation:** `shadow-1` cards, `shadow-2` toasts and popovers, `shadow-3` dialogs and sheets. Dark mode uses darker, tighter shadows and relies on borders.
- **Layout:** content max 1200 px, sidebar 232 px, phone tab bar 64 px, touch target 44 px, compact breakpoint 720 px. z-index: nav 10, dialog 40, toast 50.

## 5. Motion
`duration-fast 120 ms` (hover, press), `duration-base 200 ms` (dialogs, toasts), `duration-slow 320 ms` (sheets); easing `ease-standard cubic-bezier(0.2, 0, 0, 1)` and `ease-exit cubic-bezier(0.3, 0, 1, 1)`. Under `prefers-reduced-motion: reduce` every duration is 0 ms and the pulse and spinner stop.

## 6. Themes
- No `data-theme` on `<html>`: follow the system (`prefers-color-scheme`).
- `data-theme="light"` / `"dark"`: forced by the person (`applyTheme()`; stored per browser).
- **Custom themes (phase 2):** a theme overrides only semantic roles. An Omarchy theme (`themes/<name>/colors.toml`: `background`, `foreground`, `accent`, `selection`, ANSI colours; MIT) maps onto `bg`, `text`, `accent` and the tones, so the desktop edition can follow the person's Omarchy theme. The contrast test must pass for any shipped theme.

## 7. Using tokens
- In CSS: `color: var(--om-color-text-muted); padding: var(--om-space-4);`
- In React Native: `import tokens from '@onemind/ui/tokens.json'` then `tokens.light['text-muted']`, `tokens.scale.space['4']` (px strings).
- Adding a token: edit `tokens.ts`, run `npm run tokens`, add a contrast assertion if it is a text or UI colour.
