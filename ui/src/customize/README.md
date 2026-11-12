<!-- SPDX-License-Identifier: Apache-2.0 -->
# Customization engine (`ui/src/customize/`)

**Serves:** parity gap **PU-03** (appearance settings) in `docs/strategy/umbrel-parity.md`, the founder direction of 2026-11-12 ("the UI must look good and have customizations"), and PRINCIPLES P2 (honest state), P4 (headless first) and P5 (accessible). **Screens:** `docs/design/screens/customize/` (demo route `#/appearance/<state>`).

**Plain English.** Each person picks how OneMind looks: light, dark, automatic or scheduled theme; an accent colour; a wallpaper; density, text size, corner style, reduced motion and transparency. The choices are a small JSON document. The engine turns it into **overrides of the existing design tokens** (CSS custom properties), so every component changes without knowing about customization.

## Pieces
| File | What it does |
|---|---|
| `color.ts` | Hex parsing, WCAG 2.2 contrast, sRGB blending, OKLCH (OKLab, Ottosson 2020) lightness changes. Written for OneMind from the public formulas. |
| `accents.ts` | 8 curated accents and `deriveAccent()`: any colour → accent, hover, text-on-accent and soft background that pass AA in a theme. |
| `wallpapers.ts` | 12 wallpapers generated as CSS gradients and seeded inline SVG. Each declares its colours per theme and its accent. `minDim()` is the contrast guard. |
| `preferences.ts` | The `AppearancePreferences` document, `normalizePreferences()`, theme schedule, `customizeCss()` and `applyPreferences()`. |
| `store.ts` | `PreferencesStore` interface; `LocalPreferencesStore` (works today); `ApiPreferencesStore` (pending §12, below). |
| `upload.ts` | "Upload your own": type/size check, resize to 2560 px in the browser, colour sampling for the contrast guard. |
| `CustomizeProvider.tsx` | Loads (hub → local copy → defaults), applies, saves with a debounce, re-applies at the next scheduled switch. |
| `WallpaperLayer.tsx` | Fixed layer behind the app in both theme variants (CSS picks one, so theme switches need no JavaScript) with a dim veil. |
| `AppearanceSettings.tsx`, `controls.tsx` | The Settings → Appearance screen and its native-radio/range controls. |

## Contrast rules (tested in `engine.test.ts`)
- **Accents:** accent ≥ 4.5:1 on `bg`, `surface`, `surface-raised` and `accent-soft`; text-on-accent ≥ 4.5:1 on accent and hover, in both themes. The 8 presets pass without adjustment; the teal preset equals the shipped tokens. A custom colour keeps its hue and moves only OKLCH lightness until it passes; the screen shows the adjusted value and ratio.
- **Wallpapers:** for every wallpaper × every accent × both themes, `text`, `text-muted` and the accent reach 4.5:1 on every colour the wallpaper paints (its stops and their midpoints) once the dim veil is applied. `minDim()` finds the smallest dim (5 % steps) that does this; the applied dim is `max(chosen, minimum)` and the screen says when it was raised. Uploaded images use sampled colours, or 60 % when they cannot be sampled.
- Violet, red, amber and green are not offered as presets: they mean "agent" and the status tones (P3).

## Tokens added (all in `customize.css`)
| Token | Default | Set by |
|---|---|---|
| `--om-wallpaper-dim` | `0` | `customizeCss()` per theme (effective dim) |
| `--om-wallpaper-blur` | `0px` | `customizeCss()` |
| `--om-cz-glass-opacity` | `82%` | surface share of frosted surfaces |
| `--om-cz-glass-blur` | `18px` | backdrop blur of frosted surfaces |
| `--om-cz-ring` | 2 px surface + 2 px accent | selected wallpaper tile |

Overrides of existing tokens: `--om-color-accent`, `-accent-hover`, `-accent-text`, `-accent-soft` (per theme); `--om-radius-*` (corners); `--om-space-3…16` and `--om-layout-touch-target` (compact density; 36 px on fine pointers only, 44 px on touch); `--om-motion-duration-*` (reduced motion). Root attributes: `data-theme`, `data-om-density`, `data-om-corners`, `data-om-motion`, `data-om-wallpaper`, `data-om-glass`. Text size sets the root `font-size` (all sizes are `rem`).

## Proposed contract §12: per-person preferences (PENDING)
Not in `sdk/contracts/poc-v0.md` yet; `ApiPreferencesStore` implements this proposal and treats 404/405/501 as `pending_contract`.

| Method and path | Who | Body / returns |
|---|---|---|
| `GET /v1/me/preferences` | any **person** principal, own record only | `{"appearance": AppearancePreferences, "updated_at": "RFC3339"}`; defaults with `updated_at: null` if never saved |
| `PUT /v1/me/preferences` | the same person | body `{"appearance": …}` → the stored document. Validated like `normalizePreferences()` |
| `GET` / `PUT` / `DELETE /v1/me/wallpaper` | the same person | `{"data_url": "data:image/jpeg;base64,…"}`, ≤ 2560 px edge, size limit set by the gateway |

- Agents get **403**: appearance is personal and never an agent scope. It changes nothing on the box, so it is **not an action** and needs no approval (P1 concerns box state). It is still headless: the screen shows the exact `PUT` body; CLI verb `onemind me appearance set …` is planned.
- Until §12 ships, the provider uses `LocalPreferencesStore` and says "Saved on this browser"; with a hub store it falls back to the local copy and says "Not synced … copy saved on this browser N ago".

## Using it
```tsx
import { CustomizeProvider, WallpaperLayer, AppearanceSettings, LocalPreferencesStore } from '@onemind/ui';
const store = new LocalPreferencesStore();            // later: new ApiPreferencesStore({ token })
<CustomizeProvider store={store} cache={store}>        // mount once at the app root
  <WallpaperLayer />
  <AppShell …>{/* Settings → Appearance renders <AppearanceSettings /> */}</AppShell>
</CustomizeProvider>
```

## Provenance
Pattern studied, not copied: umbrelOS re-tints the UI accent from the wallpaper (`packages/ui/src/providers/wallpaper.tsx` @ `c43beed`, **PolyForm Noncommercial**: study only). No code, wallpaper, icon or text from umbrelOS or any other project is in this folder. Every wallpaper is generated by the code in `wallpapers.ts`; no image asset is shipped.
