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
