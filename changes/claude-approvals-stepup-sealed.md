---
pr: 1337
branch: claude/approvals-stepup-sealed
---
The phone can now approve an app install that needs secrets only a person can give, such as an API key (Refs #528). Approving such an install opens a masked form under the request; the values are sealed on the phone to the box key (X25519, HKDF-SHA256 and AES-256-GCM through the platform's own AES, the same construction as the dashboard and the gateway), bound to that app, and sent only inside the signed approval. They are never shown again or logged, and Cancel approves nothing. Keys the box makes itself are not asked for, and a hub without the secrets routes approves as before.
