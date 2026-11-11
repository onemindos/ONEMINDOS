# Lab W19-1: can a read-only OneMind image take host-level plugins without a fork?

**Written before running:** 2026-11-11T04:27:31Z (UTC). Criteria below were not changed after the run; results are appended in a separate section.
**Question (DC-16):** Device/driver adapters and OS profiles need host-level files (binaries in `/usr`, udev rules, `/etc` drop-ins, kernel modules). Can the Tier A design (RAUC A/B read-only image + writable data partition) add and remove them at runtime through systemd system extensions (`systemd-sysext`) and configuration extensions (`systemd-confext`), with no change to the root image?

**Environment:** disposable Lima VM (vz, aarch64), Debian 13 "trixie" cloud image, no host mounts, no host credentials. systemd from Debian trixie (257.x expected). The VM has a mutable root; this lab tests the *overlay mechanism*, not a full RAUC slot. The real image test is T-W19-01 in the 29 doc.

## Hypotheses and pass/fail criteria

| # | Hypothesis | PASS if | FAIL if |
|---|---|---|---|
| H1 | A sysext image in `/var/lib/extensions/` adds a binary under `/usr/bin` and a udev rule under `/usr/lib/udev/rules.d` | after `systemd-sysext merge`: the binary runs, and `udevadm verify`/`udevadm cat` (or file presence + `udevadm control --reload`) shows the rule; the sha256 of the base `/usr` file list taken with the extension unmerged is identical before and after the whole test | merge fails, or the base `/usr` file list changes |
| H2 | A confext in `/var/lib/confexts/` adds an `/etc` drop-in (a `modules-load.d` file and a systemd unit drop-in) without writing the base `/etc` | the files are visible after `systemd-confext merge` and gone after `unmerge`; the base `/etc` file list hash is unchanged | files missing, or base `/etc` modified |
| H3 | A kernel module shipped in a sysext under `/usr/lib/modules/$(uname -r)/updates/` can be loaded | `modprobe` (with a `modules.dep` regenerated *inside the extension* at build time) or at minimum `insmod` loads it and `lsmod` lists it | the module cannot be loaded from the extension at all |
| H4 | An extension built for a different OS level is refused | with host `SYSEXT_LEVEL=1.0`, an extension declaring `SYSEXT_LEVEL=2.0` is not merged and the reason is logged | it merges anyway |
| H5 | Uninstall is clean | after removing the image and `systemd-sysext refresh`, the binary, rule and module files are gone from `/usr` | any leftover file in `/usr` |

**Decision consequence:** H1, H2, H4 and H5 PASS → DC-16 does not need a fork: sysext/confext on the data partition is the host-level extension point. H3 PASS only with a per-kernel `modules.dep` → driver packs must be built per OneMind release in the image pipeline (Flatcar's model), not by third parties at install time. H3 FAIL → kernel drivers must ship inside the image (release-bound), and third-party driver plugins become a pipeline contribution, not a runtime install.

Script: `scripts/run.sh` (runs inside the VM). Logs: `logs/`.

---

## Results (appended after the run, 2026-11-11T04:30Z)

Versions: Debian 13 (trixie), systemd 257.13-1~deb13u1, kernel 6.12.115+deb13.1-cloud-arm64, aarch64 under Lima vz. Logs: `logs/run-1.log`, `logs/run-2-h4-reason.log`. Hashes: `SHA256SUMS` (README hash there is of the pre-results version; the criteria text above is unchanged).

| # | Result | Evidence (log line) |
|---|---|---|
| H1 | **PASS** | `onemind-hello adapter v1 running`; rule file present after merge and `udevadm control --reload`; `/usr` read-only while merged (`touch: ... Read-only file system`); base `/usr` list hash identical before and after (`H1-base-usr PASS`). `udevadm cat` does not exist in udev 257, so the criterion's fallback (file presence + reload) was used. |
| H2 | **PASS** | `/etc/modules-load.d/onemind-greenhouse.conf` visible; `systemctl show ssh` gives `Environment=ONEMIND_PROFILE=greenhouse`; both gone after unmerge; base `/etc` hash unchanged. |
| H3 | **PASS (modprobe)** | `modinfo` resolves the module from the extension's `updates/` dir and `modprobe` loads it, **because the extension carries `modules.dep` regenerated for that exact kernel**. The kernel logs `module verification failed: signature and/or required key missing - tainting kernel`: with Secure Boot lockdown on, an unsigned module would be refused. |
| H4 | **PASS** | `Extension 'onemind-future' is for API level '2.0', but running on API level '1.0'` → `No suitable extensions found (1 ignored due to incompatible image(s))`. |
| H5 | **PASS** | No leftover files in `/usr`; `modprobe -n` after removal: `Module onemind_hello not found`. |

**What this means (decision consequence applied):** sysext/confext on the data partition is a working host-level extension point for a read-only image: no fork is needed for binaries, udev rules, `/etc` drop-ins or profiles. Kernel modules work only when the extension is built **against the exact OneMind kernel** (its own `modules.dep`, and later a module signature from the OneMind key). So driver packs must be produced by the OneMind release pipeline per kernel (Flatcar's model), not compiled by third parties at install time.

**Limits:** VM with a mutable root (overlay mechanism tested, not a RAUC slot switch); one run (n=1); no verity-signed images; no Secure Boot. Founder/next-session test T-W19-01 in `29-PLATFORM-ECOSYSTEM-MARKETPLACE.md` covers those.
