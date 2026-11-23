---
pr: 947
branch: claude/ready-engine-feed
---
Engine feed (#619), part 1: GET /v1/engine reads the hub NATS server's loopback monitor (varz, connz, jsz, healthz, leafz) with a 2 second cache and returns connections per account, each machine's leaf link and outbox lag, JetStream used against its cap (state refused when NATS runs JetStream without a cap) and slow consumers. The owner sees everything, a machine its own account and link, everyone else a summary; children, plugins and automations get 403. No credential, client address, file path or subject is ever returned. The Settings panel and onemind nats status follow in part 2.
