---
pr: pending
branch: feat/dependency-netpol
---
Apps that declare a dependency can now reach it on a real box without weakening the per-app default-deny network policy (H-04). When the owner approves installing, updating or configuring an app whose dependency is met by an installed app, the gateway opens one narrow path: egress from that app's namespace to the provider's namespace, and a matching ingress allowance in the provider's namespace, TCP only, on the provider's web port or a new optional `port` on the dependency (contract §12.22, dependency network paths). Namespaces are matched by their exact name, with no wildcard, IP range, UDP or host port. The plan card lists every path it opens, the paths are part of the plan fingerprint so a different provider or port needs a fresh approval, and a standing approval never opens one. Removing the dependent closes both sides. This unblocks Library Chat reaching Kiwix and Ollama.
