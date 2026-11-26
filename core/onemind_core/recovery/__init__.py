# SPDX-License-Identifier: Apache-2.0
"""Never lose your data: recovery contacts, contact-assisted recovery and legacy contacts (D-028).

Gateway permissions design §3.13 (revision 3), PRs 25d to 25f. Data access never depends on any of
this: these paths only give back sign-in and keys, and none of them can delete, reset, re-key or
unlock anything (D-028 "No path deletes data or bypasses disk encryption").
"""
