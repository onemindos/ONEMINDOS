<!-- SPDX-License-Identifier: Apache-2.0 -->
# Browser tests for `ui/` and the dashboard

> **Explain it like I am the founder**
> The unit tests in `ui/` and `dashboard/` run in jsdom, a pretend browser that cannot draw anything. That is why it cannot measure colour contrast or notice that a page looks wrong. These tests open the real pages in three real browser engines: Chromium (Chrome, Edge), Firefox and WebKit (Safari, and every browser on an iPhone). On every screen they run axe-core, an automatic accessibility checker. They also click through sign-in and the main menu, and compare screenshots with approved pictures.

What runs (CI: [`.github/workflows/ui-quality.yml`](../../.github/workflows/ui-quality.yml); what each job proves: [`docs/testing/CI-MATRIX.md`](../../docs/testing/CI-MATRIX.md)):

| File | Checks |
|---|---|
| `e2e/screens.ts` | The list of every screen: 67 `ui/` demo routes and 6 dashboard pages. **A new screen gets a line here.** |
| `e2e/a11y.spec.ts` | axe-core on every screen, light and dark, at 1280 px and 375 px. Any **serious** or **critical** finding fails, and so does an uncaught exception or a `console.error`. The full axe result is attached to the report, so moderate and minor findings stay visible. |
| `e2e/known-a11y.ts` | The defects the first run found in `ui/` (A11Y-1 to A11Y-5, [CI-MATRIX §1.4](../../docs/testing/CI-MATRIX.md)). The list is a ratchet: a finding that is not on it fails, and a listed one that no longer reproduces fails too, so **the PR that fixes one deletes its entry**. |
| `e2e/flows.spec.ts` | Dashboard: a bad token is refused, `owner-demo` signs in, the menu reaches Nodes, Market, Approvals and Home, then sign-out. Demo: every main menu entry opens its screen. The WK-1 ratchet. |
| `e2e/visual.spec.ts` | 29 screenshots per engine (24 in WebKit, see WK-1 below) compared with `visual/<browser>/*.png`. More than 0.1 % of pixels different fails. Desktop shots stretch the viewport to the page's height, so fixed layers (wallpaper, Home dock) sit where a person sees them. |

The clock is fixed at 2026-11-12 15:05 UTC, so every "5 min ago" renders the same way each run. Animations are off.

**WebKit and WK-1:** WebKit on the Linux runner stops producing frames on Home, Appearance and the App Store (CI-MATRIX §1.5). axe still runs there. Those 5 screenshots are skipped in WebKit only, and the menu flow starts on Activity. `flows.spec.ts` "WK-1 ratchet" is expected to fail in WebKit; once it passes there, delete its `test.fail` line and the skips.

## Run locally

Playwright needs browsers that are not installed on our Macs (founder rule: no installs on the host). Run it in CI, or in a disposable Linux VM:

```sh
(cd ui && npm ci && npm run build:demo)
(cd dashboard && npm ci && npm run build:mock)
cd ui/test && npm ci
npx playwright install --with-deps chromium     # inside the VM only
npx playwright test --project=chromium          # or: --grep @visual, --grep "a11y desktop"
npx playwright show-report
```

The baseline is drawn on GitHub's `ubuntu-24.04` runner. Screenshots from another OS differ in fonts and anti-aliasing, so do not commit local snapshots: use the CI flow below.

## Visual baseline: how to accept a change

A screenshot difference fails the PR. The `playwright-report-<browser>` artifact shows expected, actual and diff for each failing image.

1. **The change is a bug:** fix the code and push again.
2. **The change is intended:** make CI draw the new baseline, then commit it.
   1. GitHub: **Actions → ui-quality → Run workflow**, choose your branch, tick `update_baseline`. Terminal: `gh workflow run ui-quality.yml --ref <branch> -f update_baseline=true`.
   2. The run uploads `visual-baseline-chromium`, `-firefox` and `-webkit`, holding only engines whose pictures changed. It never commits anything.
   3. On your branch: `ui/test/accept-visual.sh <run-id>`. This downloads the artifacts into `ui/test/visual/<browser>/` and shows `git status`.
   4. Look at the images. Commit them as `ui: accept visual baseline (<why>)` and push. The PR shows each changed PNG as an image diff; **approving the PR approves the new baseline.**

A new screen in `e2e/visual.spec.ts` has no baseline yet. Its first run fails with "A snapshot doesn't exist" and uploads `visual-baseline-<browser>` artifacts automatically, so step 2.3 works on that run too.

## Dependencies

Pinned exactly in `package.json`: `@playwright/test` 1.64.1 and `playwright-core` 1.64.1 (Apache-2.0), `@axe-core/playwright` 4.14.0 with `axe-core` 4.14.0 (MPL-2.0; test-only, never shipped; `ui/` and `dashboard/` already use the same axe-core version), TypeScript 5.9.3 (Apache-2.0) and `@types/node` (MIT). CI runs `scripts/npm-licence-check.py ui/test --allow Apache-2.0 MIT MPL-2.0`. This is a separate npm project, so Playwright never becomes a dependency of `@onemind/ui`.
