#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# make hygiene: the push gate of brief 30 §2 rule 9. Blocks on any unreviewed hit.
#   1. gitleaks dir over every tracked/new file (a copy, so build outputs in out/ are not scanned)
#   2. gitleaks git over the commits not yet on the base branch
#   3. the hygiene greps (scripts/hygiene.py)
set -eu
BASE=${HYGIENE_BASE:-origin/main}
ROOT=$(git rev-parse --show-toplevel); cd "$ROOT"
command -v gitleaks >/dev/null || { echo "gitleaks not installed (need v8.30.1)"; exit 1; }
gitleaks version | grep -q '8.30.1' || echo "WARNING: gitleaks $(gitleaks version) is not the pinned 8.30.1"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
git ls-files -co --exclude-standard -z | tar --null -T - -cf - | tar -xf - -C "$T"
cp .gitleaksignore "$T/" 2>/dev/null || true
rc=0
echo "== gitleaks dir (tracked + new files)"; ( cd "$T" && gitleaks dir . --no-banner --redact ) || rc=1
if git rev-parse -q --verify "$BASE" >/dev/null; then
  echo "== gitleaks git $BASE..HEAD"; gitleaks git --no-banner --redact --log-opts="$BASE..HEAD" . || rc=1
fi
echo "== hygiene greps"; python3 -I scripts/hygiene.py --base "$BASE" --root "$ROOT" || rc=1
[ $rc -eq 0 ] && echo "HYGIENE: clean" || echo "HYGIENE: BLOCKED (fix, or record a reviewed false positive in handbook/hygiene.md + scripts/hygiene-allow.tsv)"
exit $rc
