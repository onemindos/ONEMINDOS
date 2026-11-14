<!-- SPDX-License-Identifier: Apache-2.0 -->
# Image changes for app secrets (for the image-line stream)

**From:** `feat/app-secrets` ([SECRETS.md](SECRETS.md)) · **For:** whoever adds the gateway service to `os/` · **Why a note and not a diff:** `os/` belongs to the image-line stream while other streams build; `os/` has no gateway unit yet (2026-11-12).

The gateway needs one private, persistent file: the app secret-store key. On the image it should live with the other custodian keys on the data partition, so the restic `system` unit backs it up (BACKUPS.md §2, §6.4) and a restore onto new hardware can open the stored values.

## 1. Gateway environment
```ini
# /etc/onemind/gateway.env (or the image's equivalent drop-in)
ONEMIND_DATA_DIR=/data/onemind
ONEMIND_SECRETS_KEY_FILE=/data/onemind/custodian/secrets.key
# F-7 owner override: leave unset (off). Setting it to 1 is the founder's call, per box.
# ONEMIND_ALLOW_OWNER_OVERRIDE=1
```

## 2. Unit
- `ReadWritePaths=/data/onemind` (the gateway creates `custodian/` with mode 0700 and the key with 0600 on first start, and never overwrites it).
- The gateway user owns `/data/onemind/custodian`; no other service user needs to read `secrets.key`, except the backup agent when it snapshots the `system` unit (BACKUPS.md §2 lists the custodian directory there).

## 3. Not now: a TPM-sealed credential
The gateway also reads the key from a systemd credential named `onemind-secrets-key` (`LoadCredentialEncrypted=`), which can be sealed to the TPM. Do not switch to it yet: a TPM-sealed copy cannot be opened on replacement hardware, so the backup would still need the plain key (inside the encrypted restic repository). That needs a decision on how the backup agent exports it, together with CORE-SEC-5 (LUKS2 + TPM unlock).

## 4. Check after the change
```console
$ sudo ls -ln /data/onemind/custodian/secrets.key     # -rw------- owned by the gateway user
$ curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/v1/secrets/public-key
{"alg":"X25519","key":"…","key_id":"sk_…","sealed_alg":"X25519-AES256GCM"}
```
