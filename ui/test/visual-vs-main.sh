#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The visual check of CI (ui-quality.yml, CI-17) on your own machine: draw the screenshots from a base
# commit (default: where your branch left the branch PRs merge into, origin/release/next while it
# exists, else origin/main), then compare your working tree with them. Each step mirrors CI's, and
# e2e/visual-vs-main.spec.ts fails when the two drift (#883).
#   ui/test/visual-vs-main.sh [base-ref] [browser]      (defaults: that merge-base, chromium)
# Needs Playwright's browser installed (npx playwright install --with-deps <browser>; README.md: in a
# Linux VM, not on the Mac host). Base and working tree render on the same machine, so the comparison
# is fair anywhere; the pictures only look like CI's on Linux. Nothing is committed: the reference
# screenshots go to ui/test/visual/ (gitignored) and the report to ui/test/playwright-report-visual/.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
repo=$(git -C "$here" rev-parse --show-toplevel)
upstream=origin/main
if git -C "$repo" rev-parse --verify --quiet origin/release/next >/dev/null; then upstream=origin/release/next; fi
base=${1:-$(git -C "$repo" merge-base HEAD "$upstream")}
browser=${2:-chromium}
case "$browser" in chromium|firefox|webkit) ;; *) echo "unknown browser: $browser" >&2; exit 2 ;; esac
# As in CI: never re-use a server already on port 4173/4174, or one server could answer for both sides.
export CI=1 PW_GITHUB=0
tmp=$(mktemp -d)
cleanup() { git -C "$repo" worktree remove --force "$tmp/base" >/dev/null 2>&1 || true; rm -rf "$tmp"; }
trap cleanup EXIT

build() { # <tree>: the ui demo and the dashboard mock, as the CI build job does
  (cd "$1/ui" && npm ci --silent && npm run build:demo >/dev/null)
  # The dashboard imports the SDK schema, which is generated, not committed (CI-16). A fresh base worktree
  # has none, so without this its dashboard build fails and no dash-* screen gets a reference. Old bases
  # commit the schema and have no script, as CI allows.
  if [ -x "$1/sdk/scripts/gen-code.sh" ]; then "$1/sdk/scripts/gen-code.sh" ts; fi
  (cd "$1/dashboard" && npm ci --silent && npm run build:mock >/dev/null)
}

echo "base: $(git -C "$repo" rev-parse --short "$base")  browser: $browser"
git -C "$repo" worktree add --detach "$tmp/base" "$base" >/dev/null
build "$tmp/base"
build "$repo"
cd "$here"
npm ci --silent
rm -rf visual
UI_DIST="$tmp/base/ui/dist-demo" DASH_DIST="$tmp/base/dashboard/dist" PW_REPORT="$tmp/base-report" \
  PW_OUTPUT="$tmp/base-results" npx playwright test --project="$browser" --grep @visual --update-snapshots=all \
  || UI_DIST="$tmp/base/ui/dist-demo" DASH_DIST="$tmp/base/dashboard/dist" PW_REPORT="$tmp/base-report" \
    PW_OUTPUT="$tmp/base-results" npx playwright test --project="$browser" --grep @visual --update-snapshots=all --last-failed \
  || echo "some base screenshots could not be drawn; those screens will show as changed"
if PW_REPORT=playwright-report-visual PW_OUTPUT=test-results-visual \
  npx playwright test --project="$browser" --grep @visual --update-snapshots=none; then
  echo "no screen differs from $base"
else
  echo "screens differ from $base: npx playwright show-report playwright-report-visual"
  exit 1
fi
