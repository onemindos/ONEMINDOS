---
pr: pending
branch: claude/p0-installer-board-update-bundles
---
Dev releases now carry signed RAUC update bundles for the x86_64-efi installer board (the box installed from the USB stick), not only for the droplet image, plus an update-compat file per board that records the board, version pair and signing CA of the N to N+1 update and is checked with the same version rules the box uses. The installer job keeps the bundles built together with the stick's image so the throwaway CA matches. os/boards/installer-x86_64/UPDATES.md explains what happens on ceremony day and what CI must show for T2 and T5. Refs #234.
