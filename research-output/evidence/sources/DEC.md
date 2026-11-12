# Sources: DEC (01-FOUNDATION-DECISION, 00-EXECUTIVE-SUMMARY, 26-OPEN-QUESTIONS-FOR-ZEUS)

All accessed 2026-11-10. The DEC agent verified only the facts below itself. Everything else in `01-…` cites claim IDs already in the other ledgers (`evidence/claims/*.csv`), and the counter-arguments in the adversarial tables cite the refuter files in `evidence/adversarial/`, whose own sources are listed inside each file.

| # | Source | Type | Claims | Archive / integrity |
|---|---|---|---|---|
| 1 | `rauc/rauc@4fb7c798d6ae412344fb8f8d310d773046af3441:docs/reference.rst` (L97–L110, L523–L531) | PRIMARY (code repo, pinned tag v1.15.2) | C-DEC-001, C-DEC-003, C-DEC-005 | Git commit pin; sha256 of the file at that commit `b071047bc4348a6ddada6c394d2e56db6fff45e923fd95f0b067f04729b59668` |
| 2 | `rauc/rauc@4fb7c798…:docs/integration.rst` (L1228–L1250) | PRIMARY | C-DEC-002 | Git commit pin; sha256 `4fd15cb14a71212f24f0f7370c688430301a4fd58c60114538dbcfbb8d9521ae` |
| 3 | `rauc/rauc@4fb7c798…:CHANGES` (L1–L11); advisory https://github.com/rauc/rauc/security/advisories/GHSA-6hj7-q844-m2hx | PRIMARY | C-DEC-004 | Git commit pin; sha256 `3b2350ea69d1ba4573af9015b8e725c78aa932d9b42aa85ae16df1525f72bfd8` |
| 4 | https://bugs.launchpad.net/ubuntu/+source/linux-raspi/+bug/2170238 | PRIMARY (vendor bug tracker) | C-DEC-006 | No Wayback snapshot exists (availability API returned none); creating one was not attempted because Wayback save requests are blocked by this environment's permission policy. sha256 of the HTML fetched 2026-11-10: `7b4319ba46df06f3f9154d308e2548bad3f99cff536c4f52063e12ebcf37aa28` (40,393 bytes). **ARCHIVE-GAP.** ARCH5 (2026-11-11): still partial; Launchpad does not resolve here. The status fields are saved in `PLAN180/launchpad-2170238.txt`; for the description, see founder step F-1 in `ARCH5.md`. |
| 5 | https://www.truenas.com/docs/scale/24.10/gettingstarted/scalereleasenotes/ | PRIMARY (vendor release notes) | C-DEC-007 | Wayback: http://web.archive.org/web/20261015034155/https://www.truenas.com/docs/scale/24.10/gettingstarted/scalereleasenotes/ ; sha256 of the HTML fetched 2026-11-10: `ac67edd7aba2814bf2e92c3eb4578c9b9720afb7c3c1caac63c7691754389456`. Note: the page gives 24.10.0 as 2024-10-29 in its 24.10.0 section but 2024-12-17 in its introduction (that date matches 24.10.1). |

**Derived numbers (not new facts):** the refuter-corrected scorecard totals and their ±5 sensitivity runs in `01-FOUNDATION-DECISION.md` §3 were computed with the frozen formula `Σ(weight × score)/5` and the proportional rescaling rule in `evidence/scorecard-weights.md` §6. The script is short and reproduced in `01-…` §3.6 so anyone can re-run it.

### Added 2026-11-11 (revision 2)

| # | Source | Type | Claims | Archive / integrity |
|---|---|---|---|---|
| 6 | `torvalds/linux@adc218676eef25575469234709c2d87185ca223a` (tag v6.12): `kernel/module/signing.c` (L64–L65) | PRIMARY (code, pinned tag) | C-DEC-008 | Saved: `sources/DEC/linux-v6.12-kernel-module-signing.c.txt` (one author email in the header masked), sha256 of the original `b6dac3fb2527b3a2b897bf1279f056479d888be82cbdb612225c49568962e938`, of the saved copy `e958b2544b522eb1ecaa0a39f17abe58ad7f34f2f9bafb4b746b734433adfc58` |
| 7 | same commit: `security/integrity/platform_certs/load_uefi.c` (L156–L191) | PRIMARY | C-DEC-009 | Saved: `sources/DEC/linux-v6.12-security-integrity-platform_certs-load_uefi.c.txt`, sha256 `a3ceaf8ad33201a57236b4fe99c418109db8987dbc26a46b59d1a8e924d27fd9` |
| 8 | same commit: `security/integrity/Kconfig` (L55–L75) | PRIMARY | C-DEC-009, C-DEC-010 | Saved: `sources/DEC/linux-v6.12-security-integrity-Kconfig.txt`, sha256 `53c2a292cfdab6e3cef032d86a4cc244d9bb16eb8be7724cb1e905f499bc20ad` |

Why these were checked: X-2R enrolled a OneMind key in UEFI db [C-LAB-secureboot-rauc-012], and DC-16 needs OneMind-signed driver packs to load under lockdown. On a stock (Debian-built) kernel a db key cannot do that; only a key built into the kernel or a MOK key can. This is what links DC-16 and Secure Boot to the kernel route (01 §3.5). Debian's own kernel config was not opened; the inference that Debian enables the machine keyring is **not** relied on.

### Added 2026-11-11 (revision 3, critic pass-2 N9)

| # | Source | Type | Claims | Archive / integrity |
|---|---|---|---|---|
| 9 | `rauc/rauc@4fb7c798d6ae412344fb8f8d310d773046af3441` (tag v1.15.2): `docs/integration.rst` L1801–L1833 ("Package-Based Distributions") | PRIMARY (project docs, pinned tag) | C-DEC-011 | Saved: `sources/DEC/rauc-v1.15.2-integration-package-distros.txt`, sha256 `33866b0ed7737a86f9e7f077a58b90ad6213baffbcaa64f7c9d54a8c5d4d227c` |
| 10 | https://rauc.io/ (project home page, opened 2026-11-11) | PRIMARY (project site) | C-DEC-012 | Saved as text: `sources/DEC/rauc-io-home-2026-11-11.txt` (one sales e-mail address masked), sha256 of the saved copy `21e00910f606f0913a25ac7527c1c905cfb6d9bec56d70b958cdc60cb6f19390`, of the unmasked text `d01aaab091066536e7f7c56fd328142aa562ec2bee6cc0f0f056439ce7c3a1f2`. No Wayback capture made (save requests blocked here). |
| 11 | N9 precedent search, 2026-11-11: three extended web searches ("Debian-based appliance product uses RAUC A/B update production"; RAUC users list with Debian or Ubuntu rootfs; RAUC with debos/debootstrap on a robot or gateway), the rauc.io page (#10), RAUC's own docs at v1.15.2 (#9), and the ledger's existing competitor rows (HAOS, ZimaOS, SteamOS, umbrelOS) | Search log (negative result) | C-DEC-013 | Results named no shipped Debian- or Ubuntu-based product on RAUC; the only Debian mention was a 2019 Raspberry Pi forum post by a developer (not a product, not opened as evidence). Recheck when Pengutronix publishes case studies. |
| 12 | https://www.sonarsource.com/blog/security-vulnerabilities-in-casaos/ (2023-10-17) | SECONDARY (security vendor research post) | C-DEC-014 | Saved as text: `sources/DEC/sonarsource-casaos-cve-2023-37265-2026-11-11.txt`, sha256 of the saved copy (example private IPs masked) `dc02ed815b6672f39a33a7966213fa6dc5f5966d5dadbf7bf4f4642b8f57e8b8` |
| 13 | https://kubernetes.io/docs/concepts/security/pod-security-standards/ (docs for v1.37, opened 2026-11-11) | PRIMARY (project docs) | C-DEC-015 | Saved as text: `sources/DEC/kubernetes-pod-security-standards-2026-11-11.txt`, sha256 `f152f25273712a2b314224587bdd0d86dcd190d27e70adca4b78fad5fb6f58a1` |

**Ledger defect found in rev. 3 (reported, not fixed here):** three wave-3 refuter files reuse `C-REF3-DC-security-*` numbers that `claims/REF3-DC-security.csv` assigns to different facts: `DC-14-security.md` (its 003–005), `DC-22-security.md` (001–002) and `DC-24-security.md` (006–008). Their own sources are therefore not ledgered under those IDs. 01 cites the two load-bearing ones through C-DEC-014 and C-DEC-015, and cites the other three files by file name only. The REF3 owner should renumber those rows.
