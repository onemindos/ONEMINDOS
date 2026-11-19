---
pr: pending
branch: fix/test-changes-sha-flake
---
A flaky unit test is fixed: the change-fragment preview test checked that the digits 999 never appear in the generated status page, but the page also prints the commit id of a throwaway test repository, and a random commit id sometimes contains 999 (it failed the unit check on the leap-run plan PR). The test now checks for the stale summary row itself.
