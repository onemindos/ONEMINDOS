---
pr: pending
branch: feat/251-node-wake
---
Adds a Nodes-card Wake-on-LAN request through the existing owner approval ledger (#251, locked human-approval rule). Agents may request but cannot approve. Administrators provision a local ONEMIND_WAKE_TARGETS_FILE JSON map keyed by known node ID, with a unicast MAC and RFC1918 LAN network CIDR (prefix 16–30); the destination is that network's broadcast on UDP port 9, never request-supplied. Missing or invalid configuration disables wake. Approval and dispatch recheck the target fingerprint; one packet is sent with no automatic retry, and only a fresh heartbeat proves the node is awake. Generated SDKs and isolated backend/UI tests cover requests, approval, transport bytes and unavailable states. Partial hardware acceptance: no physical packet or real dashboard wake was executed; the sleeping-node acceptance criterion still needs a founder-authorized hardware test on a correctly configured LAN.
