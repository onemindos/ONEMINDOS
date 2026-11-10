# Kickoff prompt (paste into the research agent)

Daniel: open Claude Code on your account in a fresh clone of this repo, then paste the block below as **one message**.

```text
ultracode

You are the research lead for OneMind OS. Clone https://github.com/onemindos/ONEMINDOS (you have access as an owner of the onemindos org), cd into it, and read RESEARCH-MISSION.md in full. It is your complete one-shot brief. Execute it end to end at maximum depth: orchestrate parallel workflows, use extended web search, reverse-engineer competitor source code, run the VM lab where possible, and verify every load-bearing claim adversarially.

Follow its rules exactly:
- no guessing (primary sources, claims ledger)
- proven competitors first (Home Assistant OS, umbrelOS, Olares), constraint-matched
- tier order (A before B/C)
- you cannot ask the founder anything: decide, state assumptions, log them in 26-OPEN-QUESTIONS-FOR-ZEUS.md
- the repo is PUBLIC: run gitleaks before every push

Write everything to research-output/ on branch research/ultracode-foundation. Open a draft PR early, push after every workstream, and finish with:
- 01-FOUNDATION-DECISION.md (ADR-001 confirmed, changed or overturned)
- 20-PLAN-180-DAYS.md and 21-ROADMAP-5-10-YEARS.md
- 30-NEXT-ULTRACODE-BUILD-BRIEF.md
- research-output/ONEMIND-OS-FOUNDATION-REPORT.pdf, the visual founder report covering everything in context/00-CONVERSATION-RECORD.md

Then mark the PR ready for review. Do not stop until RESEARCH-MISSION.md §9 "Definition of done" is met, or you have documented exactly what remains.
```

**What Zeus reviews afterwards:** the PR → `research-output/REVIEW-CHECKLIST.md` → `ONEMIND-OS-FOUNDATION-REPORT.pdf`.
