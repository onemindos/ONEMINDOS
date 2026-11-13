<!-- SPDX-License-Identifier: Apache-2.0 -->
# Change fragments

**Why this exists.** Every PR used to add a row to the same table in `CHANGELOG.md` and edit the same rows in `docs/leap/STATUS.md`. Each merge then made every other open PR conflict, so each had to be re-synced and re-run CI. Now each PR adds one new file here and touches nothing shared. A maintainer or the weekly `changes-collect` job folds the fragments into the two files.

**The rule for agents and people:** add `changes/<branch>.md` (branch name with `/` replaced by `-`). Do not edit `CHANGELOG.md` or `docs/leap/STATUS.md` in a feature PR.

## Format

```
---
pr: pending
branch: feat/example-thing
status_rows:
  - EPIC-ID | in-review | optional short note
---
What it adds, in plain language, as one paragraph. No "|" characters (it becomes a table cell).
```

- `pr:` the PR number (`123`) or `pending` before it exists. Update it once the PR is open.
- `branch:` your branch. The file must be named `feat-example-thing.md` (slug of the branch).
- `status_rows:` optional. Each line is `ID | state | note`. The ID must already exist in `docs/leap/STATUS.md`; state is `todo`, `in-progress`, `in-review`, `review`, `done`, `parked` or `superseded` (a suffix like `(agent A)` is allowed). Collect sets the state, branch and PR on that row and appends the note.
- Body: the text for the "What it adds" cell of the Unreleased table.

## Commands

```
python3 -I scripts/changes.py check     # validate (CI runs this)
python3 -I scripts/changes.py render    # show what would be written
python3 -I scripts/changes.py collect   # maintainers/release job: merge into CHANGELOG.md and STATUS.md, delete fragments
```

`collect` is idempotent: a second run finds no fragments and changes nothing. A fragment for a branch already in the table replaces that row.
