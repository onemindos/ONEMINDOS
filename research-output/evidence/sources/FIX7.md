# Sources · FIX7 (critic pass-7 gap P7-2)

**Agent:** FIX7 · **Accessed:** 2026-11-11 · **Claims:** [`../claims/FIX7.csv`](../claims/FIX7.csv) (C-FIX7-001…006)

**Access note.** As FIX4 and FIX5 recorded, `ubuntu.com`, `canonical.com`, the Ubuntu archive and (newly checked here) `api.launchpad.net` do not resolve from this session, on the host or through the fetch tool. Nothing was bypassed: no mirror, alternative resolver or IP read was used. Ubuntu 26.04 package facts therefore come from Repology, a third-party index, and are labelled SECONDARY / `partial`. Canonical's own wording comes from the public source of its website on GitHub, pinned to a commit, the same route FIX4 used for C-FIX4-001.

**Masking.** Maintainer e-mail addresses in the Repology pages, the signatory's name on the certificate and two sample tokens in the hawkBit README were replaced with `<…-masked>` before hashing. Hashes are in [`FIX7/SHA256SUMS`](FIX7/SHA256SUMS).

| # | Source | Type | Saved copy | Claims |
|---|---|---|---|---|
| 1 | ISASecure certificate EUTC-RCOR4411-CSA-E01 (Eurotech ReliaCOR 44-11), https://isasecure.org/hubfs/EUTC-RCOR4411-CSA-E01.pdf | PRIMARY | `FIX7/isasecure-EUTC-RCOR4411-CSA-E01.txt` (PDF sha256 in SHA256SUMS) | C-FIX7-001 |
| 2 | canonical/ubuntu.com @ `ec15716` `templates/real-time/index.html` | PRIMARY (pinned) | `FIX7/ubuntu.com-real-time-index@ec15716.txt` | C-FIX7-002 |
| 3 | https://repology.org/project/linux-raspi-realtime/versions | SECONDARY | `FIX7/repology-linux-raspi-realtime.txt` | C-FIX7-003 |
| 4 | https://repology.org/project/{open62541,mosquitto,libmodbus,can-utils}/versions | SECONDARY | `FIX7/repology-*.txt` | C-FIX7-004 |
| 5 | https://repology.org/project/rauc-hawkbit-updater/versions | SECONDARY | `FIX7/repology-rauc-hawkbit-updater.txt` | C-FIX7-005 |
| 6 | rauc/rauc-hawkbit-updater @ `37b2ef4` `README.md`, plus GitHub release and licence metadata | PRIMARY (pinned) | `FIX7/rauc-hawkbit-updater-README@37b2ef4.md` | C-FIX7-006 |

Rows reused from other ledgers (not re-opened): C-STEEL-ubu-007/008/010, C-W18-060, C-CIT4-012, C-FIX4-001, C-W8-041, C-W8-044, C-W8-049, C-REF4-DC-technical-004, C-W2-005, C-W2-006.
