---
pr: pending
branch: feat/agent-gateway-ca
---
Hardening H-05, the last piece: when the gateway serves HTTPS with the box CA, each agent app's Secret now also carries that CA (public PEM) as ONEMIND_GATEWAY_CA next to ONEMIND_GATEWAY_URL and ONEMIND_AGENT_TOKEN, and the Python, Go and TypeScript SDKs' from_env verify TLS against it (that CA only, verification never disabled; a malformed value is an error). The TypeScript client does this on Node through a small node:https fetch, with no new dependency.

Agent URL and DNS: pods verify the gateway against the box CA only, and the gateway certificate has DNS names but no LAN IP, so the agent Secret no longer carries the LAN URL. A new ONEMIND_AGENT_URL setting (https://hub.onemind.internal:8443 from deploy/install.sh) is what pods dial; ONEMIND_PUBLIC_URL stays the browser URL. install.sh writes a coredns-custom ConfigMap so pods resolve hub.onemind.internal to the hub mesh address, the kubernetes executor maps that name statically for the egress NetworkPolicy, and the 2-VM suite gains N2-8 (a pod on the second node verifies the gateway).
