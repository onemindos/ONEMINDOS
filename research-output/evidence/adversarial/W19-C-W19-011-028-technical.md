# Refuter (technical): W19 DC-16 TRUST ROOT (E9) EVIDENCE [C-W19-011, 012, 015, 021, 022, 023, 025, 026, 028, 033]

**Refuter:** independent, technical lens. **Date:** 2026-11-11. Read: the conclusion and the claim rows listed above.

## Target
OneMind installs only digest-pinned, publisher-signed, OneMind-countersigned plugins, publishes from CI only, and keeps a signed revocation list that disables to a safe state and never substitutes code.

## Strongest counter-argument
Signing, countersigning and pinning prove **who** published **which bytes**. They do not prove the bytes are benign, and a revocation list is only as good as its detection. The cited best-in-class reference, VS Code Marketplace [C-W19-023], has failed both ways since it introduced signing and scanning:
- **False negatives:** ransomware extensions "bypassed security reviews". `ahban.cychelloworld` added ransomware in v0.0.2 (2024-11-24), was reported on 2024-11-25, and "remained accessible for several months" with five more versions published (TechMonitor, 2025-03-21). https://www.techmonitor.ai/?p=415511
- **False positives:** in Feb 2025 Microsoft removed "Material Theme – Free" and "Material Theme Icons – Free" (~9M installs) and banned the publisher, without contacting him first (BleepingComputer, 2025-02-26). They were later reinstated as wrongly flagged (TechMonitor, same article). https://www.bleepingcomputer.com/news/security/vscode-extensions-with-9-million-installs-pulled-over-security-risks/
For a robot or physical-control OS, a false-positive kill that "disables to a safe state" still stops a working greenhouse or vehicle payload. The E9 design needs an **appeal and owner-override policy**, plus a defined meaning of "safe state" per plugin class. Without these, the kill list becomes an availability risk of its own.

## Check of the cited sources (rows only)
The cited rows are internally consistent and pinned to commits. C-W19-022 (Obsidian) is `partial` (JS-rendered page, archive gap), so do not lean on it alone. None of the cited examples is contradicted.

## Verdict: **UPHELD**
The trust-root design is the right baseline: every counter-example concerns detection and governance, not signing or pinning, and the conclusion already says "disables, never substitutes code". Amend E9 with: (a) publisher-notification and appeal SLA before a non-critical revoke; (b) owner override for local-only, air-gapped units; (c) the per-class safe state defined in the manifest. Signing is necessary but not sufficient: review and runtime sandboxing (E2) carry the safety.

## What would flip it
- **To WEAKENED:** a signed, countersigned, digest-pinned ecosystem (for example the VS Code Marketplace after signing) where a compromised **signing or countersigning key** led to mass malicious installs. That would show the countersignature adds a single point of failure without reducing risk. Or evidence that signed revocation lists in fleets (HACS, VS Code) commonly fail to reach offline devices, which matters for local-only OneMind nodes.
