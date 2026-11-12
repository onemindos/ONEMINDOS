# Refuter (security lens): C-W19-047, the DC-16 answer (E1 to E9, no OS fork)

**Refuter:** independent, security lens · **Date:** 2026-11-11 · **Read:** the conclusion text in `29-PLATFORM-ECOSYSTEM-MARKETPLACE.md` §1 and the cited claims (C-W19-001..009, C-TD-home-assistant-os-026, C-TD-umbrelos-026, C-TD-olares-028, C-W8-026, C-W7-033). I did not read the author's reasoning sections or other adversarial files first.

## Target

Under Tier A (Debian 13, RAUC read-only A/B + data partition, k3s, NATS), no plugin type needs an OS fork, provided E1 to E9 ship in release 1.

## Strongest counter-argument

"No fork" is reached by moving the trust boundary rather than by keeping it. E2 lets a user approve `hostNetwork`, `hostIPC`, device access, GPU access and real-time grants. Kubernetes' own Pod Security Standards treat host namespaces, privileged containers and hostPath as *known privilege escalations* that even the Baseline profile forbids (C-REF-W19-security-003). A plugin that holds one of these grants is effectively host root. The two concrete day-one cases cited are Home Assistant (host networking, and on umbrelOS also `privileged` with `/dev` and `/run/dbus`, C-W8-026) and ROS 2 shared memory (`--network=host --ipc=host`, C-W7-033). These are exactly the plugins that need E2. The runtime boundary under E2 has also failed repeatedly:

- runc CVE-2025-31133, -52565 and -52881 (2025-11-05) let a malicious image escape through mount races. runc 1.1.x and earlier were left unpatched (C-REF-W19-security-001).
- NVIDIAScape, CVE-2025-23266 (CVSS 9.0), turned the NVIDIA Container Toolkit's GPU hook into host root through `LD_PRELOAD`. It was the second toolkit escape after CVE-2024-0132 (C-REF-W19-security-002). This is the E2 "GPU grant" path.

So the read-only image (D1) still protects `/usr` at rest, but it does not protect the running host from a granted plugin. Through E3 (see the C-W19-001 file), such a plugin can also persist on the data partition. The design avoids a fork, but it has no tier where a host-privileged plugin is held to a higher bar than a user click.

This **does not refute** the "no fork" claim. Every extension point is a socket in the running system, not a change to the image. It weakens the *implied safety* of the nine-point set.

## New sources (failure, CVE)

| ID | Source | Opened |
|---|---|---|
| C-REF-W19-security-001 | runc GHSA-9493-h29p-rfm2 (CVE-2025-31133), https://github.com/advisories/GHSA-9493-h29p-rfm2 | yes |
| C-REF-W19-security-002 | Wiz NVIDIAScape CVE-2025-23266, https://www.wiz.io/blog/nvidia-ai-vulnerability-cve-2025-23266-nvidiascape | yes |
| C-REF-W19-security-003 | Kubernetes Pod Security Standards, https://kubernetes.io/docs/concepts/security/pod-security-standards/ | yes |

## Verdict: **WEAKENED**

The "no fork" claim holds. The E1 to E9 list is incomplete as a security contract:

- **E2 needs a privileged tier.** It must be an admission policy enforced in-cluster: PSA or Kyverno at Baseline by default, with any host-namespace, privileged or GPU grant allowed only to OneMind-countersigned plugins at a declared risk level.
- **Patch-currency gate.** The runtime and the GPU toolkit need a minimum version gate tied to E9 revocation, so a known escape CVE disables the grant.
- **The grant must be named in the release-1 contract.** That covers the grant, the reason for it and how to revoke it, and it belongs in the manifest schema now.

## What would flip it

- **To refuted:** a day-one plugin class whose host change cannot be expressed by E2, E3 or E4 (for example, needing a different kernel config or LSM policy in the base image), or a demonstration that E2-granted plugins cannot be contained to the point the product accepts. Either would force the image itself to change per plugin.
- **To upheld:** E2 specified with enforced admission (Baseline default, host grants only for countersigned plugins), plus a lab showing a Baseline-denied manifest is rejected and a revoked grant is removed on a live device.
