---
pr: 452
branch: codex/178-plugin-tools-fold
---
Consolidates signed REST tool dispatch and installed-schema settings. Reads are bounded and audited; mutations file owner-approved actions and serialize with lifecycle changes. Destructive tools require action-bound passkeys. Includes receipt/schema upgrades for existing registry databases and fails closed on changed settings or credentials.
The install plan lists each tool with its declared effect and an update may only drop tools, never add one, change an effect or move the backend (#414). Agents and rules need the exact plugin.invoke grant to run even a read tool; destructive approval asks for a passkey only once passkeys exist. Stored plugin settings are read back by owners only, and a settings schema may not declare secret fields (#415).
