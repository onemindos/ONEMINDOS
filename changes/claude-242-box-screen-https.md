---
pr: pending
branch: claude/242-box-screen-https
---
The box's own screen (tty1) now points at https://address/ and https://name.local/ once a hub is running (ONEMIND_NET_TLS=1 in gateway.env, or role hub), instead of the plain http :8080 address that the gateway binds to loopback only. The setup wizard state still shows http :8080, and health is still probed on loopback. The Dell kit docs workaround in #537 can be deleted in a follow-up.
