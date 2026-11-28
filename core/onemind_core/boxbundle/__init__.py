# SPDX-License-Identifier: Apache-2.0
"""Box export and import, first slice (docs/architecture/BOX-EXPORT-IMPORT.md, phase 1).

> **In plain words.** A *box bundle* is one file that holds how a OneMind box is set up, in layers
> (box settings, people, rules, apps, ...), so the owner can save it, move it to new hardware or put a
> box back after it dies. This first slice only defines the bundle's table of contents (the manifest,
> checked against `sdk/schema/onemind.box-bundle.schema.json`) and builds the first layer, the box
> settings, as plain data. Nothing here is wired to a route yet, nothing is encrypted yet, and nothing
> leaves the box: encryption to the owner's kit, signing, the routes, the screen and the CLI are later
> phases, each behind owner approval with a passkey step-up.

Modules:
- `manifest.py`   the manifest: canonical JSON, layer digests, schema and version checks.
- `box_config.py` layer a: collect the box settings from the gateway database, check them, show what an
                  import would change, and write back the parts that are safe to write without a person
                  typing a secret again.
"""
