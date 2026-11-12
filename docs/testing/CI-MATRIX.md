<!-- SPDX-License-Identifier: Apache-2.0 -->
# CI test matrix: what each job proves

> **Explain it like I am the founder**
> A green check in GitHub only means something if you know what the job actually did. This page lists the test jobs added on 2026-11-12. For each one it says where it runs, what a pass proves, and what it does **not** prove. Jobs that already existed (`ci`, `ci-core`, `ci-ui`, `ci-dashboard`, `ci-apps`, `apps-rescan`, `battery`, ...) are described in their own files. The test register and the `test-all` workflow are being built on branch `test/register`. They list every test we still owe and run all workflows at once; this matrix adds the jobs that some of those register rows ask for.

| Workflow | Job | Runner | When | A pass proves | Register rows |
|---|---|---|---|---|---|
| [`ui-quality.yml`](../../.github/workflows/ui-quality.yml) | `build` | ubuntu-24.04 | PR or push touching `ui/`, `dashboard/` | The `ui/` demo and the dashboard mock build; the browser-test dependencies are exact pins with allowed licences; the tests typecheck | – |
| | `chromium`, `firefox`, `webkit` | ubuntu-24.04 | same | In each engine: no new serious/critical axe finding on any of 73 screens (light + dark, 1280 + 375 px); no uncaught exception or `console.error`; sign-in and menus work; 29 screenshots (WebKit: 24, §1.5) match the approved baseline | TR-181, TR-183 |
| [`apps-gate-all.yml`](../../.github/workflows/apps-gate-all.yml) | `gate` (app × arch) | ubuntu-24.04 **and** ubuntu-24.04-arm | Mondays 05:23 UTC, manual | Every app in `apps/` passes `app-gate --smoke` on each CPU architecture: licence, pinning and archs, Trivy, ClamAV, cosign, non-root, and the app **starts** (and answers HTTP, if it has a web UI) on a k3s cluster running natively on amd64 and on arm64 | TR-081, TR-088 |
| | `report`, `issue` | ubuntu-24.04 | after the gates | The run summary has one table of app × architecture; on full runs one issue lists every failing cell, or is closed when all pass | – |
| | self-test | both | PR touching the workflow or `sdk/tools/ci/` | The workflow itself works end to end on one canary app (`ntfy`) on both architectures; the issue is not touched | – |
| [`ci-mobile.yml`](../../.github/workflows/ci-mobile.yml) | `test` | ubuntu-24.04 | PR or push touching `mobile/` | `tsc` is clean and the 37 jest tests pass | TR-206 |
| | `android` | ubuntu-24.04 | same | `expo prebuild` + Gradle produce a debug APK; the APK requests none of the permissions `app.json` blocks | TR-201 (build only) |
| | `ios` | macos-26 | same | `expo prebuild` + CocoaPods + `xcodebuild` produce an iOS-simulator Release app with the JS bundle embedded | TR-200 (simulator only) |
| [`site.yml`](../../.github/workflows/site.yml) | `build` (new last step) | ubuntu-24.04 | PR or push touching `site/`, `apps/` | Every internal link and `#fragment` in the built site resolves, and every link into this repository names a file that exists | TR-241 (links only) |

All of them follow the same rules: workflow `permissions: {}`, each job asks only for what it needs (`contents: read`; `issues: write` only on the `issue` job, which has no checkout and runs no app code), and checkout never keeps the token (`persist-credentials: false`). Every action is pinned by commit from [`os/versions.lock.yaml`](../../os/versions.lock.yaml) (checked by `test/unit/test_versions_lock.py`). No job uses a secret.

## 1. `ui-quality`: real browsers, accessibility, visual regression

The unit tests in `ui/` and `dashboard/` run in jsdom, which has no layout or paint, so it cannot measure contrast or see a broken page. This workflow opens the built pages in Chromium (Chrome, Edge), Firefox and WebKit (Safari, and every browser on an iPhone) with Playwright. Test code and its README: [`ui/test/`](../../ui/test/README.md).

### 1.1 What runs per engine

| Check | Scope | Fails when |
|---|---|---|
| axe-core 4.14 (all default rules: WCAG 2.0, 2.1 and 2.2 A/AA plus best practices) | 67 `ui/` demo routes in light and dark, 6 dashboard pages in light (it has no dark theme yet), each at 1280 px and 375 px: 280 page visits | a **serious** or **critical** finding that is not a listed known finding (§1.4), or a listed one that no longer reproduces |
| Console and exceptions | the same 280 visits | any uncaught exception or `console.error` |
| Flows | dashboard: bad token refused, `owner-demo` signs in, menu to Nodes, Market, Approvals, Home, sign out; demo: each main menu entry opens its screen with `aria-current` | a step does not happen |
| Visual | 29 screenshots: 22 whole pages at 1280 px light, 3 dark, 4 phone (390 px); WebKit skips the 5 of Home, Appearance and the App Store (§1.5) | more than 0.1 % of pixels differ from `ui/test/visual/<engine>/` |

Determinism: the clock is fixed at 2026-11-12 15:05 UTC, motion is reduced, animations and the caret are off, and time zone and locale are fixed (UTC, en-US). Each engine has its own baseline, drawn on the same runner image, because fonts and anti-aliasing differ between engines. A desktop shot stretches the viewport to the page's height and then captures it. A plain full-page capture draws `position: fixed` layers (the wallpaper, the Home dock, the dashboard background) only within the first 860 px, which put the dock in the middle of the picture. The baseline is about 9 MB per engine (unquantised PNGs). Accepting one changed screen rewrites only its file.

Moderate and minor axe findings do not fail. They stay visible in the report (`axe-results.json` is attached to every visit).

### 1.2 Reading a failure

Download `playwright-report-<browser>` from the run and open `playwright-report/index.html`. A failing visit shows the axe rule, the help link and the element. A failing screenshot shows expected, actual and diff. The trace is a step-by-step recording of the page.

### 1.3 Accepting a visual change

A difference fails the PR on purpose; someone has to look at it. If the change is intended:

1. Actions → ui-quality → Run workflow on your branch with `update_baseline` ticked (`gh workflow run ui-quality.yml --ref <branch> -f update_baseline=true`). The run rewrites the snapshots and uploads `visual-baseline-<browser>` artifacts. It never commits.
2. `ui/test/accept-visual.sh <run-id>` copies them into `ui/test/visual/<browser>/`.
3. Commit, push. The PR shows each changed PNG as an image diff; **approving the PR approves the baseline**.

A new screenshot has no baseline yet. Its first PR run fails and uploads the candidate automatically, so step 2 works on that run too.

### 1.4 Known findings (defects in `ui/`, for the ui stream to fix)

The first run on 2026-11-12 found five accessibility defects in `ui/`. Chromium and Firefox reported the same five. The ui stream owns `ui/**` ([WORKSTREAMS](../leap/WORKSTREAMS.md)), so this PR does not fix them. It lists them in [`ui/test/e2e/known-a11y.ts`](../../ui/test/e2e/known-a11y.ts) instead, and that list works as a ratchet: anything **new** still fails. A listed finding that stops reproducing also fails, so its entry is deleted in the PR that fixes it.

| Id | axe rule (impact) | Where | Screens | Suggested fix |
|---|---|---|---|---|
| A11Y-1 | `button-name` (critical) | `PaletteTrigger`, `ui/src/shell/CommandPalette.tsx`; `shell.css` hides its text below the compact breakpoint | palette demo, 375 px | `aria-label={label}` on the button |
| A11Y-2 | `label-content-name-mismatch` (serious, WCAG 2.5.3) | palette close button shows "esc" but is named "Close" | palette demo, both widths | name it "Close (esc)", or drop `aria-label` and add visually hidden "Close" |
| A11Y-3 | `color-contrast` (serious) | `StateView` offline dimming, `.oms-dimmed-more` (`opacity: 0.75` + grayscale) in `ui/src/shell/shell.css` | shell states demo, light theme | dim with a token colour that keeps 4.5:1 instead of opacity |
| A11Y-4 | `scrollable-region-focusable` (serious) | App Store screenshot strip `.om-store-shots-list`, `ui/src/store/AppDetail.tsx` | App Store app page | `tabIndex={0}`, `role="region"` and an `aria-label` on the scrolling list |
| A11Y-5 | `scrollable-region-focusable` (serious) | `Table` wrapper `.om-table-wrap`, `ui/src/components/Table.tsx` | Updates history at 375 px | same as A11Y-4 on the wrapper (named by the caption) |

### 1.5 WK-1: WebKit stops producing frames on three screens (open)

Seen on runs 1 and 2 of this PR, on GitHub's `ubuntu-24.04` runner with Playwright 1.64.1's WebKit. On the demo's **Home**, **Appearance** and **App Store** screens, WebKit stops producing rendering updates soon after the page loads:

- the first screenshot capture never completes (the Playwright log stops at "waiting 100ms before taking screenshot"), so the screenshot fails after 5 s;
- a click on the Home menu waits 60 s in Playwright's actionability check without a single retry, because the in-page check runs on animation frames.

Chromium and Firefox render the same pages normally, and axe passes on them in WebKit too (it needs no frames). **Ruled out:** blur. Run 2 switched off every `filter` and `backdrop-filter` in WebKit and the stall stayed. **Not yet ruled out:** the features these three screens use and the others do not: `mask-image` on a scrolling chip row (Home), `conic-gradient` with `color-mix()` (Appearance and App Store), and the App Store's tall page.

Until it is understood, WebKit skips those 5 screenshots, and the menu flow starts on Activity, so it never clicks on Home. `e2e/flows.spec.ts` "WK-1 ratchet" clicks on Home with `test.fail` in WebKit only. When the stall goes away, that test turns red ("expected to fail, but passed"), and the fix removes the marker and the skips.

**Is it a Safari bug?** UNVERIFIED. Headless WebKit on Linux paints differently from Safari on a Mac or iPhone. Next steps: open Home in Safari with Web Inspector's Timelines recording (the founder's Safari check, TR-183), and bisect the three CSS features above with Playwright's WebKit in a disposable Linux VM.

## 2. `apps-gate-all`: every app, both architectures, every week

`ci-apps` gates only the apps a PR changes, and only on amd64. `apps-rescan` rescans every app daily on amd64 and turns new scan results into a PR. Neither shows that an app **runs on arm64**, the CPU of a Raspberry Pi 5 and a Jetson. A multi-arch image index can list `linux/arm64` while that image still crashes on start.

`apps-gate-all` runs [`sdk/tools/app-gate`](../../sdk/tools/app-gate) `--smoke --tier check --no-write` for every app on `ubuntu-24.04` (amd64) and `ubuntu-24.04-arm` (arm64). Each job gets its own k3d cluster with the same k3s pin as the OS image. The gate's tools are installed for the runner's architecture, each pinned by sha256 for amd64 and arm64 ([`sdk/tools/ci/install-tools.sh`](../../sdk/tools/ci/install-tools.sh), same values in `os/versions.lock.yaml`, kept equal by `sdk/tools/tests/test_ci_tools.py`).

- **A pass proves** (per app and architecture) what contract §9.4 checks 2–9 prove: licence class, tag+digest pin with the declared archs, no fixable CRITICAL CVE, no secret, no ClamAV hit, cosign where upstream signs, non-root or dropped capabilities. On top of that, the app's pods became Ready **on that CPU** and, for an app with a web UI (`spec.web`), its port answered 200/3xx.
- **Same signatures everywhere:** ClamAV signatures are downloaded once per run and shared by every job, so two cells never disagree because of a signature update.
- **Read-only:** the jobs never write `scan.json`, tiers or READMEs (`--no-write`). `apps-rescan` stays the only writer.
- **One issue:** the `report` job writes a table of app × architecture (pass, FAIL with the failing checks, ERROR for a tool or setup failure, NO RESULT for a job that did not finish) into the issue "App gate on every app (amd64 + arm64): failures". It opens the issue, rewrites it on later runs, and closes it when everything passes. IP addresses and colour codes are removed from the text ([`sdk/tools/ci/gate_summary.py`](../../sdk/tools/ci/gate_summary.py)). The `issue` job, the only one with `issues: write`, posts it. A manual run limited to some apps (`apps` input) only writes the run summary and does not touch the issue.
- **Self-test on pull requests:** a PR that changes the workflow or `sdk/tools/ci/` runs it on one canary app (`ntfy`, verified, with a web UI) on both architectures. This exists because GitHub can only start a manual run of a workflow that is already on `main`, so a workflow change would otherwise go untested until after it merges.
- **Not proven:** that the app works on a real Pi 5 or Jetson (kernel, storage, USB). A GitHub arm64 runner is a cloud server, not a board.

## 3. `ci-mobile`: unit tests and both native builds

Until now, `mobile/` was built only on a developer Mac.

- `test`: `tsc --noEmit` and `jest --ci`.
- `android`: React Native's own version catalog (`node_modules/react-native/gradle/libs.versions.toml`) names the NDK. The job installs that NDK and CMake 3.22.1, runs `expo prebuild`, then `./gradlew assembleDebug` with JDK 17. `aapt2` then checks the APK: none of the permissions `app.json` blocks may be requested. The one exception is `SYSTEM_ALERT_WINDOW`, which React Native's debug manifest adds for the developer menu ([`mobile/README.md`](../../mobile/README.md), Security notes). The APK is kept for 14 days as `onemind-mobile-debug-apk`, for sideloading (TR-202).
- `ios`: `expo prebuild`, `pod install`, then `xcodebuild` Release for the iOS simulator on `macos-26`, unsigned. The job checks that `main.jsbundle` is inside the app, which proves Metro bundling too.
- **Not proven:** that the app launches. An emulator smoke flow (TR-201) and a real device (TR-200, TR-202) are still open. Signing and store builds need founder accounts.

## 4. `site`: offline link check

[`scripts/check-links.py`](../../scripts/check-links.py) (standard-library Python) reads every page in `site/dist` after the build:

- Every relative and root-relative `href`, `src`, `srcset` and `poster` must point to a file or a directory `index.html` in the build. A `#fragment` must match an `id` on the target page.
- Every link into this repository (`github.com/onemindos/ONEMINDOS/{blob,tree,edit,raw}/main/<path>`, including Starlight's "Edit page" links) must name a path that exists in the checkout. A moved doc therefore fails the build instead of leaving a dead link.
- Other external links are counted but not fetched, so the check never flakes on someone else's server.

First run (2026-11-12, local build): 28 pages, 1,252 links, 0 broken, 43 repository links checked. Still open from TR-241 / CORE-WEB-1: axe over the built site, and deployment (founder decision F-5).

## 5. Running them

| Workflow | Manual run |
|---|---|
| ui-quality | `gh workflow run ui-quality.yml --ref <branch>` (add `-f update_baseline=true` to redraw the baseline) |
| apps-gate-all | `gh workflow run apps-gate-all.yml` (all apps; updates the issue) or `-f apps="ntfy mosquitto"` (some apps; summary only) |
| ci-mobile | `gh workflow run ci-mobile.yml --ref <branch>` |
| site | runs on PRs; its manual trigger is added on `test/register` |

All three new workflows have `workflow_dispatch`, so `test-all` (branch `test/register`) can add them. `ci-mobile` and `ui-quality` belong in its light list, `apps-gate-all` in its heavy list.

## 6. Still not covered

| Gap | Register row or backlog | Why not here |
|---|---|---|
| Customization persists across reload (themes, accents, wallpapers, density) | TR-184 | Needs settled expected behaviour per setting first; the suite's flows file is the place for it |
| axe over the built website | TR-241, CORE-WEB-1 | Starlight's own markup would need its own known-findings review |
| Android emulator launch (Maestro or Detox) | TR-201 | Needs a KVM emulator job and a smoke flow; the APK from `ci-mobile` is its input |
| Home performance budget (initial JS over 200 KB gzip fails) | UMB-DESK-16 | Separate gate; ui-quality covers its axe half |
| Dashboard dark theme | CORE-DASH-1 | The dashboard has no dark theme yet; it will be added to `a11y.spec.ts` when it exists |
| WebKit on Home, Appearance and App Store | WK-1 (§1.5) | WebKit stops producing frames there; its root cause is open |
