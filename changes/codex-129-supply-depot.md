---
pr: 374
branch: codex/129-supply-depot
---
Supply Depot apps for the Market (issue 129, NMD-04): CyberChef, IT-Tools, LibreTranslate, ArchiveBox and Collabora Online (CODE) as OneMind app packages. Each runs upstream's unmodified image pinned by tag and digest (read from the registry on 2026-11-19), non-root with RuntimeDefault seccomp, all capabilities dropped and resource limits, and has a README that explains the setup and its licence evidence. LibreTranslate's language models are a separate download whose per-model terms are still UNVERIFIED. Collabora stays tier blocked because the licence gate cannot confirm its MPL-2.0 licence (GitHub reports NOASSERTION and there is no research licence-matrix row).
