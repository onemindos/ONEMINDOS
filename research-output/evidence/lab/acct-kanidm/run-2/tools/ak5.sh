#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# AK-5 credential-reset link: one use only.
set -euo pipefail; T=AK-5; . /root/aklab/lib.sh
stamp "AK-5: credential-reset link"
run "admin_relogin"
run "reset_token child1 child1.reset2"
note "child1 already has a passkey from AK-3; the new credential is a password + TOTP"
run "\$PY enrol child1 child1.reset2 password+totp"
run "\$PY signin child1 passwordmfa"
note "second use of the same link"
run "\$PY reuse-intent child1.reset2"
