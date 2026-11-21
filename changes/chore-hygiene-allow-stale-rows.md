---
pr: pending
branch: chore/hygiene-allow-stale-rows
---
Removes seven stale rows from the hygiene allow-list: the four old home-directory rows for the VM image, QEMU tests, lab kits and handbook (those paths moved to a different user home), the row that only allowed those rows inside the list itself, and two mesh address rows for files that never contained one. Removing allow rows cannot hide a finding, and the full scan shows none of them matched anything.
