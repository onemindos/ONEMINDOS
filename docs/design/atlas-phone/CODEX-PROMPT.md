<!-- SPDX-License-Identifier: Apache-2.0 -->
# Prompt for Codex: build the phone app's agreed design

Paste everything below the line into Codex, run from a clone of `onemindos/ONEMINDOS`.

---

You are building the OneMind OS phone app (`mobile/`, Expo / React Native) to match the design the founder picked on 2026-11-21. The desktop dashboard already uses it; the phone does not. Work through three issues **in order**, one branch and one PR each:

1. **#1225 `phone-atlas-home`**: red buttons, the Contour background, the tab bar (Home, Approvals, Apps, Me) and the Home screen (render `13a`). Do this first; the other two depend on it.
2. **#1226 `phone-atlas-approvals`**: Approvals with hold to approve (render `13d`).
3. **#1227 `phone-atlas-app-page`**: the app page with the install-waiting state (render `13c`).

## Read first, in this order
1. `CLAUDE.md` and `docs/leap/AGENT-QUEUE.md` (claiming, definition of done, sign-off).
2. `docs/design/atlas-phone/README.md` and the renders next to it (`13a`, `13c`, `13d`, light and dark). If that folder is not on `release/next` yet, read it from branch `docs/atlas-phone-design`.
3. The issue you are on: `gh issue view <n> -R onemindos/ONEMINDOS`.
4. `mobile/README.md`, `mobile/src/ui/theme.ts`, `mobile/src/ui/bits.tsx`, `mobile/src/nav.ts`, `mobile/src/screens/`.

## How to work
- **Claim:** comment `claim: codex, branch feat/<key>` on the issue and add the `claimed` label.
- **Branch from `origin/release/next`** (not `main`): `git fetch origin release/next && git switch -c feat/phone-atlas-home origin/release/next`.
- **Once per clone:** `make -C sdk gen-code`, then `cd mobile && npm ci`.
- **Colours come only from the tokens** in `mobile/src/ui/theme.ts` (generated from `ui/src/tokens/tokens.ts`). Primary buttons use `action` (red); `accent` (teal) is for selection, focus, the active tab and toggles. Never type a raw hex value in a screen.
- **Real data only.** Every value comes from the hub through `@onemind/sdk`. The renders' people and places ("Rivera home", Maya, Hermes, the greenhouse) are made up: copy the layout, never the data. If the hub has no data for a card, hide the card. Test fixtures stay inside tests.
- **Approvals are safety-critical.** An action with `risk` `actuate` or `destructive` can only be approved by a completed 2-second hold followed by the existing passkey / approval-key signing. No one-tap, swipe or notification approve for those, ever. Deny is always one tap. Do not change the signing code (`mobile/src/approvalKey/`, gateway verifiers): change screens only.
- **Keep every existing screen reachable.** Activity and More move under the Me tab with Settings. Do not add an empty Map tab: #656 adds Map later.
- **Accessibility:** status by shape and word, never colour alone; 44 px minimum touch targets; nothing under 12 px; honour reduce motion; every live value shows its age.
- **Smallest change that meets the issue's Spec list**, under about 600 changed lines. Tests for new behaviour in the same PR.

## Before you open the PR (all must pass)
```bash
cd mobile && npm ci && npm run typecheck && npx jest --ci && cd ..
make lint
python3 -I scripts/changes.py check
make hygiene
```
- Add one change fragment `changes/<branch-with-dashes>.md` (see `changes/README.md`, `pr: pending`). Never edit `CHANGELOG.md` or `docs/leap/STATUS.md`.
- Every commit `git commit -s`.
- **Screenshots:** run the app on an Android emulator (or ask the founder to run it on his Samsung) in light and dark, and attach them to the PR beside the matching render. A release APK needs the crash fix on branch `fix/android-workmanager-r8`; a debug build (`npx expo run:android`) works without it.
- Open the PR against `release/next` with `.github/pull_request_template.md` (Why / What / Tests / Not done), `Refs #<n>` (never "Closes"), labels `builder:codex` and `needs-review`. The Opus gate reviews and merges; do not merge yourself.

## Stop and ask instead of building around it
- The issue seems to need a new gateway route or a change in `core/`.
- A design rule conflicts with a founder decision in `docs/DECISIONS.md` or with "AI never actuates without human approval".
- The hub cannot supply data a card needs (say which card and which route is missing in the PR's "Not done").

When an issue's PR is open, go to the next issue in the list. Then stop and report: each PR link, what is done, what is not, and the screenshots.
