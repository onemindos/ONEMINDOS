---
pr: pending
branch: ma/train-core-batch-part-a
---
Founder-authorized merge train, core batch part A (Refs #234): lands fourteen approved branches on release/next in one go, in order: the core integration (#1166), the log viewer, inputs-forget, passkey sign count and Work repeat time zone follow-ups (#1169, #1170, #1171, #1176), Work management (#1256), the gateway permissions stack (#1200 to #1205), the Permissions screens (#1271 to #1276), the NATS stack up to the signed policy snapshot (#1165, #1187, #1189, #1199, #1210), the Kanidm decision D-030 (#1163), the gateway idle-memory fix (#1195), the CI build cache (#1181), the Dell install kit (#1164) and the CI speed-up (#1180). Conflicts keep both sides; the OpenAPI spec is regenerated, never hand-edited. One combination fix: a #1166 node-exposure test now files a real write type, because the permissions stack refuses a type with no risk class before it is filed.
