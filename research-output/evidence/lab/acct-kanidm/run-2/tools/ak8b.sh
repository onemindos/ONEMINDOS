#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# AK-8b: the mitigation run-1 left UNVERIFIED: require passkeys for a household group through Kanidm's account policy,
# so that a person in it cannot sign in with password + TOTP (and TOTP replay no longer matters for them).
set -euo pipefail; T=AK-8; . /root/aklab/lib.sh
stamp "AK-8b: credential-type-minimum = passkey on onemind_adults (adult2 only has password + TOTP)"
run "admin_relogin"
run "k group account-policy enable onemind_adults"
run "k group account-policy credential-type-minimum onemind_adults passkey"
run "k group get onemind_adults | grep -iE 'name|member|credential|policy' "
run "\$PY signin adult2 passwordmfa refused"
note "control: adult1 (passkey) was removed from the group in AK-10; child1 (other group, password+TOTP) is not affected by this policy"
run "\$PY signin child1 passwordmfa"
