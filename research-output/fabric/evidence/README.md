<!-- SPDX-License-Identifier: Apache-2.0 -->
# Evidence for the fabric mission

> **Explain it like I'm the founder.** Every fact in the fabric files has an ID like `C-FB4-001`. This folder is where those IDs live: the source, the date it was read, and how sure we are. Lab tests and the arguments against our own conclusions are here too, so anyone can check our work.

| What | Where |
|---|---|
| Claims ledger (same columns as mission 01) | `claims/FB1.csv` … `claims/FB11.csv`, `claims/FBREF.csv` (refuter sources) in this folder; lab ledgers next to mission 01's: `../../evidence/claims/LAB-fb2-fdo-enroll.csv`, `LAB-fb4-fleet-rings.csv` (and the earlier `LAB-fb3-mesh-nat.csv`) |
| Lab spikes (pre-registered) | `../../evidence/lab/fb3-mesh-nat/` (spike 1, PASS, earlier run), `fb4-fleet-rings/` (spike 2), `fb2-fdo-enroll/` (spike 3, PASS), `fb-bridges/` (spike 4, BLOCKED), `fb-installer-mode/` (spike 5, BLOCKED); register `../../evidence/lab/PREREGISTRATION.md` |
| Saved copies of load-bearing web pages | `sources/FB/*.txt` (plain text, masked), hashes in `sources/FB/SHA256SUMS`; GitHub sources are pinned to commit SHAs in the ledgers instead |
| Refuters and steelmen | `refuters/` (not blind; see its README) |

**Lab placement.** The brief asks for lab logs under `research-output/fabric/evidence/`. Spike 1 had already been committed under `research-output/evidence/lab/` with mission 01's single pre-registration register, so spikes 2–5 follow it there to keep one register; this README is the pointer.

**Claim-ID prefixes.** `C-FB<n>-…` = workstream FB-n (FB1 join matrix, FB2 identity, FB3 connectivity, FB4 multi-cluster, FB5 naming, FB6 AI, FB8 updates, FB9 vehicles, FB11 competitors); `C-FBREF-…` = sources added by refuters; `C-LAB-<spike>-…` = lab results. Mission 01 IDs (`C-W4-…`, `C-TD-…`, `C-LIC-…`) are cited unchanged.

**Hygiene.** No secrets, private IPs, e-mail addresses or host paths: lab logs are masked (`<lab-dir>`, `<hub-ip>`, `<pod-ip>`, `<vm-ip>`), device credential prints and raw server debug dumps were not committed, and the lab Docker network used the documentation range 198.51.100.0/24.
