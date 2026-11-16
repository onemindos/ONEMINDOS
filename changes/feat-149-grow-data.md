---
pr: 318
branch: feat/149-grow-data
---
IMG-02 part 1: the data partition now grows to the real disk at first boot on every GPT board (x86, arm64, vm), so an image written to a 256 GiB NVMe uses the whole disk instead of stopping at 32 GiB. A small boot service, enabled by a wants symlink, rewrites only the data partition's table entry (same start, GUIDs and name) and grows the ext4 online; it does nothing unless the data partition is the last one and there is free space behind it, and it never shrinks, moves or re-creates anything. Making slot B at first boot (the smaller download) and the battery at 32, 64 and 256 GiB are the next parts.
