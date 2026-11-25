#!/bin/bash
# AK-3 household groups, AK-9 RSS sample after.
set -euo pipefail; T=AK-3; . /root/aklab/lib.sh
stamp "AK-3: household groups"
run "admin_relogin"
for g in onemind_owners onemind_adults onemind_children onemind_guests; do run "k group create $g"; done
run "k person create adult1 'Adult One'"; run "k person create adult2 'Adult Two'"
run "k person create child1 'Child One'"; run "k person create guest1 'Guest One'"
run "k group add-members onemind_owners owner"
run "k group add-members onemind_adults adult1 adult2"
run "k group add-members onemind_children child1"
run "k group add-members onemind_guests guest1"
for p in adult1 child1 guest1; do run "reset_token $p $p.reset"; run "\$PY enrol $p $p.reset passkey"; done
run "reset_token adult2 adult2.reset"; run "\$PY enrol adult2 adult2.reset password+totp"
note "gateway read path: a service account with an API token, reading memberof over REST"
run "k service-account create onemind_gateway 'OneMind gateway (lab)' idm_admins"
note "read rights: idm_account_mail_read is the narrowest built-in group whose ACP (idm_acp_people_read) lets a service account read memberof of persons"
run "k group add-members idm_account_mail_read onemind_gateway"
run "kanidm service-account api-token generate onemind_gateway gateway-read -D idm_admin 2>&1 | grep -oE '[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}' | head -1 > $SEC/gateway.api_token; chmod 600 $SEC/gateway.api_token; test -s $SEC/gateway.api_token && echo 'api token issued (kept in the secrets dir)'"
run "\$PY memberof gateway.api_token owner adult1 child1 guest1"
run "for g in onemind_owners onemind_adults onemind_children onemind_guests; do k group list-members \$g; done"
