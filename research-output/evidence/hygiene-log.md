# Hygiene log: secrets, personal data and private addresses

**Owner:** HYG agent; re-scan and P3-10 masking by PROP4-d · **Last scan:** 2026-11-11, after `01` revision 4.1 (working tree of `research/ultracode-foundation` on top of `b933b86`, the rev-4 commit, which is pushed [C-SYNC5-a-001]); history re-scanned per commit by SYNC5-a · **Answers:** critic pass-2 N13 (no hygiene record), the history part of N1/N2, critic pass-3 P3-7 and P3-10, and critic P4-9 (§3), P4-11 (§4.2) and P6-4 (§7).

> ### Explain it like I'm the founder
> The repo is public, so anything committed can be read by anyone, forever, even after we delete it, because git keeps old versions. This file records three things: **what we scan for and how**, **which hits are harmless and why** (so the next reviewer does not raise them again), and **what leaked earlier and what we did about it**. One early commit (`414d60a`) contained the lab computer's home-folder path and some internal virtual-machine addresses. They are masked in every file now, but that old commit still holds them. Removing them from history needs a force-push, which the research brief forbids, so it is your decision (Q-P2-5).

## 1. Scans run and results

| Check | Command (run from `<repo>`) | Result on 2026-11-11 |
|---|---|---|
| Secrets | `gitleaks dir research-output` (gitleaks 8.30.1) | **0 hits** after `01` rev. 4. Critic pass 3 counted 2 (P3-7): FP-6 and the same public Mender fingerprint in `lab/mender/scripts/build.sh` line 16 (FP-6b). Both are now in `.gitleaksignore`, which is why they no longer show. trufflehog is not installed |
| Private IPv4 (RFC1918 and 100.64/10) | `grep -rE` for `10.x`, `172.16–31.x`, `192.168.x`, `100.64–127.x` over `research-output/` | **Clean** in the working tree. Commit `414d60a`: 11 files hit (§3) |
| Host home path / username | `grep -rE '/Users/[a-z]'` plus the account name | **Clean** in the working tree except FP-11 (a planted fake path in a test description). Commit `414d60a`: 17 files hit (§3) |
| Tailnet names | `grep -rhoE '[A-Za-z0-9.-]*\.ts\.net'` | Only the bare string `.ts.net` appears, in critic files describing the check itself. No hostname |
| E-mail-shaped strings | `grep -rhoE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}'` | 6 distinct strings, all false positives (§2; `serial-getty@ttyAMA0.service` from the rev-4 arm64 lab is FP-3's pattern) |
| Lab-host paths (`work/.lab`) | `grep -rn 'work/\.lab'`, plus a grep for the host's own folder names (substitute them locally; they are not written here, because the pattern would itself publish the layout) | **Fixed in `sources/**` and claim rows** (§4), and in every lab README and script after critic pass 3 (§4.1, P3-10). **No hit names the host's folder layout any more.** The remaining short relative mentions are listed in §5 |

## 2. Reviewed false positives (do not re-raise)

| ID | Hit | Where | Why it is acceptable |
|---|---|---|---|
| FP-1 | `security@pengutronix.de` | `claims/REF-W3-longevity.csv` (3×) | Public role address of the RAUC maintainers' security team, quoted from their published security policy. Not personal data |
| FP-2 | `aur-general@lists.archlinux.org` | `sources/W19.md` (2×) | Public mailing-list address quoted from Arch Linux documentation |
| FP-3 | `serial-getty@ttyS0.service` | lab logs (8×) | A systemd unit name (the `@` is template syntax), not an e-mail |
| FP-4 | `ha-blog-securetar-v3@6f38b5b4.md` | sources file names | A file name pinned to a commit, not an e-mail |
| FP-5 | `git@github.com` | one source | GitHub's generic SSH remote user, published by GitHub |
| FP-6 | `MENDER_APT_KEY_FP="E6C8…1B29B00"` (gitleaks `generic-api-key`); **FP-6b:** the same fingerprint as `MKEY_FP=…` in `lab/mender/scripts/build.sh` line 16 | `sources/LAB-mender/mender-convert@85e8c50_configs_mender_convert_config_L225-L240.txt` line 13; FP-6b in the lab script. Both are listed in `.gitleaksignore` | The public fingerprint of Mender's APT signing key, copied from upstream `mender-convert` at a pinned SHA. A fingerprint identifies a public key; it grants nothing. If push protection objects, mask it as `<masked-fingerprint>` like the two existing cases |
| FP-7 | `K3S_TOKEN=xxx` | `lab/w5-restore/shared/install.sh` line 14 | A usage comment in the unmodified upstream k3s installer (sha256 `c2a2643d…ab9d`). `xxx` is a placeholder. Editing it would break the file's hash match with upstream |
| FP-8 | `K3S_TOKEN` / `K3S_TOKEN_FILE` | same file, lines 21 and 181 | Variable names in upstream code, not values |
| FP-9 | Key option names in man pages (`mkosi.1.md`: `SecureBootKey=`, `VerityKey=` and similar) | `lab/w18-mac-toolchain/sources/mkosi.1.md`, `sources/W18/` | Option names from upstream documentation, with no key values |
| FP-9b | `<masked-token>` placeholders | `sources/TD-tier-c-alt/`, `sources/W14/` | Example or leaked tokens in saved third-party pages, already masked at save time |
| FP-10 | Fedora signing-key UID in a build log | `lab/fedora-bootc/logs/` | A public Fedora package-signing key ID (pass-1 #24), already masked as `fedora-44-primary (Fedora public key UID, masked)` |
| FP-11 | A `/Users/…` path in a test description | `30-NEXT-ULTRACODE-BUILD-BRIEF.md` line 191 (D-B1.3) | A deliberately planted fake path, used to prove the hygiene check fails when it should. It is not the lab host's path |

## 3. What leaked earlier, and what was done

**Every pushed commit, scanned (SYNC5-a, critic P4-9).** All four commits on the research branch are pushed; the branch head is `b933b86` [C-SYNC5-a-001]. "Adds" counts lines a commit introduced; "tree" counts files that hold the string in that commit's snapshot, including ones inherited from earlier commits [C-SYNC5-a-002].

| Commit | Account name or home path | Private IPv4 | Host folder layout (no account name) | Tailnet name / CGNAT |
|---|---|---|---|---|
| `414d60a` (Tier A) | **Adds: 17 files** | **Adds: 11 files** | Adds: 16 files | none |
| `ee98bc7` (wave 2) | none (it masks them) | none | Adds 3 (`critic/pass-2.md`, `lab/rauc-k3s-gate/README.md`, `lab/secureboot-rauc/README.md`); tree: 11 | none |
| `7836316` (wave 3, rev. 3) | none (only FP-11) | none | Adds 2 (`critic/pass-3.md`, this file's grep pattern); tree: 13 | none |
| `b933b86` (wave 4, rev. 4) | none (only FP-11) | none | Tree: 3 (`critic/pass-2.md`, `critic/pass-3.md`, this file); masked in the working tree by SYNC5-a (§4.2) | none |

So removing the account name needs only `414d60a` rewritten, but removing the host folder layout from history needs all four. Z-28 in `26` names them.

**Commit `414d60a`** (2026-11-11T04:13:48Z, pushed to `origin/research/ultracode-foundation`) contained:
- the lab host's **home path, including the account name**, in 17 files: `w18-mac-toolchain/{artifacts.txt,spike.log,start.log}`, `w4-k3s-footprint/{create.log,start.log}`, `w5-restore/logs/{a1-attempt1-race,a1,a2,b1,b2,create-w5a,create-w5b,start-w5a,start-w5b}.log`, `w5-restore/scripts/drill.sh` and `w5-restore/shared/{drill.sh,reverify.sh}` (critic N1);
- **VM-internal private addresses** in 11 files: the Lima host-gateway address and `10.42.0.x` pod addresses in the w4, w5 and w18 logs (critic N2). These are addresses inside throwaway VMs, not the founder's network, but the rule is absolute.

**Masking done so far (working tree, before and during this pass):**
- Home path → `<home>`, account name → `<user>`, lab folder → `<lab-dir>`, VM gateway → `<vm-private-ip>` / `<vm-ip>`, other private addresses → `<private-ip-masked>`, e-mails in saved vendor pages → `<email-masked>` / `<masked-email>` (vendor originals' hashes kept in `sources/LIC/ORIGINAL-HASHES.txt`), tokens → `<masked-token>`, key fingerprints → `<masked-fingerprint>`.
- Commits `ee98bc7`, `7836316` and `b933b86` (all pushed) and the working tree have **no** home-path, account-name or private-address hits (re-checked 2026-11-11 after rev. 4.1; the only `/Users/` string is FP-11). Commit `7836316` still carries ten of the eleven lab-layout paths masked in §4.1 (`secureboot-1152` was never committed); they name no account. `b933b86` carries the layout only in the three quotations listed in the table above.
- The masked lab files no longer match the hashes written at run time; each lab's `versions.md` says which files differ and why.

**Update 2026-11-11: history rewritten (Z-28 = a, founder-approved).** Zeus allowed the one-time rewrite. All six commits on `research/ultracode-foundation` were rebuilt with `git filter-repo --replace-text`. The rules were home path → `<home>`, account name → `<user>`, lab folder → `<lab-dir>` (and the bare host folder name in grep patterns → `<lab-host-folder>`), the Lima gateway → `<vm-private-ip>`, and `10.42.0.x` → `<vm-ip>`. The branch was then force-pushed once, with a lease on the old head. **Checks after the rewrite:** (1) `git log -p` over the branch range has 0 hits for the account name, the host folder name, the home path or the private addresses; (2) the head tree is byte-identical to the pre-rewrite head (`git diff --quiet` passes), so no research content changed; (3) `gitleaks git` over the 6 commits finds no leaks. Commits that were already on `main` were not touched; `main` had already removed its own home-path line in PR #3. **Still open:** GitHub keeps the old commits readable by SHA until GitHub Support purges cached views. Zeus files that request. Every clone made before the rewrite must be reset to the new head and must never push the old branch back. The SHAs elsewhere in this log are the **old** ones; map them with this table:

| Old SHA (purged) | New SHA | Commit |
|---|---|---|
| `414d60a` | `d6620f9` | Tier A |
| `ee98bc7` | `ce42a47` | wave 2 |
| `7836316` | `03d8d00` | wave 3, rev. 3 |
| `b933b86` | `7a337a7` | wave 4, rev. 4 |
| `66db1ac` | `859eec1` | wave 5, rev. 4.1 |
| `6eeaf04` | `8922454` | founder decision Z-38 |

**Before the rewrite (kept for the record):** the brief (§8) forbade force-push, so `414d60a` still held the unmasked text and anyone can read it from the branch history. Masking applies going forward only. Removing it needs a history rewrite and force-push of the research branch (or squash-merging the PR and deleting the branch, which keeps the commit reachable on GitHub until garbage-collected). That is the founder decision in critic pass-2 Q-P2-5, listed as Z-28 in `26-OPEN-QUESTIONS-FOR-ZEUS.md` with all four commits named.

## 4. Changes made in this pass

- `work/.lab` → `<lab-dir>` in `sources/{W4,W5,W9,LEDGER,TD-balenaos,TD-casaos-zimaos,TD-kairos,TD-project-nomad,TD-proxmox-ve,TD-startos,TD-talos}.md` and `sources/{W4,W5,W6,W18,TD-villageos,TD-truenas-scale/from-lab}/INDEX.md` (critic #14, ledger-audit L2).
- Claim rows C-W4-076…081 and the eight C-W5 lab rows (in `claims/W4.csv`, `claims/W5.csv` and the master `claims.csv`) now point to the in-repo, masked copies under `research-output/evidence/lab/…` instead of the lab host (critic #5).
- The page saved for C-W18-038 (`sources/HYG/`) was checked for credential-, account- and e-mail-shaped strings before saving: none.

### 4.1 Changes made after critic pass 3 (P3-10, P3-7)

- **Lab READMEs and scripts masked (P3-10).** Eleven files named the lab host's folder layout (no account name): `lab/fedora-bootc/{README.md,scripts/lab.sh,scripts/run-vm.sh}`, `lab/k3s-footprint-restore/scripts/{host-fetch,host-restore,host-source,run-all}.sh`, and the READMEs of `lab/rauc`, `lab/rauc-k3s-gate`, `lab/secureboot-rauc` and `lab/secureboot-1152`. READMEs now say `<lab-dir>/<spike>`. Scripts now use `LAB=${LAB:?"set LAB to <lab-dir>/<spike>"}`, so they stop with a clear error instead of defaulting to a host path; `bash -n` passes on all six.
- **The pre-registration record is kept.** Every README edit sits below its `## Results` heading, the part the register allows to change; `secureboot-1152`'s frozen prefix still hashes to its registered value. The original and masked sha256 of all eleven files, and the commit holding each unmasked original, are in `lab/PREREGISTRATION.md` §"Masking log". `SHA256SUMS` in `fedora-bootc/`, `k3s-footprint-restore/` and `secureboot-1152/` now carry the masked hashes and verify; each affected `versions.md` says so.
- **gitleaks (P3-7):** re-run; 0 hits. FP-6b recorded in §2.

### 4.2 Changes made after critic pass 7 (P4-11, SYNC5-a)

- The host folder layout quoted in `critic/pass-2.md` l. 48 and `critic/pass-3.md` l. 61 and l. 114 is replaced with `<lab-dir>` (for example `$HOME/<lab-dir>`). Line numbers are unchanged. After this, `grep` for the host's folder names over `research-output/` returns nothing in the working tree; history keeps it (§3).
- The §1 lab-host row no longer spells the layout as a grep pattern.

## 5. Remaining hits (not changed here; owners should decide)

None of these names the host's folder layout or an account; each is a short relative `work/.lab/…` mention:
- `06-backups-recovery.md` line 313 (also stale: `w5-restore` now lives in `evidence/lab/w5-restore/`; critic P3-8c, owner of 06); `adversarial/W4-P0-1-technical.md`, `W5-W5-P0-1-{technical,longevity,security}.md`, `W5-W5-P0-2-security.md` (relative `work/.lab/…` paths in refuter evidence, which is a historical record)
- `sources/W12/parse-catalogs.py` line 2 (default `LAB_SRC` value `work/.lab/src`, relative; it is a source-capture script, not a lab spike, so P3-10 did not cover it)
- Critic files quote the leaked strings in masked form only (`/Users/<user>/<lab-dir>/…`), which is fine. Critic passes 4–7 also mention relative `work/.lab` and the masked `/Users/<alias>` form only.

**Recommendation:** done for the lab spikes (§4.1). New lab scripts should use the same `${LAB:?…}` form from the start, and prose should say `<lab-dir>`.

## 6. Before every push

1. `gitleaks dir research-output` and `gitleaks git --log-opts="origin/main..HEAD"`: only §2 entries may appear.
2. The IP, home-path, `.ts.net` and e-mail greps in §1: only §2 entries may appear.
3. Any new saved page: mask credential-, account- and e-mail-shaped strings (even documentation examples) before hashing, and record the original hash.

## 7. Process deviations: reads past the Ubuntu DNS block (critic P6-4)

Since the afternoon of 2026-11-11 the research environment does not resolve the Ubuntu and Canonical names (`archive.ubuntu.com`, `security.ubuntu.com`, `ubuntu.com`, `canonical.com`), while other names resolve [C-FIX5-001, C-FIX5-004]. Whether the block is deliberate is not known (`lab/ubuntu-secureboot/README.md` §R.5). The run's rule is not to work around a block. Two reads went past it. Both are disclosed where they happened, and **nothing from either is used as evidence**:

| # | What happened | Where it is disclosed | Used as evidence? |
|---|---|---|---|
| D-1 | During the U-SB spike (LT-VM-20), before the agent recognised the failures as a block, it asked a public resolver from inside the VM for the archive's address and read the Ubuntu 26.04 `Release` file **once, by IP**. Nothing else was downloaded and nothing was built from it. The agent then stopped: no alternative resolver, `/etc/hosts` entry or third-party Ubuntu mirror was used | `lab/ubuntu-secureboot/README.md` §R.2 item 1 | **No**: not cited; U-SB is recorded BLOCKED [C-FIX5-002] |
| D-2 | The blind S1R5 security refuter read ubuntu.com pages through Wayback Machine captures, although those names do not resolve here | `01` §5.1.3 (security row, "Source note") | **No row 01 relies on is Wayback-only**: the same Canonical policy and lifecycle facts are corroborated by pinned GitHub copies of Canonical's site [C-REF5-S1L-001…005] |

**Whether these are acceptable is Zeus's call** (critic pass-6 Part 6; `26` Z-41). Logging them is not a judgment. Going forward: on a DNS failure for a vendor name, probe once from the host, record it, and write a founder-runnable step; do not query another resolver, read by IP, or read the vendor's pages through an archive.

## Glossary

- **gitleaks:** a scanner that looks for passwords, API keys and tokens in files and git history.
- **False positive:** a scanner hit that looks like a secret but is not one.
- **RFC1918 / 100.64/10:** IP ranges used only inside private networks (home, office, VMs, Tailscale). Publishing them reveals network layout.
- **Force-push / history rewrite:** replacing commits already on the server. It is the only way to remove text from git history, and it breaks everyone else's copy of the branch.
- **Masking:** replacing a sensitive value with a placeholder such as `<home>` or `<vm-private-ip>`.
