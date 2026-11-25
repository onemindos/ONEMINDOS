---
pr: pending
branch: claude/nats-n3-observer
---
The hub now watches its own message bus. A read-only observer user in a new NATS system account (SYS) hears only the server's connect, disconnect and refused-sign-in announcements and cannot publish; the gateway turns them into fabric.connect, fabric.disconnect and fabric.auth_failed audit lines (no client addresses, rate limited per key) and raises security alerts for an unknown key, a removed key that keeps retrying and a machine that keeps reconnecting. The observer key is made at install and first boot like the other service keys. Read it with GET /v1/fabric/events, onemind fabric events, or the new Security events card in Settings > About; the alert on/off switch is the existing security notification topic. Checked against a real nats-server 2.15.3, which also showed that a refusal sends a second DISCONNECT announcement that the observer drops. Plan N3, issue 620.
