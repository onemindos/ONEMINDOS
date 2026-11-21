---
pr: 451
branch: codex/180-plugin-cli-fold
---
Consolidates plugin scaffolding, deterministic OCI packaging, pinned content inspection and private-key signing. Artifact signatures bind an explicit plugin purpose and digest; supplied signatures are checked before extraction. Real Ed25519, RSA and ECDSA tests cover malformed input, wrong purpose, tampering and safe key handling. Packaging and signing do not authorize installation. Includes a technical handoff identifying verified review units and the remaining trusted-install integration.
