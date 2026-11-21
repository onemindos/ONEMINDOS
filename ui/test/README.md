<!-- SPDX-License-Identifier: Apache-2.0 -->
# Browser tests for `ui/` and the dashboard

> **Explain it like I am the founder**
> The unit tests in `ui/` and `dashboard/` run in jsdom, a pretend browser that cannot draw anything. That is why it cannot measure colour contrast or notice that a page looks wrong. These tests open the real pages in three real browser engines: Chromium (Chrome, Edge), Firefox and WebKit (Safari, and every browser on an iPhone). On every screen they run axe-core, an automatic accessibility checker. They also click through sign-in and the main menu. On a pull request they take screenshots of the screens twice, once as `main` draws them and once with the PR's changes, and show a person every screen that looks different.

What runs (CI: [`.github/workflows/ui-quality.yml`](../../.github/workflows/ui-quality.yml); what each job proves: [`docs/testing/CI-MATRIX.md`](../../docs/testing/CI-MATRIX.md)):

| File | Checks |
|---|---|
| `e2e/screens.ts` | The list of every screen: 67 `ui/` demo routes and 6 dashboard pages. **A new screen gets a line here.** |
| `e2e/a11y.spec.ts` | axe-core on every screen, light and dark, at 1280 px and 375 px. Any **serious** or **critical** finding fails, and so does an uncaught exception or a `console.error`. The full axe result is attached to the report, so moderate and minor findings stay visible. |
| `e2e/known-a11y.ts` | The defects the first run found in `ui/` (A11Y-1 to A11Y-5, [CI-MATRIX §1.4](../../docs/testing/CI-MATRIX.md)). The list is a ratchet: a finding that is not on it fails, and a listed one that no longer reproduces fails too, so **the PR that fixes one deletes its entry**. |
| `e2e/flows.spec.ts` | Dashboard: a bad token is refused, `owner-demo` signs in, the menu reaches Nodes, Market, Approvals and Home, then sign-out. Demo: every main menu entry opens its screen. The WK-1 ratchet. |
| `e2e/visual.spec.ts` | 29 screenshots per engine (24 in WebKit, see WK-1 below). On a PR they are drawn from `main` first, then the PR is compared with them; more than 0.1 % of pixels different counts as a change (next section). Desktop shots stretch the viewport to the page's height, so fixed layers (wallpaper, Home dock) sit where a person sees them. |

The clock is fixed at 2026-11-12 15:05 UTC, so every "5 min ago" renders the same way each run. Animations are off.

**WebKit and WK-1:** WebKit on the Linux runner stops producing frames on Home, Appearance and the App Store (CI-MATRIX §1.5). axe still runs there. Those 5 screenshots are skipped in WebKit only, and the menu flow starts on Activity. `flows.spec.ts` "WK-1 ratchet" is expected to fail in WebKit; once it passes there, delete its `test.fail` line and the skips.

## Run locally

Playwright needs browsers that are not installed on our Macs (founder rule: no installs on the host). Run it in CI, or in a disposable Linux VM:

```sh
(cd ui && npm ci && npm run build:demo)
(cd dashboard && npm ci && npm run build:mock)
cd ui/test && npm ci
npx playwright install --with-deps chromium     # inside the VM only
npx playwright test --project=chromium --grep-invert @visual   # axe and flows
npx playwright show-report
```

**The visual check, locally:** `ui/test/visual-vs-main.sh [base-ref] [browser]` does what CI does. It builds the base (default: where your branch left `origin/main`) in a temporary git worktree, draws its screenshots into `ui/test/visual/` (gitignored), builds your working tree and compares it with them. Open the result with `npx playwright show-report playwright-report-visual`. Both sides render on the same machine, so the comparison is fair anywhere. On macOS the fonts differ from CI's, so the pictures only look like CI's on Linux.

## Visual changes: how a PR gets them accepted (CI-17)

**Why it works this way.** Screenshots used to be committed PNGs. Every dashboard PR that changed a shared screen carried new PNGs, so when one merged the others were out of date and PRs had to land one at a time. Now nothing is committed. Each PR is compared with `main`, drawn in the same CI job, on the same machine, with the same fonts, so only real UI changes show up.

How the `ui-quality` workflow decides, on every pull request:

1. The build job builds the ui demo and the mock dashboard twice: from the PR (GitHub's merge commit, the PR on top of `main`) and from its first parent, which is `main` as the PR merges into it. Another PR that merged meanwhile is part of both sides, so it never shows up as your change.
2. Each browser job runs axe and the flows exactly as before, then draws the 29 screenshots from the `main` build and compares the PR build with them.
3. The `visual` job collects the result. **No screen differs: it passes.** Screens differ: it fails and lists them in the run's summary page, unless the PR has the label **`visual:accepted`**.
4. The `playwright-report-<browser>` artifact holds the diffs: open `playwright-report-visual/index.html` for expected (main), actual (the PR) and diff of each changed screen.

**The reviewer (the gate) accepts a change:** look at the diffs; if the change is intended, add the label `visual:accepted` (`gh pr edit <pr> --add-label visual:accepted`). Adding or removing a label starts a cheap `visual-recheck` run: it waits for the newest full run of the same commit, requires its build, axe and flows to have passed, and decides again with the labels as they are now. It renders nothing. Then re-run `merge-gate` (`gh run rerun <gate-run-id>`), because the gate made its decision before the label existed. A new push renders everything again, and a label added before the newest commit no longer counts (it approved older screens): look at the new diffs, then remove the label and add it again. **The change is a bug:** fix the code and push again.

A new screen has no picture on `main`, so it always shows as changed in its first PR; accepting it works the same way. A push to `main` or a manual run has nothing to compare with: axe and flows only. No job in this workflow can write to the repository.

## Dependencies

Pinned exactly in `package.json`: `@playwright/test` 1.64.1 and `playwright-core` 1.64.1 (Apache-2.0), `@axe-core/playwright` 4.14.0 with `axe-core` 4.14.0 (MPL-2.0; test-only, never shipped; `ui/` and `dashboard/` already use the same axe-core version), TypeScript 5.9.3 (Apache-2.0) and `@types/node` (MIT). CI runs `scripts/npm-licence-check.py ui/test --allow Apache-2.0 MIT MPL-2.0`. This is a separate npm project, so Playwright never becomes a dependency of `@onemind/ui`.
