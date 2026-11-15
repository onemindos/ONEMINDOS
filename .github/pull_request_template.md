<!-- Rules: docs/leap/AGENT-QUEUE.md. One issue per PR, under about 600 changed lines. -->
Closes #

## Why

## What

## Tests
<!-- The exact commands you ran and their result. -->

## Not done

## Checklist
- [ ] Real data through the gateway; no mock or placeholder data on a screen a user can reach
- [ ] Reachable from a route, a dashboard screen or the `onemind` CLI
- [ ] A test that fails without this change; touched suites pass
- [ ] `make lint`, `scripts/changes.py check`, `scripts/hygiene.py`, gitleaks pass
- [ ] `changes/<branch>.md` fragment added; CHANGELOG.md and STATUS.md untouched
- [ ] Every commit signed off (`git commit -s`)
- [ ] No locked decision broken (D-001 to D-014); AI never actuates without human approval
