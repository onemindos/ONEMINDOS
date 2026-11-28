# SPDX-License-Identifier: Apache-2.0
"""Box export and import (docs/architecture/BOX-EXPORT-IMPORT.md).

> **In plain words.** A *box bundle* is one file that holds how a OneMind box is set up, in layers
> (box settings, people, rules, apps, ...), so the owner can save it, move it to new hardware or put a
> box back after it dies. The manifest describes the layers and the envelope protects them using
> the owner's kit and export signing key.

Modules:
- `manifest.py`   the manifest: canonical JSON, layer digests, schema and version checks.
- `envelope.py`   offline seal and open with kit and optional passphrase recipients.
- `box_config.py` layer a: collect the box settings from the gateway database, check them, show what an
                  import would change, and write back the parts that are safe to write without a person
                  typing a secret again.
"""

from .envelope import OpenedBundle, certify_export_key, kit_recipient_public_key, open_bundle, seal_bundle

__all__ = ["OpenedBundle", "certify_export_key", "kit_recipient_public_key", "open_bundle", "seal_bundle"]

CONFIG_APPLY = "config.apply"
