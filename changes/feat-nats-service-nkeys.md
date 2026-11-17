---
pr: 269
branch: feat/nats-service-nkeys
---
The hub NATS has no passwordless user any more. The gateway and the hub's onemindd each sign in with their own NATS key (nkey), made by the installer, with each seed readable only by its own service. Any other local process without a listed key is refused, which a real nats-server test proves (no key, an unknown key, a forged signature, a node key on the client port). Nodes already had their own keys and TLS on the leaf link. The check tools natscheck, node-check and verify sign in with a key too. Boxes without service keys (the dev compose stack) keep the old loopback user until reinstalled (CORE-SEC-4, issue 161).
