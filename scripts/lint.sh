#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# make lint (D-B1.2): shellcheck on our shell, byte-compile our Python, SPDX headers on our files,
# no naive gate shipped (B5), no Ubuntu artifact uploaded (Z-01).
set -eu
cd "$(git rev-parse --show-toplevel)"
rc=0
OURS="os test scripts lab-kits .github Makefile"
sh_files=$(git ls-files -co --exclude-standard $OURS | while read -r f; do
  case "$f" in (*.sh) echo "$f";; (*) if head -c 40 "$f" 2>/dev/null | grep -qE "^#!/bin/(ba)?sh"; then echo "$f"; fi;; esac; done)
if command -v shellcheck >/dev/null; then
  echo "== shellcheck"; shellcheck -S warning -e SC1090,SC1091,SC2086,SC2046,SC2016,SC2155 $sh_files || rc=1
else echo "WARNING: shellcheck not installed (CI runs it)"; fi
echo "== python compile"
for f in $(git ls-files -co --exclude-standard $OURS | grep -E '\.py$'); do python3 -m py_compile "$f" || rc=1; done
echo "== SPDX headers (Apache-2.0) on OneMind files"
for f in $(git ls-files -co --exclude-standard $OURS | grep -vE '(\.keep|\.json|\.md|\.txt|\.ext|PREREGISTRATION\.sha256|etc/hostname|etc/hosts)$'); do
  head -n 5 "$f" | grep -q 'SPDX-License-Identifier: Apache-2.0' || { echo "missing SPDX header: $f"; rc=1; }
done
echo "== no naive gate outside test fixtures (B5)"
if git grep -n 'NAIVE' -- os/ | grep -v 'assemble.py'; then echo "naive gate code in os/"; rc=1; fi
echo "== no Ubuntu image is uploaded (Z-01)"
if grep -nE 'name: image-ubuntu|leg: ubuntu' .github/workflows/image.yml; then echo "Ubuntu artifact in image.yml"; rc=1; fi
[ $rc -eq 0 ] && echo "LINT: ok" || echo "LINT: FAILED"
exit $rc
