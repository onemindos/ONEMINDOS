#!/bin/bash
# AK-8c: does the passkey-minimum policy stop a person in the group from ENROLLING password + TOTP in the first place?
set -euo pipefail; T=AK-8; . /root/aklab/lib.sh
stamp "AK-8c: with credential-type-minimum = passkey, can a member of onemind_adults enrol password + TOTP?"
run "admin_relogin"
run "k person create adult3 'Adult Three'"
run "k group add-members onemind_adults adult3"
run "reset_token adult3 adult3.reset"
run "\$PY enrol adult3 adult3.reset password+totp"
run "reset_token adult3 adult3.reset2"
run "\$PY enrol adult3 adult3.reset2 passkey"
