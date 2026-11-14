---
pr: pending
branch: feat/app-secrets
status_rows:
  - CORE-DEPLOY-4 | in-review | app secret store built (spec.secrets, sealed owner input, AES-256-GCM at rest, server-side apply, rotation); dashboard wiring still to do
---
App secrets (CORE-SECRETS-1): manifests declare spec.secrets; the owner enters values in the install approval or files a change, sealed in the browser to the box key; values are stored AES-256-GCM with a key from the box key store, applied as Kubernetes Secrets by server-side apply, and never shown again, never to agents, never logged. Hermes declares its model-provider keys; the onemind-secrets command is the terminal stand-in until the dashboard shows the form. The F-7 owner override for scan-failed installs (APP-OVERRIDE-1) is built but off unless ONEMIND_ALLOW_OWNER_OVERRIDE=1 (founder decision F-7 is pending), never covers malware or a blocked tier, and leaves a red audit mark. Form, dialog and demo in ui/src/secrets. Guide: docs/leap/core/SECRETS.md.
