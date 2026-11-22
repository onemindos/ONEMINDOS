---
pr: pending
branch: claude/c12-nas-client-packages
---
NAS client tools in the image (#871): cifs-utils (SMB) and nfs-common (NFS) join the common package list on both legs, so #718 can mount a NAS share on the box itself. Clients only: no NFS or SMB server package is added, and the rpcbind and nfs-client units nfs-common enables are disabled at build. The image manifest (packages.txt) now records each package's installed size. A new battery step (CRITERIA-NAS.md, TN0-TN2) checks the packages, kernel modules, disabled units and the slot size budget on the booted image, then mounts a throw-away NFSv4 and SMB 3.1.1 export from the guest itself over loopback and reads a random token back.
