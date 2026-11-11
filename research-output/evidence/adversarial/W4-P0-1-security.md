# Adversarial review: W4 P0-1 (security lens)

- **Conclusion under test (05-kubernetes-cluster-conversion-nvidia.md, P0-1):** Keep Kubernetes (k3s) as the app platform on every OneMind node with at least 4 GB RAM, and do not require it below that. Devices under 4 GB join as NATS leaf nodes with an MCP/MHS adapter. Stated confidence: medium-high (lab on a VM, not Pi silicon).
- **Cited claims:** C-W4-001, -003, -004, -042, -043, -044, and lab claims C-W4-076 to -081.
- **Refuter lens:** security (attack surface per node, insecure defaults, patch cadence, physical capture).
- **Date:** 2026-11-11. Re-check by: 2027-05-10.
- **Verdict: `weakened`.** Nothing I found shows k3s is the wrong platform for nodes with 4 GB or more. But the conclusion and its evidence are about footprint only, and the 4 GB gate was measured on a k3s with default, unhardened settings. A hardened k3s does more work (audit logging among other things), and running a full control plane on field devices someone can physically capture is a security cost the conclusion never prices. The decision holds only if those two gaps are closed.

## 1. Re-check of the cited sources

| Claim | Re-check | Status |
|---|---|---|
| C-W4-001, -003, -004 (k3s minimums and resource profile) | Pinned k3s-io/docs SHA as cited. Not re-run byte by byte; nothing in the security evidence contradicts them | Accepted |
| C-W4-042 to -044 (Olares 8 GB; umbrelOS and HA run Docker, not Kubernetes) | Accepted as context. They show that peer products on small hardware avoid Kubernetes, which supports the under-4 GB carve-out | Accepted |
| C-W4-076 to -081 (lab W4-1) | The lab ran k3s **with default flags** (and a "slim" variant that only disables addons). No CIS profile, no `secrets-encryption`, no audit policy and no `protect-kernel-defaults` were measured | **Accepted as measured. The scope gap is material (see section 3.1)** |

## 2. Strongest counter-argument

"Every node with 4 GB or more that runs k3s carries a full Kubernetes control plane and datastore: the API server on 6443, a kubelet, containerd/runc, an SQLite or etcd store holding every Secret, and a cluster-admin kubeconfig at `/etc/rancher/k3s/k3s.yaml`. On a robot, drone companion computer or field Jetson that can be captured, that is far more to steal and attack than Podman plus systemd. The lab measured Podman at 32 MiB with the same app. Kubernetes assumes nodes sit in a physically secure datacenter (arXiv 2405.10131). The OneMind threat model (C2/ISR, devices in the field) breaks that assumption. 'One OS' (F-14) does not require one control plane per device: those devices should be k3s *agents*, or Podman/quadlet hosts managed from a hub, and only hub-class nodes should run a server."

## 3. Findings

### 3.1 The footprint gate was not measured on a secure configuration
The k3s hardening guide (docs.k3s.io/security/hardening-guide, opened 2026-11-11) says k3s "will pass a number of the Kubernetes CIS controls without modification". Audit logging is **off by default** ("audit log configuration and audit policy must be created manually"). `protect-kernel-defaults` and the pod-security policy are opt-in, and controls 1.1.20, 1.2.9, 1.2.11, 1.2.21, 4.2.13 and 5.x still need manual remediation. The guide's own hardened config enables `secrets-encryption` explicitly. The lab's PASS rests on 2.50 GiB available and 2.75 GB/day written (C-W4-078). The write gate is 5 GB/day. Audit logging on an API server whose controllers write constantly adds writes, and the slim run already showed 6.06 GB/day (C-W4-080, a figure the lab says is not steady state). Whether hardened k3s still passes both gates on a 4 GB device is **unmeasured**.

### 3.2 k3s has a record of insecure defaults
The k3s-io/k3s advisory index and the GitHub Advisory Database (opened 2026-11-11) show:
- **GHSA-864f-7xjm-2jp2 / CVE-2025-46599** (2025-04-25, CVSS 6.8, CWE-1188 "Insecure Default"). In k3s 1.32.0-rc1 up to 1.32.4-rc1, a kubelet configuration change could enable the unauthenticated read-only port 10255 on a default online install, "exposing credentials".
- **GHSA-cxm9-4m6p-24mc** (2021). k3s bootstrap data was encrypted with an empty string when no token was supplied.
- **GHSA-m4hf-6vgr-75r2** (2023, High). An unauthenticated remote DoS against the apiserver/supervisor port 6443.
- **GHSA-jxr7-mqhw-9p98 / CVE-2026-54250** (2026-06-03, CVSS 5.8). A path traversal when restoring an etcd snapshot. Fixed in v1.35.3, v1.34.6 and v1.33.10. This matters for OneMind's restore path (06-backups), because a restored snapshot taken from an untrusted medium can write anywhere on the node.

Two of these four are insecure-default bugs that hit installs with **default** settings, which is exactly what the lab measured. On every node, OneMind must therefore pin its own explicit k3s config and not inherit upstream defaults.

### 3.3 The vulnerability load grows with the number of nodes
Each node with 4 GB or more ships its own bundled containerd and runc. The runc container escapes CVE-2025-31133, CVE-2025-52565 and CVE-2025-52881 (oss-sec 2025-Q4) needed runc 1.2.8, 1.3.3 or 1.4.0-rc.3, followed by a further batch (1.3.6, 1.4.3). In k3s those fixes arrive only through a k3s patch release. A fleet updated at user discretion (R-1) means that every lagging node is a container-escape target. Podman hosts have the same runc exposure, so this is **not** a reason to prefer Podman. It is a reason that OTA cadence (04-image-install-updates-rollback) is a precondition of P0-1.

### 3.4 The under-4 GB carve-out is a security positive
A NATS leaf with an adapter has a smaller attack surface than any Kubernetes node. This part of P0-1 is strengthened by the security lens, provided leaf credentials are per-device and revocable.

## 4. New sources (searched for CVEs, insecure defaults and failure; all opened 2026-11-11)

1. GHSA-864f-7xjm-2jp2 / CVE-2025-46599, k3s kubelet read-only port exposes credentials. https://github.com/advisories/GHSA-864f-7xjm-2jp2. PRIMARY.
2. k3s-io/k3s security advisories index (GHSA-jxr7-mqhw-9p98, GHSA-m4hf-6vgr-75r2, GHSA-cxm9-4m6p-24mc). https://github.com/k3s-io/k3s/security/advisories. PRIMARY.
3. GHSA-jxr7-mqhw-9p98 / CVE-2026-54250, path traversal in etcd snapshot restore. https://github.com/k3s-io/k3s/security/advisories/GHSA-jxr7-mqhw-9p98. PRIMARY.
4. k3s CIS hardening guide: audit off by default, manual controls listed. https://docs.k3s.io/security/hardening-guide. PRIMARY.
5. Thijsman et al., "Trusting the Cloud-Native Edge: Remotely Attested Kubernetes Workers", arXiv 2405.10131 (2024-05-16). https://arxiv.org/abs/2405.10131. PRIMARY (peer research).
6. oss-sec, runc breakouts CVE-2025-31133/52565/52881. https://seclists.org/oss-sec/2025/q4/138. PRIMARY. Seen in search results only, not opened, so it is used as corroboration only.

## 5. What would flip the decision

- **Toward `refuted`:** on Pi 5 / Jetson silicon, a hardened k3s (the hardening-guide profile plus `secrets-encryption`, an audit policy and `protect-kernel-defaults`) running the reference app leaves less than 2.0 GiB, or writes more than 5 GB/day, at steady state. The 4 GB floor would then be really 8 GB, or Kubernetes would belong only on hub nodes. A second signal: a k3s-specific **unauthenticated RCE** advisory, or a third insecure-default advisory within 12 months.
- **Toward `upheld`:** a lab re-run of W4-1 with the hardened profile that still passes both gates, plus a written node-role rule: field devices that can be captured run the k3s **agent** only, with no server, no datastore and no admin kubeconfig on disk, and they are enrolled with TPM-bound or short-lived credentials.
