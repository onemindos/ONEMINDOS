---
pr: pending
branch: claude/cli-polish
---
The `onemind` command is easier to live with. The image now ships tab completion for bash, zsh and fish and the `onemind` man pages (`man onemind`, `man onemind-apps`, ...), both generated at image build from the same command tree as the binary so they cannot drift, and adds `man-db` to the package list. A new first-boot check, F14 (pre-registered in CRITERIA-FIRSTBOOT.md section 10), proves the completion files exist, the completion entry point answers, and `man onemind` renders on the booted image. For laptops, a new `cli-packages` workflow builds the CLI for Linux amd64 and arm64 and macOS arm64 and amd64 as `.tar.gz` archives, a `.deb` per Linux arch and a Homebrew formula, with completions and man pages inside, smoke-tests the `.deb` and uploads everything as a CI artifact. Nothing is published or signed (that stays with the release workflow and founder item F-27). Refs #882 and #234.
