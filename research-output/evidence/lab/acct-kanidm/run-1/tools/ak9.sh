#!/bin/bash
# AK-9 footprint: disk.
set -euo pipefail; T=AK-9; . /root/aklab/lib.sh
stamp "AK-9 disk footprint on the source box"
run "dpkg-query -W -f='\${Package} \${Version} Installed-Size=\${Installed-Size}KiB\n' kanidmd kanidm"
run "du -sh /usr/bin/kanidmd /usr/bin/kanidm /usr/share/kanidmd"
run "du -sh /var/lib/private/kanidmd; ls -l /var/lib/private/kanidmd; du -sh /var/lib/private/kanidmd/backups"
run "rss"
