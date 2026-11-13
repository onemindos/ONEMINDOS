# SPDX-License-Identifier: Apache-2.0
"""Resolve git conflicts in row/registration files by keeping BOTH sides (main first, then the branch).
Only for append-style files: CHANGELOG.md, docs/leap/STATUS.md, scripts/hygiene-allow.tsv, registries.
Since change fragments (changes/README.md, scripts/changes.py) PRs no longer edit CHANGELOG.md or
STATUS.md, so this is rarely needed now: only for PRs that still edit those files directly.
usage: python3 -I scripts/merge/keepboth.py <file>...
"""
import re,sys
for p in sys.argv[1:]:
    s=open(p).read()
    def keep(m):
        a=m.group(1).splitlines(True); b=m.group(2).splitlines(True)
        return ''.join(b+[l for l in a if l not in b])  # main first, then ours
    s=re.sub(r"<<<<<<< [^\n]*\n(.*?)=======\n(.*?)>>>>>>> [^\n]*\n", keep, s, flags=re.S)
    open(p,'w').write(s)
