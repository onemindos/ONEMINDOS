# QEMU recovery bundle crypto criteria

**Status:** PRE-REGISTERED before implementation. Serves phase 2 of
`docs/architecture/BOX-EXPORT-IMPORT.md`, D-007 and D-029 (Refs #1287, Refs #234).
This check exercises the crypto backend. The fresh-disk restore criteria BX1–BX4
in the design apply when the restore workflow exists.

| ID | PASS | FAIL |
|---|---|---|
| F17 | On the booted Debian 13 hub in slot A, the installed gateway venv runs the pinned cryptography wheel. Using ephemeral keys and no network, it seals a multi-chunk payload to an ML-KEM-768 + X25519 kit recipient and a passphrase recipient, opens it independently with each, and rejects a changed ciphertext byte under the original owner-root fingerprint. | An unavailable algorithm, wheel version mismatch, incorrect plaintext, acceptance of the changed byte, or an absent success marker. |

Run with `make firstboot BOARD=x86_64-efi FUPTO=F2`. Require F17 to pass
on x86_64-efi. An unavailable runner or image is reported as blocked.
