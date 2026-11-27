---
pr: pending
branch: ma/fix-app-page-wording-cpu-and-memory-cli-
---
Three live bugs from the founder's audit of a real hub (Refs #1232, Refs #234). The installed-app page no longer says Open skips the OneMind sign-in: Open goes through it. Machine CPU and temperature on Home were always blank because the dashboard read flat fields while the node heartbeat nests them under metrics; they are now lifted from metrics (null stays null). The app metrics route now says why a CPU or memory figure is missing (no runtime, pods unreadable, metrics-server silent or has no reading yet) in a new reason field shown on the app page, and a part without a reading is null instead of 0. Global flags such as --hub typed before storage or mesh are now accepted by the CLI.
