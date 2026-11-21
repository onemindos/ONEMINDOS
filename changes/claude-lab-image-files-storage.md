---
pr: pending
branch: claude/lab-image-files-storage
---
Files and storage actions work on an image-built hub: the gateway now has ONEMIND_FILES_ROOT=/data/onemind/files (made on start and writable inside its sandbox) and ONEMIND_STORAGE_ENABLED=1, and a new onemind-storage.service runs onemindd storage serve on the hub. Before this the files roots route answered 503 storage_unavailable and storage actions were off (R530 lab run). Existing hubs pick up the settings when first boot next rewrites gateway.env.
