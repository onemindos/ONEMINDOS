<!-- SPDX-License-Identifier: Apache-2.0 -->
# DC-F2 steelman of the runner-up: one big cluster over the mesh

**Argued for one cluster, as instructed.** One Kubernetes API for everything is simpler for the owner and for agents; k3s officially supports agents on other networks and even ships a Tailscale integration with a self-hosted control server [C-FB4-001, C-FB4-002]; NETWORKING §8 already puts k3s on mesh addresses with WireGuard flannel, so a worker at the cabin "just works"; KubeEdge shows one control plane can schedule 100,000 nodes [C-FB4-008]; scheduling across sites (burst to a friend's GPU, F-6) is native; no fleet engine, no summaries, no federation to build.

**Why it still loses.** k3s says "all servers should be in the same location" and warns about latency [C-FB4-001]; when the WAN drops, a remote site loses its control plane and Kubernetes starts evicting its workloads from `NotReady` nodes; a field kit or vehicle must keep full authority offline (`08-…`; context/02 §10 "do not stretch consensus across WAN links"); one cluster is one blast radius across every owner; Headscale's scope ends at one small tailnet [C-FB3-006, C-FBREF-006].

**What would make it win:** a site set that is always online (for example several cloud regions of one owner) — which is exactly the exception kept in `05-…` (always-online cloud workers).
