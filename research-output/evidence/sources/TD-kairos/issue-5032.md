# kairos-io/kairos#5032: epic: move Kubernetes and the provider bits to system extensions
state: open created: 2026-09-28T08:08:27Z closed: null

Split out of #4298 at @mudler's request, so that ticket stays about the sysext hub itself.

The hub now publishes extensions and an index, the agent resolves and installs them by name, and AuroraBoot bundles them into artifacts. What is not decided is how the Kubernetes layer stops being baked into the `standard` image and becomes an extension instead.

## Scope

| | Issue |
| --- | --- |
| named extension triggers: `k3s: true` should imply the k3s extension | #4967 |
| no Kubernetes extension exists yet: build and publish it from provider-kairos | #4968 |

## Open points to settle before any of this is implemented

- **What is in the extension.** provider-kairos, edgevpn and the k3s/k0s binaries are three things with three cadences. One extension or several?
- **Where the provider binary lands.** The agent already scans `/usr/local/system/providers`, so an extension can supply it without a new lookup, but nothing pins which path is the contract.
- **Config surface.** `k3s: true` implying an extension install overlaps with #3604 (unifying the Kubernetes attributes into a single block). The trigger cannot be designed before that block is.
- **The `standard` image.** Does it keep existing as a pre-baked convenience, or does it become core plus a bundled extension? That decides whether kairos-init still installs Kubernetes at build time.
- **Signatures.** A node outside Trusted Boot needs `extensions.ignore_signatures` to merge an unsigned extension today. Shipping Kubernetes this way makes that the default path for every standard user, not an opt-out for an edge case.
- **Upgrade and rollback.** #4969 has no defined guarantee for independently upgraded extensions. Kubernetes is the case where that matters most.
- **OpenRC flavors.** #4970 is still open, so Alpine cannot consume the artifacts at all.

Carrying the `triage` label: these points need a planning discussion before the sub-issues are picked up.

