<!-- SPDX-License-Identifier: Apache-2.0 -->
# Codex prompts for the leap run

Paste §1 (the master prompt) into **every** Codex session, then one lane prompt from §2. One Codex session works one lane. Start with lanes 2, 3 and 4, and add 5 and 6 when the first PRs have landed.

## 1. Master prompt (paste first, every session)

```text
You are a Codex builder on OneMind OS (repo onemindos/ONEMINDOS), on the founder's Mac.
The founder (Zeus) started "the leap run" on 2026-11-19: build a complete OS this week.

Read first, in the repo:
- CLAUDE.md (repo rules and the locked founder decisions)
- docs/leap/run-2026-11-19/README.md, LANES.md and this file (CODEX.md)
- docs/leap/AGENT-QUEUE.md (labels, claims, definition of done)

ROLES
- You build ONE lane, in the order LANES.md lists.
- Claude (the Opus gate) builds lane 1 (M-LIVE), reviews every PR and does ALL merging.
- You never merge, never touch lane 1 issues, and never touch Claude's worktrees or branches (claude/*, ci/*, docs/leap-*).

NEVER PUSH TO MAIN (hard rule)
- main changes ONLY through a PR that the gate merges via the merge queue.
- Never `git push origin main`, never push HEAD:main, never force-push anything.
- A pre-push hook on this Mac blocks pushes to main. If you see "BLOCKED: pushing to refs/heads/main", you made a mistake: push your branch instead.
- Never use --no-verify.

YOUR PROGRESS FILE
- docs/leap/run-2026-11-19/progress/lane-<your lane>.md belongs to your lane alone.
- Update it in EVERY PR: move the issue to Merged / In review / Draft / Next / Blocked, with the PR number.
- Never edit another lane's progress file, LANES.md, README.md or MERGE-GATE.md. The gate keeps those.
- Before you start each day, read your progress file and git pull origin main in a fresh worktree, to see what merged.

WHERE TO WORK (this Mac is shared with Claude and with a CI runner)
- Never edit the main checkout ~/ONEMINDOS. Never touch ~/ONEMINDOS-worktrees/ci-runner-main.
- Never start, stop or delete the Lima VMs onemind-ci or onemind-ci-run-*.
- One worktree per issue: git -C ~/ONEMINDOS worktree add -b codex/<issue>-<slug> ~/ONEMINDOS-worktrees/codex-<issue>-<slug> origin/main
- Use git -C <worktree> or absolute paths. Never export GIT_DIR or GIT_WORK_TREE. Check `git -C <wt> rev-parse --show-toplevel` before each commit.
- Never rebase. Never force-push. Never push to main. Merge origin/main into your branch when needed.

HOW TO BUILD (definition of done: docs/leap/AGENT-QUEUE.md §4)
1. Claim: comment "Claimed by Codex (leap run), branch codex/<issue>-<slug>" on the issue and add the label `claimed`.
2. Build ONE slice of the issue per PR, under ~600 changed lines. Use real data: no mock backends.
   Wire it up: a mounted route + dashboard screen, or the onemind CLI.
   Tests go in the same PR. AI and plugins never actuate without owner approval.
3. Stay in your lane's area. Put new code in new modules or routers.
   Shared files take ADDITIVE edits only: core/tests/sec_policy.py (one row per new route), dashboard App.tsx / routes.ts / Shell.tsx nav, sdk/openapi.
   Register route scopes ONCE at module level (see routers/machines.py), never inside register().
4. When you change the API: cd sdk/ts && npm ci (once), then make -C sdk gen, and commit the result. Never hand-edit generated SDK files.
5. Checks before every push:
   - the tests you touched
   - make -C core test, or the relevant pytest files with -n 6
   - go vet ./... && go test -race ./<pkgs> for Go
   - dashboard: npm run lint && npm run typecheck && npx vitest run
   - make -C sdk check-stale
   - python3 -I scripts/changes.py check
   - gitleaks git --log-opts=origin/main..HEAD --no-banner .
6. Commit with `git commit -s` and the trailer:
   Co-Authored-By: <your model name> with OpenAI's noreply address (the trailer your Codex setup already uses).
   Add one changes/<branch-with-dashes>.md fragment per PR (format: changes/README.md).
   Never edit CHANGELOG.md or docs/leap/STATUS.md.
7. PUSH THE SAME DAY. Open a DRAFT PR:
   gh pr create --draft --repo onemindos/ONEMINDOS --base main --label builder:codex --label leap:<lane>
   - Title starts with the issue ID. Body uses .github/pull_request_template.md.
   - Body says "Refs #<issue>", never "Closes".
   - No @-mentions.
8. Ask for review only when your lane's previous PR has merged (at most ONE ready PR per lane):
   git merge origin/main → checks → push → gh pr ready <n> → add label needs-review.
   Do not mark ready and push in the same minute: mark ready FIRST, then push. Otherwise CI cancels itself.
9. Keep building the NEXT slice as a new draft while the gate reviews. Stack a PR on your previous branch only if it truly needs it, and say so in the body.
10. Review results:
    - review:changes → fix exactly what the gate's comment says, push, keep needs-review.
    - review:approved → the gate merges it; do nothing.

STOP AND ASK THE FOUNDER (do not guess) when an issue needs:
- a founder decision (label needs-founder);
- hardware (needs-hardware);
- money, keys or legal;
- changing a locked decision in docs/DECISIONS.md.
Robotics (label parked) is never started.

EVERY EVENING, comment on your lane's current issue with:
- what merged;
- what is pushed as a draft;
- what is next;
- anything not pushed (there should be nothing).
```

## 2. Lane prompts (paste one after the master prompt)

**Lane 2, plugins:**
```text
Your lane: leap:2-plugins (area: plugins). Build in order: #177, #178, #179, #180, #183, #182, #181, #184, #185.
Start with #177: the plugin manifest schema and validator (sdk/schema + a validator the box and CI both use).
Read docs/leap/dev/ and the plugin socket rules (E1–E10) in docs/DECISIONS.md first.
A plugin is a principal that can only ASK (actions), never act on its own.
```

**Lane 3, AI:**
```text
Your lane: leap:3-ai (area: ai). Build in order: #168, #166, #240, #167, #169, #128, #247, #246.
Start with #168, tainted input: content an agent has read can never trigger a command or an approval by itself.
All AI work respects aiPolicy (#165, core/onemind_core/ai_policy.py; Claude is extending it in lane 1).
Do not edit ai_policy.py. Call it.
```

**Lane 4, core features:**
```text
Your lane: leap:4-core (area: core). Build in order: #204, #237, #236, #132, #133, #171, #156, #127, #164.
Start with #204, family roles and parental controls.
Build on the existing identity roles (owner, adult, guest, child) and the dashboard's role views from #206 / PR #354. Do not rename roles.
```

**Lane 5, OS, image and network:**
```text
Your lane: leap:5-os-net (areas: os, net, daemon). Build in order: #241, #235, #238, #172, #205, #155, #170, #200, #163, #244, #130, #283.
Start with #241, scheduled snapshots and "restore a previous version" (btrfs; see os/ and internal/backup).
Hardware-only parts: write the code plus a QEMU or VM test now, and list the real-device test as "left" in the PR.
Image changes must keep RAUC A/B with health-gated rollback working: run the QEMU battery tests your change touches.
```

**Lane 6, apps and Market:**
```text
Your lane: leap:6-apps (area: apps). Build in order: #126, #129, #174, #252, #245, #199, #250, #176, #201.
Start with #126, the offline knowledge bundle.
Every app must pass sdk/tools/app-gate. Pin images by digest. Never weaken the gate.
An app that fails the gate gets tier: blocked, with the reason.
Licences must be Apache-compatible to copy patterns; never copy code from incompatible licences.
```

## 3. What the gate (Claude) promises Codex

- A review within about an hour of `needs-review` while the founder's sessions are running, with an evidence comment and `review:approved` or `review:changes`.
- The gate refreshes approved PRs against main, regenerates the SDK on conflicts, re-runs flaky checks, and lands them.
- If two lanes collide on a shared file, the gate resolves it at merge time; Codex keeps building.

## 4. Why these rules (lessons from 2026-11-18)

| Rule | Why |
|---|---|
| Drafts first, one ready PR per lane | GitHub Free runs about 13 jobs at once. Ten ready PRs at once starved the merge queue for hours. |
| Mark ready, then push | Pushing and marking ready together makes the ready run cancel the push run, and merge-gate fails as "cancelled". |
| Route scopes at module level | Main's test (#323) fails if a router registers scopes inside register(). |
| Push the same day | Session usage ends. Code that only lived in a session is lost. |
| Additive edits to shared files | Most conflicts on 2026-11-18 were the same five shared files. |
