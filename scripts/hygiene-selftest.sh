#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# D-B1.3 self-test: plant a fake private key and a fake home path in a throwaway repo, and prove
# that the hygiene gate catches both. The planted values are generated at run time, so this
# file itself contains neither.
set -eu
ROOT=$(git rev-parse --show-toplevel)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/scripts"; cp "$ROOT/scripts/hygiene.py" "$ROOT/scripts/hygiene-allow.tsv" "$T/scripts/"
cd "$T"; git init -q; git -c user.name=t -c user.email=t@t.invalid commit -q --allow-empty -m base; git branch -q base
ssh-keygen -q -t ed25519 -N "" -C planted -f planted_key >/dev/null
printf 'see %s for the build output\n' "$(printf '/%s/%s/build' Users x)" > notes.md
git add -A; git -c user.name=t -c user.email=t@t.invalid commit -q -m planted
fail=0
if gitleaks git --no-banner --redact --log-opts="base..HEAD" . >/dev/null 2>&1; then echo "SELFTEST FAIL: gitleaks missed the planted key"; fail=1; else echo "selftest: gitleaks caught the planted key"; fi
if python3 -I scripts/hygiene.py --base base --root . >/dev/null; then echo "SELFTEST FAIL: greps missed the planted path"; fail=1; else echo "selftest: greps caught the planted home path"; fi
exit $fail
