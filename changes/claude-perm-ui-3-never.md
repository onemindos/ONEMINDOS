---
pr: 1274
branch: claude/perm-ui-3-never
---
Settings, Permissions has a Never tab for deny rules: each requester that may never have a request type, or a whole kind of request (reading, writing, sensitive changes, deleting, controlling devices, anything physical), approved without a person, with the reason given. Adding one only makes things safer, so it applies at once with no passkey; the form suggests the box's agents and the request types it has seen. Removing one loosens, so the owner's passkey confirms it through the normal passkey sign-in when the gateway asks. The CLI already has onemind permissions deny list, add and remove.
