<!-- SPDX-License-Identifier: Apache-2.0 -->
# Local private-tier artifact signing (E9, issue 180)

After `onemind plugin pack SOURCE --output LAYOUT`, run:

```sh
onemind plugin sign LAYOUT --digest sha256:ARTIFACT_DIGEST --key PRIVATE_KEY --output SIGNATURE
onemind plugin inspect LAYOUT --digest sha256:ARTIFACT_DIGEST --key PUBLIC_KEY --signature SIGNATURE
```

The digest must be the exact immutable value returned by pack. Signing checks the complete layout, including bounded extraction and bundle validation. The signed message is UTF-8 `onemind.plugin.artifact/v1` plus newline, the exact SHA-256 digest plus newline, then the raw OCI manifest bytes; signatures are base64-encoded Ed25519, SHA-256 ECDSA ASN.1 or SHA-256 RSA PKCS#1 v1.5, using the existing Sigstore cryptographic implementation with that same purpose binding. Legacy signatures over raw manifest bytes alone are refused. Supported keys are unencrypted PKCS8 PEM, Ed25519, RSA at least 2048 bits or NIST EC at least 256 bits. Key input is bounded to 16 KiB and must be a regular owner-only file. No key is generated or enrolled by signing. Signature output must be a new file.

The command prints only the artifact digest, public-key fingerprint and signature path. Its JSON result keeps `verified: false`: the box must separately check active owner enrollment, scan freshness, revocations and compatibility, and obtain explicit installation approval. A detached signature from an arbitrary key cannot authorize installation.
