---
pr: pending
branch: claude/fnd-learning-nats-guide
---
Learning note docs/learning/nats-fabric.md (#625): the NATS fabric in plain words for the founder. It covers subjects, accounts, leaf nodes, JetStream, domains, sources, the leaf outbox, monitoring, what survives a link cut and the proposed two-door agent rule. It has a diagram of the hub, leaves and accounts exactly as natsconf.py writes them, cites docs.nats.io, nats-server v2.15.2 source or the W8-1 and FB-3 lab evidence in every section, and flags four places where the contract and the code disagree (outbox names, per-node auth wording, cross-account sourcing, leaf memory and ping settings).
