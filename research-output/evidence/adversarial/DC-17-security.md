# DC-17 · One OS from Pi 5 to GPU cluster (F-14, G5) — refuter (security lens)

**Refuter:** REF3, security lens, 2026-11-11. Inputs read: the DC-17 question, the W2 answer (`03-base-os.md` §10, `qbank/W2.md` Q334, `qbank/W4.md` input), the current G5 row in `01-FOUNDATION-DECISION.md` §tie-break (COND for both Debian and Ubuntu, a tie) and cited claims C-W2-053, -026, -028, C-LAB-k3s-footprint-restore-007.

## Conclusion under test
G5 is **CONDITIONAL** for the proposal: the same k3s apps and management plane run from a 4–8 GB Pi 5 (k3s idle ≈ 0.9–1.1 GiB) to RTX/DGX GPU servers; Jetson is a second OS family (or a second Ubuntu release). Debian and Ubuntu tie on G5.

## Strongest counter-argument
G5 was scored on footprint and userland family. It ignores that **the two ends of the range cannot share one security baseline**, so "one OS, simple at every scale" hides a trust split that the founder's promise implies away.

1. **The small end has no hardware root for secrets.** A Pi has no TPM and no hardware-protected key store; its disk key is in OTP, "protected by software mechanisms" (W6's own reading, C-W6-056/-058). k3s keeps its secrets-encryption AES key in a plain file, `/var/lib/rancher/k3s/server/cred/encryption-config.json` [C-REF3-DC-security-008], next to the cluster CA and join token. A Pi 5 running the k3s *server* — the default for a single-box Lite/Edge tier — therefore protects every app secret, and any later cluster CA, with software-only key storage. An x86 or Jetson node can seal the same material to a TPM/fTPM. Same OS, different assurance.
2. **Encryption of secrets is not a property you get later for free.** Secrets encryption is opt-in; enabling it on a server started without it was only supported from the March 2026 k3s releases (v1.33.10/v1.34.6/v1.35.3) and needs a restart and re-encrypt [C-REF3-DC-security-008]. "Start on a Pi, grow into a cluster" must ship with it on from the first boot, or fleets accumulate plaintext-at-rest secrets in kine/SQLite.
3. **The large end carries a different class of risk.** GPU servers run the NVIDIA Container Toolkit / GPU Operator, whose createContainer hook gave host root from an untrusted image (NVIDIAScape, CVSS 9.0; GPU Operator ≤ 25.3.1) [C-REF3-DC-security-007]. A multi-tenant GPU cluster needs runtime isolation (for example, no untrusted images on GPU nodes, or sandboxed runtimes) that a home Pi does not. One image family with one default policy is either too loose for the cluster or too heavy for the Pi.
4. **Mixed clusters inherit the weakest node.** If a Pi joins the same k3s cluster as GPU servers (the "same product at every scale" story), it holds the join token and receives the secrets of pods scheduled on it; a stolen Pi with software-only disk keys is the cheapest path into the cluster.

These points apply equally to Debian and Ubuntu (neither gives the Pi a TPM; both use the same toolkit), so they **do not break the tie**.

## Verdict: **upheld** (COND is the right grade; a security condition is added)
G5 stays CONDITIONAL and the Debian/Ubuntu tie stands. Add to the G5 condition: (a) per-tier trust roles — Pi 5 nodes are lower-assurance, never a server/CA holder in a cluster that also holds GPU or fleet secrets; (b) `--secrets-encryption` on from first boot on every tier; (c) a GPU-node runtime policy (patched toolkit, image allowlist) distinct from the Pi profile. Without these, "simple at every scale" would be achieved by giving the cluster the Pi's assurance level.

## What would flip it
- **To weakened (G5 toward FAIL for all candidates):** a design requirement that a single Pi 5 must be able to act as the control plane of a mixed cluster holding fleet or GPU-tier secrets — the hardware cannot meet that at the x86/Jetson assurance level.
- **To a non-tie:** a candidate base gives Pi-class nodes a hardware-backed key store (for example, a CM5 carrier with a discrete TPM supported by the base out of the box) that the other base does not.

## New sources (opened)
- k3s docs, Secrets Encryption and `k3s secrets-encrypt` — https://docs.k3s.io/security/secrets-encryption , https://docs.k3s.io/cli/secrets-encrypt [C-REF3-DC-security-008]
- Wiz, NVIDIAScape CVE-2025-23266 — https://wiz.io/blog/nvidia-ai-vulnerability-cve-2025-23266-nvidiascape [C-REF3-DC-security-007]
