<!-- SPDX-License-Identifier: Apache-2.0 -->
# Plan: encrypt the NATS auth-callout requests (xkey)

**Status:** plan only, nothing built. Founder decision 2026-11-26: "add pr draft for it in detail for later". Issue [#1221](https://github.com/onemindos/ONEMINDOS/issues/1221). Follows the auth callout (#1199) and decision D-029 ("the gateway decides; NATS enforces").

## In plain words

When a program the hub's NATS does not know tries to connect (today: an AI agent), nats-server does not decide on its own. It sends the gateway a question: "this client, with this key and this signed one-time number, wants in." The gateway answers "no", or "yes, with these limits." That question and answer are the **auth callout**.

Today they are **signed** (nobody can fake them) but **not encrypted** (anyone who can read the AUTH account's messages could read them). They never leave the box: they travel over the hub's own loopback NATS, and only the gateway's responder may subscribe to them. So the gap is small, and closing it is hardening, not a fix for an open hole.

**xkey** is NATS's name for encrypting both directions with a per-server key pair, using the same kind of public-key encryption as libsodium's "box" (Curve25519 + XSalsa20-Poly1305).

## What the request carries today, and why encryption still helps

- The client's public key, a one-time nonce and the client's signature over it. No password, no secret.
- **Still worth encrypting:**
  - which agents try to connect, and when, is metadata;
  - a future client type might send a token in the request (for example a phone or app account in 1.1, D-029);
  - an answer carries a short-lived user JWT, which is a bearer credential for its lifetime (600 s by default).

## How xkey works in nats-server (UNVERIFIED: check every line against the v2.15.3 source before building)

The repo pins nats-server v2.15.3 (`os/versions.lock.yaml`).

1. **Config:** the `auth_callout` block in the hub accounts file gains `xkey: <curve public key>` (the gateway's key, "X..." prefix). Today's block has `issuer`, `account` and `auth_users` (see `internal/leaf/testdata/hub-accounts-callout.golden.conf`).
2. **Request:** nats-server seals each authorization request to that public key with its own per-server curve key, and sends its public key in a message header (expected name `Nats-Server-Xkey`).
3. **Answer:** the gateway opens the request with its private curve key, then seals its signed answer back to the server's public key from that header.
4. **Failure:** a request that does not open is never answered, so the client is refused (fail closed, as today).

## The build, step by step

1. **Dependency:** add PyNaCl to `core/pyproject.toml` and `core/uv.lock`, pinned and hash-checked.
   - PyNaCl is Apache-2.0 (compatible); it bundles libsodium (ISC).
   - Check that a wheel exists for every architecture the gateway runs on: x86_64 and arm64 Linux, Python 3.12.
   - Add it to the dependency review.
   - `cryptography` is not enough: it has X25519 but not NaCl's box construction.
2. **Key:** a new curve seed `callout-xkey.nk` in the gateway's custodian directory, next to `callout-issuer.nk` and `callout-service.nk` (`core/onemind_core/callout.py`).
   - It is made on first use, mode 0600, on `/data` (read-only root).
   - It follows D-029's "one key per purpose": it only ever encrypts callout traffic.
   - It is backed up like the other callout keys (D-020 emergency kit) or simply re-made: a new xkey only needs the accounts file rendered and reloaded again.
3. **Config render:** `natsconf.render_accounts` writes `xkey` into `auth_callout`. Golden files in `internal/leaf/testdata/` and the Go config tests are updated.
4. **Gateway responder:** `callout.Responder.handle` reads the server key from the header, opens the request, then runs the existing `answer()` checks unchanged (aud `nats-authorization-request`, exp with 5 s skew, a registered agent key, kill switch). It seals the answer to the server key.
   - A request that is not sealed, or does not open, is refused and written to the audit log as `nats.callout` with reason `xkey_open_failed`.
   - Plain requests are refused once xkey is on: no fallback, so a downgrade is impossible.
5. **Turning it on:** one switch, on by default for new boxes. Existing boxes switch on the next accounts render, which happens anyway on join, the kill switch or key changes. Machines are not affected: they use their pinned keys and never go through the callout.
6. **Docs:** update the "Not yet" paragraph in `callout.py`, `docs/security/THREAT-MODEL.md`, and this page's status line.

## Tests (one PR, about 300-500 lines)

- **Unit (core):**
  - seal/open round trip with a test server key;
  - a tampered request is refused;
  - a request sealed to the wrong key is refused;
  - a plain request is refused once xkey is on;
  - the answer opens only with the server key;
  - the audit line on failure.
- **Real server (Go, `internal/leaf`):** a callout test against nats-server 2.15.3 with xkey on:
  - a registered agent gets in;
  - an unknown one is refused;
  - the kill switch still cuts agents;
  - a wrong gateway xkey refuses everyone, which fails closed.
- **Golden files:** the accounts file with `xkey`, and the existing vector file `internal/leaf/testdata/callout-vector.json` extended with a sealed request.
- **Whole suites:** `make -C core test`, `go test -race ./...`, the unit suite, `deploy/check-pins.py` for the new pin.

## Out of scope

- Encrypting any other NATS traffic. TLS between machines and the hub is a separate topic: the mesh already encrypts it in transit.
- Per-app bus accounts, which arrive in 1.1 (D-029).

## Risks

- **A wrong or missing header name or seal format** makes every agent connection fail. That is safe (fail closed) but visible, so the real-server test is required before merge.
- **The extra native dependency** grows the gateway image slightly. Check the size against the perf budget (`test/perf/budget.json`, gateway idle memory; issue #1207).
