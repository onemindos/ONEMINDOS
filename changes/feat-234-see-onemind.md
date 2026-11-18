---
pr: 315
branch: feat/234-see-onemind
---
See OneMind (DEV-SEE-01, part 1): the arm64 image now also comes as a compressed qcow2 that UTM imports on an Apple Silicon Mac. A nightly workflow publishes the newest green image run as a labelled DEV BUILD pre-release (Mac qcow2, Beelink installer stick, droplet qcow2; throwaway keys, signs nothing). Step-by-step guides for the Mac, the Beelink USB stick (with what a 2 core 8 GB box can and cannot run) and the droplet are in docs/see-onemind, and the droplet kit now sets the hub role in user data and puts a Cloud Firewall before the first boot, closing the cluster ports 4222, 6443, 10250 and 8472.
