---
pr: pending
branch: feat/274-image-nats-accounts
---
CORE-SEC-5 (#274), on top of #304: tests that pin the image first boot's NATS setup to what deploy/install.sh does. The generated hub config has a loopback client port only, a leaf listener with TLS from the box CA and `verify: true`, and the per-node accounts include; no user, password or token appears in it or anywhere in the first-boot source. The two service nkeys are in the accounts file, node accounts are separate, and nats-server itself accepts the hub config. A hub set up before the mesh keeps its own config across an update and is not rewritten by the mesh step. No behaviour change beyond #304: #304 already removed the shared node password and the nats_tls switch.
