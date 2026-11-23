---
pr: 946
branch: claude/ab2-mesh-mount
---
The mesh is now fully mounted in the gateway (CORE-NET-8, #876). The owner turns the mesh on or off, picks its provider (Headscale) and sets the control URL with `PUT /v1/mesh/settings` or `onemind mesh settings`. The choice is stored in the settings store, written to the audit log and applied at once, with no restart. Only the owner can change it. Agents and other people get 403, and each refusal is audited. With no provider chosen, `GET /v1/mesh` says "not set up" and gives the next step. A provider that is chosen but not installed says how to install it. The box CA now starts when the mesh is turned on, and reading the mesh view no longer creates one. The join bundle's mesh block now names the provider next to the relay fields. Every older field stays, so nodes from the previous release keep joining.
