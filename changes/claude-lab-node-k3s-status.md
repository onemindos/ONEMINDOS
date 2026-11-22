---
pr: pending
branch: claude/lab-node-k3s-status
---
Fixed the node status API reporting k3s as role agent, ready false on a healthy image hub (R530 lab finding). The detector only looked for the Debian-package k3s paths, but the image keeps k3s data in /data/k3s and writes the admin kubeconfig to /run/k3s/k3s.yaml, so it never saw a server and never ran the readiness check. It now recognises both layouts and passes the image kubeconfig to `k3s kubectl get --raw /readyz`. A new test covers the image layout. Not done: plain `k3s kubectl` on the box still defaults to the gateway port because root's KUBECONFIG is unset; that is an image change left for a follow-up.
