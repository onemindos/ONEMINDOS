# Pinned versions and hashes (W4-1, k3s vs Podman footprint)

Compiled 2026-11-11 by the HYG agent from this folder's README, logs and the hash files the spike wrote in `<lab-dir>/w4-k3s-footprint/` at run time. Nothing was re-run.

| Item | Version / pin | Source in this folder |
|---|---|---|
| Host | Apple M5 Max, macOS 27.2; Lima 2.3.0 (`vz`) | README |
| Lab VM | Lima `template:debian-13`, image `debian-13-genericcloud-arm64-20261103-2651.qcow2`, sha512 `5d3ecec46fd29605db4084388a1e2eb82fd19a80202898f962840ea73793261de721e505e3877c829ae86c37fdd2f6c205b0b3b1337a89d0d4b98d9081adc0c2` (pinned by Lima); 4 vCPU / 4 GiB; `mounts: []` | README, `create.log` |
| Guest kernel | 6.12.115+deb13.1-cloud-arm64 | `run-1.log` |
| k3s | v1.37.2+k3s1, `k3s-arm64`, checked against the release `sha256sum-arm64.txt` (`k3s-arm64: OK`) | `run.sh`, `run-1.log` |
| k3s binary hash | not written by this spike; the same release file hashed by `../k3s-footprint-restore/` is `a779ccf1e5e2e33a62f5a29c2f1c0bbf99431e100579d4c10f0aa0742a6aa84b` | cross-reference |
| Podman | 5.4.2 (Debian 13 main) | `run-1.log` |
| Test images | `nginx:1.29-alpine` `sha256:5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de`; `redis:8-alpine` `sha256:71885d8cc6e42f2bc0aa2eb853bfc4be200b5108a46ac50e117ae1df0531fb80` | `run-1.log` |

## Run-time hash files (outside the repo)

The spike wrote `inputs.sha256` before the run (file time 2026-11-10T20:13-05:00, i.e. 01:13Z on 11-11) and `results.sha256` after it (21:17-05:00). Both are local file times, so they are self-attested, not proof.

| File | sha256 in `inputs.sha256` | sha256 in this folder now | Same? |
|---|---|---|---|
| README.md | `f4022c4cf633d786f2d9596b6d3154c689f865d84144d61e9409201d223768f1` | `f4022c4c…68f1` | yes: the committed criteria are the ones hashed before the run |
| run.sh | `abe438f6869f85549a667d144f92845a3433c54a4172d3514db72e506e0fccdb` | `abe438f6…ccdb` | yes |
| RESULT.md | (results file) `dc913f3a442433ba756f4bd5268e7969eb73c776bc68bebfe580235b048bfd8f` | same | yes |
| run-1.log | (results file) `c019bc07…c5c7` | `9cc9e09a…10c5` | no: host paths and VM addresses were masked before commit |

`SHA256SUMS` in this folder hashes the committed files as they are now.
