---
pr: pending
branch: feat/173-licence-inventory
---
Refs #173 (APPS-01), partial tooling support only: the existing CI app validator now lists each processed readable app's computed SPDX-derived licence class, using the unchanged L1/L2/blocked classifier in stable directory order. The output explicitly distinguishes this inventory from declared metadata.licenceClass, primary-source verification, scan success and preinstall permission. Invalid manifest structures retain schema errors; unreadable manifests report errors without invented licence facts. Dedicated nondestructive tests cover policy, output, targeting, ordering and error preservation. Required manifest-field enforcement, catalogue migration and actual preinstall-boundary acceptance remain separate work; this does not complete #173.
