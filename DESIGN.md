<!-- SPDX-License-Identifier: Apache-2.0 -->
# Atlas appearance

Home opens with the Contour wallpaper. Keep status and outstanding approvals ahead of the app grid. A map opens in a desktop window using the same navigation and focus rules as other apps. [Atlas design issue #757](https://github.com/onemindos/ONEMINDOS/issues/757)

| Role | Light | Dark |
| --- | --- | --- |
| Stone desktop background | `#fafaf9` | `#151311` |
| Stone window surface | `#ffffff` | `#191715` |
| Selection, links and keyboard focus | `#1f6a66` | `#6db8b0` |
| Primary action | `#d11826` | `#fb605a` |

Settings → Appearance offers ten theme packs. The Atlas collection includes Atlas Night, Atlas Day, Night Watch, Greenhouse and Harbor. The Console collection includes Console Default, Console Light, Field, Village and Mono. Each pack sets light or dark mode, wallpaper, tint, corners and transparency. Atlas Night and Atlas Day use Contour. Mono uses a solid background. All ten keep selection teal and primary actions red. Saved personal accents, including the former OneMind Red default, tint wallpaper artwork. The interactive colours stay the same when someone changes the tint or restores an older preference. Existing wallpaper choices are preserved. Keep action and danger labels explicit, including on the approval screen. Forced colours follow the device's accessibility palette.

Use the shared Inter type scale for labels and body text and monospace for identifiers. Windows start at a 24 px radius on the desktop. App tiles use a 26% radius. Display the icon distributed in the reviewed app manifest when its licence permits. A missing or unusable icon gets neutral initials. The logo uses the original paths, view box and theme colours at every size.

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
