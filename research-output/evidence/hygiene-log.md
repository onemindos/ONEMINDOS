# Hygiene log: secrets, personal data and private addresses

**Owner:** HYG agent · **Last scan:** 2026-11-11 (working tree of `research/ultracode-foundation` on top of `ee98bc7`) · **Answers:** critic pass-2 N13 (no hygiene record) and the history part of N1/N2.

> ### Explain it like I'm the founder
> The repo is public, so anything committed can be read by anyone, forever, even after we delete it, because git keeps old versions. This file records three things: **what we scan for and how**, **which hits are harmless and why** (so the next reviewer does not raise them again), and **what leaked earlier and what we did about it**. One early commit (`414d60a`) contained the lab computer's home-folder path and some internal virtual-machine addresses. They are masked in every file now, but that old commit still holds them. Removing them from history needs a force-push, which the research brief forbids, so it is your decision (Q-P2-5).

## 1. Scans run and results

| Check | Command (run from `<repo>`) | Result on 2026-11-11 |
|---|---|---|
| Secrets | `gitleaks dir research-output` (gitleaks 8.30.1) | **1 hit, reviewed as a false positive** (§2, FP-6). trufflehog is not installed |
| Private IPv4 (RFC1918 and 100.64/10) | `grep -rE` for `10.x`, `172.16–31.x`, `192.168.x`, `100.64–127.x` over `research-output/` | **Clean** in the working tree. Commit `414d60a`: 11 files hit (§3) |
| Host home path / username | `grep -rE '/Users/[a-z]'` plus the account name | **Clean** in the working tree. Commit `414d60a`: 17 files hit (§3) |
| Tailnet names | `grep -rhoE '[A-Za-z0-9.-]*\.ts\.net'` | Only the bare string `.ts.net` appears, in critic files describing the check itself. No hostname |
| E-mail-shaped strings | `grep -rhoE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}'` | 5 distinct strings, all false positives (§2) |
| Lab-host paths (`work/.lab`) | `grep -rn 'work/\.lab'` | **Fixed in `sources/**` and claim rows** this pass (§4). Remaining hits are listed in §5 |

## 2. Reviewed false positives (do not re-raise)

| ID | Hit | Where | Why it is acceptable |
|---|---|---|---|
| FP-1 | `security@pengutronix.de` | `claims/REF-W3-longevity.csv` (3×) | Public role address of the RAUC maintainers' security team, quoted from their published security policy. Not personal data |
| FP-2 | `aur-general@lists.archlinux.org` | `sources/W19.md` (2×) | Public mailing-list address quoted from Arch Linux documentation |
| FP-3 | `serial-getty@ttyS0.service` | lab logs (8×) | A systemd unit name (the `@` is template syntax), not an e-mail |
| FP-4 | `ha-blog-securetar-v3@6f38b5b4.md` | sources file names | A file name pinned to a commit, not an e-mail |
| FP-5 | `git@github.com` | one source | GitHub's generic SSH remote user, published by GitHub |
| FP-6 | `MENDER_APT_KEY_FP="E6C8…1B29B00"` (gitleaks `generic-api-key`) | `sources/LAB-mender/mender-convert@85e8c50_configs_mender_convert_config_L225-L240.txt` line 13 | The public fingerprint of Mender's APT signing key, copied from upstream `mender-convert` at a pinned SHA. A fingerprint identifies a public key; it grants nothing. If push protection objects, mask it as `<masked-fingerprint>` like the two existing cases |
| FP-7 | `K3S_TOKEN=xxx` | `lab/w5-restore/shared/install.sh` line 14 | A usage comment in the unmodified upstream k3s installer (sha256 `c2a2643d…ab9d`). `xxx` is a placeholder. Editing it would break the file's hash match with upstream |
| FP-8 | `K3S_TOKEN` / `K3S_TOKEN_FILE` | same file, lines 21 and 181 | Variable names in upstream code, not values |
| FP-9 | Key option names in man pages (`mkosi.1.md`: `SecureBootKey=`, `VerityKey=` and similar) | `lab/w18-mac-toolchain/sources/mkosi.1.md`, `sources/W18/` | Option names from upstream documentation, with no key values |
| FP-9b | `<masked-token>` placeholders | `sources/TD-tier-c-alt/`, `sources/W14/` | Example or leaked tokens in saved third-party pages, already masked at save time |
| FP-10 | Fedora signing-key UID in a build log | `lab/fedora-bootc/logs/` | A public Fedora package-signing key ID (pass-1 #24), already masked as `fedora-44-primary (Fedora public key UID, masked)` |

## 3. What leaked earlier, and what was done

**Commit `414d60a`** (2026-11-11T04:13:48Z, pushed to `origin/research/ultracode-foundation`) contained:
- the lab host's **home path, including the account name**, in 17 files: `w18-mac-toolchain/{artifacts.txt,spike.log,start.log}`, `w4-k3s-footprint/{create.log,start.log}`, `w5-restore/logs/{a1-attempt1-race,a1,a2,b1,b2,create-w5a,create-w5b,start-w5a,start-w5b}.log`, `w5-restore/scripts/drill.sh` and `w5-restore/shared/{drill.sh,reverify.sh}` (critic N1);
- **VM-internal private addresses** in 11 files: the Lima host-gateway address and `10.42.0.x` pod addresses in the w4, w5 and w18 logs (critic N2). These are addresses inside throwaway VMs, not the founder's network, but the rule is absolute.

**Masking done so far (working tree, before and during this pass):**
- Home path → `<home>`, account name → `<user>`, lab folder → `<lab-dir>`, VM gateway → `<vm-private-ip>` / `<vm-ip>`, other private addresses → `<private-ip-masked>`, e-mails in saved vendor pages → `<email-masked>` / `<masked-email>` (vendor originals' hashes kept in `sources/LIC/ORIGINAL-HASHES.txt`), tokens → `<masked-token>`, key fingerprints → `<masked-fingerprint>`.
- Commit `ee98bc7` and the working tree have **no** home-path, account-name or private-address hits.
- The masked lab files no longer match the hashes written at run time; each lab's `versions.md` says which files differ and why.

**History was not rewritten.** The brief (§8) forbids force-push, so `414d60a` still holds the unmasked text and anyone can read it from the branch history. Masking applies going forward only. Removing it needs a history rewrite and force-push of the research branch (or squash-merging the PR and deleting the branch, which keeps the commit reachable on GitHub until garbage-collected). That is the founder decision in critic pass-2 Q-P2-5; it should be listed in `26-OPEN-QUESTIONS-FOR-ZEUS.md` by its owner.

## 4. Changes made in this pass

- `work/.lab` → `<lab-dir>` in `sources/{W4,W5,W9,LEDGER,TD-balenaos,TD-casaos-zimaos,TD-kairos,TD-project-nomad,TD-proxmox-ve,TD-startos,TD-talos}.md` and `sources/{W4,W5,W6,W18,TD-villageos,TD-truenas-scale/from-lab}/INDEX.md` (critic #14, ledger-audit L2).
- Claim rows C-W4-076…081 and the eight C-W5 lab rows (in `claims/W4.csv`, `claims/W5.csv` and the master `claims.csv`) now point to the in-repo, masked copies under `research-output/evidence/lab/…` instead of the lab host (critic #5).
- The page saved for C-W18-038 (`sources/HYG/`) was checked for credential-, account- and e-mail-shaped strings before saving: none.

## 5. Remaining hits (not changed here; owners should decide)

These name the lab layout (`~/<lab-dir>/…` or `$HOME/<lab-dir>/…`) but **no account name**. Changing lab READMEs would break their recorded hashes (`lab/PREREGISTRATION.md`), so they were left alone:
- `lab/fedora-bootc/README.md` line 84, `scripts/lab.sh` line 3, `scripts/run-vm.sh` line 7
- `lab/k3s-footprint-restore/scripts/{host-fetch,host-source,host-restore,run-all}.sh` (default `LAB=` value)
- `lab/rauc/README.md` line 170, `lab/rauc-k3s-gate/README.md` line 189, `lab/secureboot-rauc/README.md` line 173
- `06-backups-recovery.md` line 313; `adversarial/W4-P0-1-technical.md`, `W5-W5-P0-1-{technical,longevity,security}.md`, `W5-W5-P0-2-security.md` (relative `work/.lab/…` paths in refuter evidence, which is a historical record)
- `sources/W12/parse-catalogs.py` line 2 (a default value in a script; replacing it with `<lab-dir>` would break the script)
- Critic files quote the leaked strings in masked form only (`/Users/<user>/…`), which is fine.

**Recommendation:** in the next lab edits, replace the default with `LAB=${LAB:?set LAB to your lab folder}` and refer to `<lab-dir>` in prose.

## 6. Before every push

1. `gitleaks dir research-output` and `gitleaks git --log-opts="origin/main..HEAD"`: only §2 entries may appear.
2. The IP, home-path, `.ts.net` and e-mail greps in §1: only §2 entries may appear.
3. Any new saved page: mask credential-, account- and e-mail-shaped strings (even documentation examples) before hashing, and record the original hash.

## Glossary

- **gitleaks:** a scanner that looks for passwords, API keys and tokens in files and git history.
- **False positive:** a scanner hit that looks like a secret but is not one.
- **RFC1918 / 100.64/10:** IP ranges used only inside private networks (home, office, VMs, Tailscale). Publishing them reveals network layout.
- **Force-push / history rewrite:** replacing commits already on the server. It is the only way to remove text from git history, and it breaks everyone else's copy of the branch.
- **Masking:** replacing a sensitive value with a placeholder such as `<home>` or `<vm-private-ip>`.
