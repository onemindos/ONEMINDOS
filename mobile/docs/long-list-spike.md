<!-- SPDX-License-Identifier: Apache-2.0 -->
# Long list spike (D-032): measure 10,000 rows on a phone

Screen: `src/spikes/LongListSpike.tsx`. Me tab, "Dev: long list spike". It only shows in a dev build, or in a build made with `EXPO_PUBLIC_ONEMIND_SPIKES=1`. Rows are generated on the phone and nothing is read from or written to the box.

## Run it on a Samsung S24 Ultra
1. Phone: Settings, About phone, Software information, tap Build number 7 times; then Developer options, USB debugging on. Plug in by USB and accept the prompt.
2. Build a **release** build (dev builds are much slower and would mislead): `cd mobile && npm ci && EXPO_PUBLIC_ONEMIND_SPIKES=1 npx expo run:android --variant release --device`.
3. Open the app, sign in as usual, Me tab, "Dev: long list spike".

## Measure (once per list engine)
Use a fixed run so the two numbers compare: pick the engine, then
```
adb shell dumpsys gfxinfo com.onemindos.mobile reset
```
Fling the list from top to bottom and back, 10 flings, no typing. Then:
```
adb shell dumpsys gfxinfo com.onemindos.mobile > gfx-flatlist.txt   # or gfx-flashlist.txt
```
Read these lines: `Total frames rendered`, `Janky frames` (count and %), `50th/90th/95th/99th percentile` (ms), `Number Missed Vsync`, `Number Slow UI thread`. At 120 Hz a frame has 8.3 ms; at 60 Hz 16.7 ms.
Then repeat with the search box: type "receipt 1" (reset first), and note how long the count line takes to update.

## Pass line (proposal, the founder may change it)
Janky frames under 5%, 95th percentile under 16 ms, search typing never blocks the keyboard.
