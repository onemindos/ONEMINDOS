---
pr: pending
branch: claude/fix-gateway-idle-memory-3
---
Gateway memory and cold start on installed hubs (perf-smoke idle_memory_mib.gateway): uv's managed Python ships its standard library without bytecode, and the gateway cannot write any under /opt/onemind/python, so every start compiled about 200 stdlib modules from source and kept about 4 MiB more private memory. deploy/install.sh (both the build-on-box and the bundle path) and deploy/bundle.sh now compile the standard library once at install, as the image already does. Measured on a Linux build worker with the installed layout: idle gateway 116 to 112 MiB.
