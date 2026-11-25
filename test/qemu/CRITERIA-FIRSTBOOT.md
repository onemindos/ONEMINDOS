# QEMU battery, first boot: pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-12 before the OneMind layer (onemindd, gateway, dashboard, NATS, `onemind-firstboot`) was built into any image or booted. Its sha256 at that moment is in `PREREGISTRATION.sha256` and in the commit that adds it, which comes before the code it judges. Nothing here may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here (they go to the run's `results-firstboot.json` and CI logs).

**Serves:** the founder's request of 2026-11-12 (every deployment boots straight into OneMind), D-007, brief 30 B2 (image layers: "… → gate → `onemindd` → …"), B4.2 (updater in the image), contract `sdk/contracts/poc-v0.md` §1–§3. **Does not replace** `CRITERIA.md`: T0–T11 keep their own criteria and must still pass on the same image.

## 1. Starting state and rules

- The fixture is the battery's own slot-A disk (`make fixtures`, version `1`, test overlay with serial autologin) plus a **NoCloud seed disk** (FAT, label `CIDATA`) whose `user-data` is a `#cloud-config` with an `onemind:` mapping `{role: hub}`. Nothing else is configured by hand: no command touches `/data` or `/etc` before F1's checks.
- "No human input" between a `reboot` and the end state, as in `CRITERIA.md` §1.
- The owner token is read only from the guest's **console** (serial log); the test never reads it from a file on the box.
- A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS. A harness bug may be re-run once and is named as such.
- Every verdict records the board, KVM or TCG, and the host CPU count.
- Timeouts (wall clock, from the moment QEMU starts or the reboot is sent): first-boot configuration line 900 s; gateway `/healthz` 900 s; node listed 600 s after `/healthz`; gate result as in `CRITERIA.md`.

## 2. Tests

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| F0 | Image contents | In the slot-A tree: `/usr/bin/onemindd`, `/usr/bin/onemind`, `/usr/bin/nats-server` run and print a version; the `nats-server` file's sha256 equals the value pinned for this arch in `os/versions.lock.yaml`; the gateway venv's Python imports `onemind_core`; `/usr/lib/onemind/dashboard/index.html` exists; `/usr/lib/onemind/tuf/` exists; units `onemind-firstboot`, `onemind-gateway`, `onemind-nats`, `onemindd`, `onemind-update` exist and **only `onemind-firstboot`** of them is enabled in the image | Any item missing, a hash mismatch, or a role unit enabled in the image |
| F1 | First boot as hub | Within the timeouts: the console shows `ONEMIND-FIRSTBOOT: configured role=hub source=nocloud` and exactly one `ONEMIND OWNER TOKEN: <64 hex>` line; `curl http://127.0.0.1:8080/healthz` returns HTTP 200; `GET /v1/nodes` **with** that token lists a node whose `node_id` equals the box's recorded node id and whose role is `hub`; the same request **without** a token gets 401; the gate logs `RESULT committed-boot slot=A version=1` | Any item missing, the token absent or printed more than once, or the node never listed |
| F2 | Dashboard served | `GET /` on :8080 returns HTTP 200 and a body byte-identical (sha256) to the image's `/usr/lib/onemind/dashboard/index.html` | Different body, error, or no dashboard in the image |
| F3 | Reboot keeps state | After `systemctl reboot` with no input: the console shows `ONEMIND-FIRSTBOOT: already configured role=hub` and **no** new `ONEMIND OWNER TOKEN` line; the node id, the sha256 of the gateway's tokens file and the first-boot state file are unchanged; the **same** owner token from F1 still gets HTTP 200 on `/v1/nodes` and the box is listed again with the same `node_id` | A new token, changed node id or secrets, or the old token refused |
| F4 | A/B update keeps /data | A marker file with random content is written to `/data/onemind/f4-marker`; the battery's `good` bundle (v2) installs to slot B; after the reboot the gate logs `RESULT mark-good slot=B version=2`; then, on slot B: the marker is byte-identical, `ONEMIND_VERSION` is `2`, the console shows `already configured` and no new owner token, the F1 owner token still gets 200 on `/v1/nodes` with the same `node_id` listed, and `/healthz` returns 200 | No commit of B, a lost or changed marker, a re-run of first-boot configuration, or the old token refused |

## 3. Boards and verdicts for this task

- **x86_64-efi** (OVMF) and **arm64-efi** (AAVMF) run F0–F4.
- On a host without KVM the run uses TCG and says so. A gate deadline missed only because TCG is slower than the 300 s budget is reported as **BLOCKED (TCG timing)**, with the measured times, not as PASS; the same test must then pass on a KVM host (CI) before it counts.
- Required for this task's "done": F0–F4 PASS on x86_64-efi and F0–F2 PASS on arm64-efi; every other cell is reported, never required.

## 4. Amendment (2026-11-13): F5 and F6, hardening H-01 and H-12 on the booted image

**Status:** PRE-REGISTERED before F5/F6 were implemented in `firstboot.py` or run. F0–F4 above are unchanged. The sha256 of this file with this section is appended to `PREREGISTRATION.sha256`. **Serves:** `docs/security/HARDENING-BACKLOG.md` H-01 (Pod Security Admission on every namespace) and H-12 (Secrets encrypted at rest in the k3s datastore). The image ships both settings (`k3s.service`, `/etc/rancher/k3s/psa.yaml`); until now no test proved the running k3s honours them.

Both run on the slot-A boot from F1, after `/healthz` is 200 and before the F3 reboot, using the node's own `k3s kubectl`. No image is pulled: pod admission is checked with `--dry-run=server`, which runs the real admission chain but stores nothing.

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| F5 | PSA rejects a privileged pod (H-01) | In namespace `default` (no PSA label of its own, so the cluster default applies): `kubectl apply --dry-run=server` of a pod with `securityContext.privileged: true` is **refused** with a message containing `violates PodSecurity` and `baseline`; the same call for an ordinary pod with no `securityContext` is **accepted** (so the refusal is the policy, not a broken apply); the k3s unit's command line contains `admission-control-config-file=/etc/rancher/k3s/psa.yaml` | The privileged pod is admitted, it is refused for another reason, or the ordinary pod is refused |
| F6 | Secrets encrypted at rest (H-12) | `k3s secrets-encrypt status` reports encryption `Enabled`; a Secret `f6-probe` with a random 64-hex value is created in `default` and `kubectl get` returns that value (not a vacuous test); a raw read of the datastore files (`/data/k3s/server/db/state.db` and its `-wal`) finds the AES-CBC envelope prefix `k8s:enc:aescbc:v1:` at least once and the plaintext value **zero** times; the probe Secret is deleted afterwards | Status not Enabled, the value found in plaintext in the datastore, no envelope prefix, or the datastore file missing |

Required for this task's "done": F5 and F6 PASS on x86_64-efi (the board with the F0–F4 requirement); other boards are reported.

## 5. Amendment (2026-11-15): F7, F8 and F9, the mesh in the image (IMG-MESH-01, #292)

**Status:** PRE-REGISTERED before F7–F9 were implemented in `firstboot.py` or run, in the commit before the code that adds them. F0–F6 above are unchanged. The sha256 of this file with this section is appended to `PREREGISTRATION.sha256`. **Serves:** issue #292's "Done when" items (the hub gets a mesh address and serves HTTPS with the box CA; Headscale refuses an enrollment without a valid key; one box CA) and NETWORKING.md §4, §5, §7 (CORE-SEC-4 on the image hub's NATS).

All three run on the slot-A boot from F1, after F6 and before the F3 reboot, from the hub's own shell. `onemind-mesh-setup.service` runs after first boot, so F7 waits for it: the mesh address must appear within **600 s** of the start of F7, and `/healthz` over HTTPS within **300 s** after that. Nothing is reached outside the VM; the second Tailscale client in F7 runs in userspace networking with its own state in `/run`, and is stopped and removed afterwards.

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| F7 | The hub is on its own mesh and serves HTTPS with the box CA | `tailscale ip -4` prints one address inside 100.64.0.0/10; `curl --cacert /data/onemind/identity/ca.pem --resolve onemind.local:8443:127.0.0.1 https://onemind.local:8443/healthz` returns HTTP 200 (the certificate verifies against the box CA, by name); a **second** `tailscaled` (userspace networking, state under `/run`, no log upload, trusting only the box CA) runs `tailscale up --login-server https://control.onemind.internal:8444` with a made-up key of the right shape (`hskey-auth-` + 48 random hex) and exits **non-zero** within its 30 s timeout, and Headscale's node list (`headscale nodes list -o json` over its local socket) has the **same** number of nodes before and after, with no node named like the second client | No mesh address or one outside the range, HTTPS not 200 or not verifiable with the box CA, the made-up key accepted, or a new node registered |
| F8 | Hub NATS: own keys only, leaf port needs the box CA | On `127.0.0.1:4222` a client that sends `CONNECT` with **no** nkey gets `-ERR 'Authorization Violation'`; a client signing the server's nonce with the onemindd service seed (`/data/onemind/nats/keys/onemindd.nk`) gets `PONG`; on `<hub mesh IP>:7422` (after the plain-text `INFO`, the client upgrades to TLS trusting the box CA) a client with **no** certificate and a client with a certificate from a **different** CA are both refused (TLS alert, handshake error or close within 3 s), while a client with a certificate the **box CA** signed for the test (`BoxCA.sign_node_csr`, client auth) completes the handshake and is not refused within 3 s (the control); the test key and certificates are deleted afterwards; `nats.conf` contains no `password` | Any refusal missing, the onemindd key refused, the control refused, or a password in the config |
| F9 | One box CA | The sha256 of `/data/onemind/identity/ca.pem` equals that of `/data/onemind/gateway/tls/ca.crt`; `/data/onemind/identity/ca.key` does not exist; `openssl verify -CAfile /data/onemind/identity/ca.pem` accepts the gateway's `https.crt`, Headscale's `control.crt` and the NATS leaf listener's `nats.crt` | Two different CAs, a CA key in `identity`, or a certificate not from the box CA |

Required for this task's "done": F7–F9 PASS on x86_64-efi. They are written without having run QEMU (no KVM where they were written); a harness bug found on the first run may be fixed and re-run once, named as such, under §1's rule.

## 6. Amendment (2026-11-21): F10, the rescue console on the booted hub (CORE-UPDATE-9, #278)

**Status:** PRE-REGISTERED before F10 was implemented in `firstboot.py` or run, in the commit before the code that adds it. F0-F9 above are unchanged. The sha256 of this file with this section is appended to `PREREGISTRATION.sha256`. **Serves:** issue #278's second "Done when" item (on a booted image hub with k3s stopped, the owner gets the rescue page). The image ships `onemind-rescue.service` and first boot enables it on the hub role; until now no test proved the running unit answers.

F10 runs on the slot-A boot from F1, after F9 and before the F3 reboot, from the hub's own shell. It uses the owner token printed on the console in F1. Nothing is reached outside the VM. `k3s.service` is stopped by the test and started again at the end, so F3 and F4 judge the same box as before.

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| F10 | Rescue console answers with k3s stopped | `systemctl is-enabled onemind-rescue` prints `enabled` and `is-active` prints `active`; with `systemctl stop k3s` done and `is-active k3s` not `active`: `curl --cacert /data/onemind/identity/ca.pem --resolve onemind.local:7443:127.0.0.1 https://onemind.local:7443/` returns HTTP **401** without a token (the certificate verifies against the box CA, by name) and HTTP **200** with `Authorization: Bearer <F1 owner token>`; `/status.json` with the token returns HTTP 200 and valid JSON; after `systemctl start k3s` the unit is still `active` | The unit not enabled or not active, a certificate that does not verify, anything other than 401 without the token or 200 with it, k3s still active when asked, or the unit stopped by k3s stopping |

Required for this task's "done": F10 PASS on x86_64-efi. It is written without having run QEMU (no KVM where it was written); a harness bug found on the first run may be fixed and re-run once, named as such, under section 1's rule. The battery tier is the first-boot battery (`make firstboot`, run by CI's `image` and `battery` workflows with F4 as the upper limit, which includes F10); the A/B battery T1-T11 does not boot the OneMind layer.

## 7. Amendment (2026-11-21): F11, the starting page and the hand-over to the gateway (P0 "starting page and faster gateway start")

*Renumbered from section 6 / F10 to section 7 / F11 when it was combined with the #278 amendment (also written as section 6 / F10) on release/next, 2026-11-21. No criterion, threshold or procedure changed; only the ID and section number.*

**Status:** PRE-REGISTERED before F11 was implemented in `firstboot.py` or run, in the commit before the code that adds it. F0–F10 above are unchanged. The sha256 of this file with this section is appended to `PREREGISTRATION.sha256`. **Serves:** the finish-audit item "starting page and faster gateway start after boot" (image speed audit, item 5 and 6); #234 (OneMind running live). **First run:** CI's image workflow (no KVM where it was written).

F11 runs on the slot-A boot from F1, after F9 and before the F3 reboot, from the hub's shell. It restarts the **front door** on purpose: it stops `onemind-gateway.service` and `onemind-starting.service`, then starts `onemind-starting.service` (which holds `:443` and `:8443` with the box certificate) and, at once, `onemind-gateway.service`. A probe in the guest (the gateway venv's Python, standard library only) opens a TCP connection to `127.0.0.1:443` every 100 ms and, for each connect that succeeds, does a TLS request and records the HTTP status and whether the header `X-OneMind-Starting: 1` is present. It stops at the first response from the gateway itself (HTTP 200 on `/healthz` over HTTPS, no such header) or after **180 s**.

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| F11 | Starting page, then the gateway, never a refused connection | The probe ends with the gateway's own HTTP 200 within 180 s; the **first** successful connect is answered by the starting page (HTTP 503 **with** `X-OneMind-Starting: 1`) or directly by the gateway; once any connect has succeeded, **no later connect is refused or reset** (no `ECONNREFUSED`, no reset, until the probe's end); no response with the marker header has status other than 503; the gateway unit's `After=` and `Wants=` lines contain no `network-online.target`; the elapsed seconds from the start command to the first gateway 200 (**time to dashboard**) are recorded in the verdict detail and in the run's `perf-dashboard.json`, and are at or under `time_to_dashboard_s` in `test/perf/budget.json` | A refused or reset connect after the first success, a page answering anything but 503, no gateway 200 in 180 s, `network-online.target` in the gateway's ordering, or a time over the budget |

Required for this task's "done": F11 PASS on x86_64-efi in CI's image workflow. The time budget is a ceiling set from the first CI run, so it starts generous (TCG is slower than hardware); tighten it from real runs.

## 8. Amendment (2026-11-22): F12, the gateway reaches the host helper (#875 mount-host-socket)

**Status:** PRE-REGISTERED before F12 was implemented in `firstboot.py` or run, in the commit before the code that adds it. F0–F11 above are unchanged. The sha256 of this file with this section is appended to `PREREGISTRATION.sha256`. **Serves:** issue #875 (the gateway reaches the host helper on a real box, reports `host helper: reachable|missing` in `GET /v1/status`, and starts no host action when it is missing). **First run:** CI's image workflow (no KVM where it was written).

Why here and not in the A/B battery: the gateway is not a k3s pod. In the image it is `onemind-gateway.service` (user `onemind`), and it reaches `/run/onemind/host.sock` (made by `onemind-host.socket`, mode 0660 root:onemind) through that unit; the host helper admits root and the gateway's uid only (`SO_PEERCRED`). The A/B battery T1–T11 does not boot the OneMind layer, so the only booted hub with a gateway is this first-boot battery.

F12 runs on the slot-A boot from F1, after F11 and before the F3 reboot, from the hub's shell, with the owner token from F1. Nothing is reached outside the VM. It stops the host helper on purpose and starts it again at the end, so F3 and F4 judge the same box as before.

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| F12 | The gateway reaches the host helper; without it, it says so and starts nothing | Within 120 s, `GET /v1/status` on :8080 with the owner token returns HTTP 200 with `host.helper` = `reachable`, `host.state` = `ok` and `host.hostname` equal to the output of `hostname` in the guest (one harmless host read: the answer comes from the host helper over the socket); then, with `systemctl stop onemind-host.service onemind-host.socket` done and `/run/onemind/host.sock` removed: `GET /v1/status` returns HTTP 200 with `host.helper` = `missing`, `host.state` not `ok`, `host.hostname` null and a `host.summary` that starts with `host helper: missing` and contains no `/run/`; and `GET /v1/os/updates` returns HTTP 200 with `install.available` false, `install.reason` = `engine_unreachable` and a plain-text `install.message` (no `Traceback`, no `Errno`, no `/run/`); after `systemctl start onemind-host.socket`, `host.helper` is `reachable` again within 60 s | Any status other than 200, `reachable` never seen before the stop or after the restart, a hostname that differs, `reachable` or `ok` while the socket is gone, a summary or message that leaks a path or a traceback, or the install reported available without the helper |

Required for this task's "done": F12 PASS on x86_64-efi in CI's image workflow. It is written without having run QEMU (no KVM where it was written); a harness bug found on the first run may be fixed and re-run once, named as such, under section 1's rule.

## 9. Amendment (2026-11-24): F13, disk and admin tools are on the box (Step 2 PRs 4 and 7)

**Status:** PRE-REGISTERED before F13 was implemented in `firstboot.py` or run, in the commit before the code that adds it. F0-F12 above are unchanged. The sha256 of this file with this section is appended to `PREREGISTRATION.sha256`. **Serves:** `internal/storage/smart.go` calls `smartctl`, which was not installed; the owner's shell had no gdisk, btrfs, ping, rsync and the like. **First run:** CI's image workflow.

F13 runs on the slot-A boot from F1, after F12 and before the F3 reboot, from the hub's shell. It changes nothing on the box and reaches nothing outside the VM.

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| F13 | The disk and admin tools run, and smartd is masked | In the guest: `smartctl --version` and `smartctl --scan` exit 0 and `smartctl -H` on the root disk runs and prints a `smartctl` banner (a virtual disk may say SMART is unavailable; that is fine, a missing command is not); `sgdisk -p` on the root disk exits 0 and lists a partition table; `btrfs --version` exits 0; each of `jq`, `htop`, `rsync`, `nano`, `less`, `ethtool`, `dmidecode`, `lspci`, `lsusb`, `ping` answers its version flag with exit 0; `/usr/share/bash-completion/bash_completion` exists; `systemctl is-enabled smartmontools.service` and `smartd.service` both say `masked` | Any command missing or exiting non-zero, no partition table listed, or smartd not masked |

Required for this task's "done": F13 PASS on x86_64-efi in CI's image workflow.
## 11. Amendment (2026-11-24): F15, the owner shell (Step 2 "Debian bones", PR 2: openssh-server, sudo, libpam-systemd)

*Renumbered from section 9 / F13 to section 11 / F15 on 2026-11-25: the parallel Step 2 lanes (clock, disk and admin tools) took section 9 / F13 and the next ones for their own checks. No criterion, threshold or procedure changed; only the ID and section number.*

**Status:** PRE-REGISTERED before F15 was implemented in `firstboot.py` or run, in the commit before the code that adds it. F0-F12 above are unchanged. The sha256 of this file with this section is appended to `PREREGISTRATION.sha256`. **Serves:** the Debian-bones plan (step 2, item 2 "Owner shell"), D-007 (Debian 13 is the shipping base), "AI never actuates without human approval" (the owner's own shell is key-only, with no password on the wire). **First run:** a KVM build worker, then CI's image workflow.

F15 runs on the slot-A boot from F1, after F12 and before the F3 reboot, from the hub's root shell on the serial console. Nothing is reached outside the VM: SSH is tried against `127.0.0.1` from inside the guest with the guest's own `ssh` client. The key pair and the console password are generated inside the guest from `/dev/urandom` for this test only; the image carries neither. It uses only the image's own tool `/usr/lib/onemind/onemind-owner`.

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| F15 | The owner shell: key-only SSH that starts with the first owner key, a console login on tty2, no baked password | **(a) Image:** the packages `openssh-server`, `sudo` and `libpam-systemd` are installed; `admin` is a user with uid 1000 and shell `/bin/bash`; `/etc/shadow` has **no** `admin` line (no password is baked); there are no `/etc/ssh/ssh_host_*` files in the slot; `/var/lib/extrausers/shadow` has no `admin` line before the test. **(b) No key, no sshd:** `systemctl is-active ssh.service` is not `active`, nothing listens on TCP 22 (`ss -ltn`), and `nft list chain inet onemind_host ssh` holds no `dport 22` rule. **(c) First key starts it:** after `onemind-owner key-add` of the generated public key returns 0, `ssh.service` is `active` within 60 s, TCP 22 is listening, the `ssh` chain holds `tcp dport 22 accept`, and the host keys are in `/data/onemind/ssh` with none in `/etc/ssh`. **(d) Key login works:** `ssh -i KEY -o BatchMode=yes admin@127.0.0.1 id -un` prints `admin`. **(e) Password login is refused:** after `onemind-owner password` has set a password, `ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password,keyboard-interactive -o BatchMode=yes admin@127.0.0.1 true` exits non-zero with `Permission denied (publickey)`; `sshd -T` reports `passwordauthentication no`, `kbdinteractiveauthentication no`, `permitrootlogin no`, `authenticationmethods publickey` and `allowusers admin`. **(f) tty2 login:** `getty@tty2.service` is enabled; a login through `/bin/login admin` on a pseudo-terminal with the right password reaches a shell running as `admin`, and in that shell `sudo` accepts the same password (`id -u` prints `0`); the same login with a wrong password prints `Login incorrect` and never reaches a shell. **(g) Kiosk still starts:** with `/data/onemind/kiosk/enabled` created, `onemind-kiosk.service` is `active` after `systemctl start` and logind holds a session for `onemind-kiosk`; the flag is removed and the unit stopped again at the end | Any sub-check false, a password or private key printed to the log, an `admin` shadow line found before the test, sshd active or listening without an owner key, password login accepted, a tty2 login accepted with a wrong password, or the kiosk unit failing |

Required for this task's "done": F15 PASS on x86_64-efi. It is written before it was run; a harness bug found on the first run may be fixed and re-run once, named as such, under section 1's rule. The first-boot battery runs with `-nic user,restrict=on`, so the guest cannot reach the outside: nothing here leaves the VM.
