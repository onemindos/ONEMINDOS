<!-- SPDX-License-Identifier: Apache-2.0 -->
# Atlas appearance

Home opens with the Contour wallpaper. Keep status and outstanding approvals ahead of the app grid. A map opens in a desktop window using the same navigation and focus rules as other apps. [Atlas design issue #757](https://github.com/onemindos/ONEMINDOS/issues/757)

Colours are Sovereign's, from the founder's final design (picks of 2026-11-21): stone neutrals, one signal red for every button in both modes and in every pack, teal for the highlight.

| Role | Light | Dark |
| --- | --- | --- |
| Stone desktop background | `#e8e7e3` | `#0d0e10` |
| Stone window surface | `#fafaf8` | `#17181b` |
| Selection, links and keyboard focus (highlight) | `#1e6870` | `#5fc4cb` |
| Primary action (signal red, white text, 5.53:1) | `#cc1f2b` | `#cc1f2b` |
| Needs you (red as text) | `#b8141f` | `#ff6a6f` |
| Fresh / stale / offline | `#1a6e3e` / `#8a5100` / `#5e5f64` | `#5bc98a` / `#f2b45a` / `#a6a7ac` |
| Fault / plugin layer / simulated | `#a3420f` / `#6a4bc4` / `#44454a` | `#ff8a4c` / `#b9a2ff` / `#cdcdd0` |

The logo red `#ff333a` stays inside the logo files; as text it fails AA. Departures from Sovereign's own values, all for contrast: light fresh and stale are darkened to pass 4.5:1 on stone, and the dark sunken well is `#26272c` so it shows on the surface.

Settings → Appearance offers ten theme packs. The Atlas collection includes Atlas Night, Atlas Day, Night Watch, Greenhouse and Harbor. The Console collection includes OneMind, OneMind Light, Field, Village and Mono. Each pack sets light or dark mode, wallpaper, tint, corners and transparency. Atlas Night and Atlas Day use Contour; Night Watch and Field use Ember, Greenhouse Mycelium, Harbor Signal, OneMind and OneMind Light Dawn, Village Harvest and Mono Lattice. All ten keep selection teal and primary actions signal red.

Wallpapers come from Console's set, drawn in code (no image files): Contour (the default), Ripple, Signal, Dawn, Harvest, Mycelium, Lattice and Ember, each with a light and a dark side, plus your own photo. No pack opens on Ripple. The earlier OneMind wallpapers stay selectable after them. Saved personal accents, including the former OneMind Red default, tint wallpaper artwork. The interactive colours stay the same when someone changes the tint or restores an older preference. Existing wallpaper choices are preserved. Keep action and danger labels explicit, including on the approval screen. Forced colours follow the device's accessibility palette.

Use the shared Inter type scale for labels and body text and monospace for identifiers. Windows have a 14 px radius on the desktop, a 42 px title bar and a 38 px top strip. App tiles use a 26% radius. Display the icon distributed in the reviewed app manifest when its licence permits. A missing or unusable icon gets neutral initials. The logo uses the original paths, view box and theme colours at every size.

The optional Home command bar opens the existing palette. An owner with a reachable Hermes installation can open its chat through the hub's app proxy. A command that changes the box still uses its existing approval path.

## Motion and loading

| Token | Value and use |
| --- | --- |
| `--om-motion-duration-fast` | 120 ms for control feedback |
| `--om-motion-duration-base` | 200 ms for a window or menu transition |
| `--om-motion-duration-slow` | 320 ms for a larger surface transition |
| `--om-motion-ease-standard` | Standard entry and position changes |
| `--om-motion-ease-exit` | Dismissal |
| Button loader | 16 px ring, 2 px stroke, 800 ms linear revolution |

Follow reduced motion for transitions and use a static busy indicator alongside an accessible progress label. When content dimensions are known, reserve its space with a skeleton. Retain readable content during refresh. [Logo and loading guidance](docs/learning/atlas-logo-and-loading.md)
