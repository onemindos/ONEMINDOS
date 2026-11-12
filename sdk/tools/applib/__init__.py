# SPDX-License-Identifier: Apache-2.0
"""Shared code for the OneMind app tools (app-scaffold, app-gate, app-readme).

Contract: sdk/contracts/poc-v0.md §4, §9 and §11. The tools put this package's parent directory
on sys.path themselves, because `python3 -I` does not add the script directory.
"""
