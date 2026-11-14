---
pr: pending
branch: feat/agent-gateway-ca
---
Hardening H-05, the last piece: when the gateway serves HTTPS with the box CA, each agent app's Secret now also carries that CA (public PEM) as ONEMIND_GATEWAY_CA next to ONEMIND_GATEWAY_URL and ONEMIND_AGENT_TOKEN, and the Python, Go and TypeScript SDKs' from_env verify TLS against it (that CA only, verification never disabled; a malformed value is an error). The TypeScript client does this on Node through a small node:https fetch, with no new dependency.
