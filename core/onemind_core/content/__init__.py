# SPDX-License-Identifier: Apache-2.0
"""Offline content manager (NMD-02, #127): Kiwix books by pack and by Wikipedia size and language.

kiwix.py reads the live Kiwix catalogue, packs.py holds the curated packs, service.py turns a choice
into an owner-approved `app.configure` of the Kiwix app and runs the auto-update check.
"""
