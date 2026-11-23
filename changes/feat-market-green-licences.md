---
pr: 867
branch: feat/market-green-licences
---
Closes #173 (APPS-01). Every app manifest now declares a required metadata.licenceClass (L1 permissive, L2 copyleft, blocked, unknown). A one-off tool filled it for all 68 apps from each manifest's recorded upstream licence; esphome and chromium are unknown because their licence evidence disagrees or is incomplete. validate-apps refuses a green claim that does not match the SPDX licence. The gateway lists the class on every app and refuses to approve an install of a blocked or unknown app unless the owner types the app id (accept_licence), never through a standing approval or an agent. The Market shows green classes by default and takes the class from the manifest.

Clients now send it: the dashboard Approvals page asks the owner to type the app id in a dialog, the onemind CLI asks the same (or takes --accept-licence APP_ID), and the phone says to do it on the dashboard or CLI. validate-apps now prints the declared metadata.licenceClass beside the computed SPDX class.
