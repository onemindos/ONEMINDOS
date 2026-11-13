---
pr: pending
branch: apps/fix-unready-apps
---
Market apps that failed the gate smoke test, diagnosed from real runs and local reproductions of the pinned images with the pods' security settings: Sonarr, Radarr and Prowlarr never started because the LinuxServer image only takes its non-root branch when /run is non-root owned, so the manifests now set LSIO_NON_ROOT_USER; PhotoPrism crash-looped on s6-overlay preinit, so it gets a writable /run; OpenClaw's probes required a ready field that /startupz does not return, so they now check status started. qBittorrent stays blocked: its 401 on the login page is correct and no fixed image exists. Tiers are untouched (only the gate sets them) and the other CVE and secret findings still block these apps. The app-scan workflows also gain an optional Docker Hub login that runs only when the secret is set and never for fork pull requests.
