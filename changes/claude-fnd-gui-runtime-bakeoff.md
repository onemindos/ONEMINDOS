---
pr: pending
branch: claude/fnd-gui-runtime-bakeoff
---
One streaming runtime for desktop apps, first slice (Refs #786): a shared desktop base in apps/_bases/desktop (Neko 3.2.0 on Debian 13, pinned by digest, uid 1000, setuid bits stripped, Widevine removed, licence notices in the image) that the app factory checks (app-factory base-check, run in CI) and builds with a Trivy scan and a CycloneDX SBOM (app-factory base-build); validate-apps check 12, which refuses a desktop app that runs as root, privileged or with added capabilities, or ships a second runtime, and allows the runtime's own login to be off only when the NetworkPolicies the gateway writes for it admit the gateway alone; and the bake-off kit in test/gui (an Obsidian test image built from the vendor file at build time, never committed, and bakeoff.py, which checks clipboard both ways, audio, resize and reconnect in headless Chromium, records latency and picks the runtime in the order Neko, Selkies, Xpra).
