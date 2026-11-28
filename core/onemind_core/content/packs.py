# SPDX-License-Identifier: Apache-2.0
"""Curated content packs (NMD-02, #127): named groups of Kiwix books.

A pack lists catalogue names and flavours only, never a dated file: the newest release and its
size are read from the live catalogue when the owner looks (kiwix.py), so a pack never points at
a file the mirror has dropped. Every name below was looked up on opds.library.kiwix.org on
2026-11-19; sizes then are in the comments. Content licences differ per book (Wikipedia and
Stack Exchange text is CC BY-SA; check each book's page on library.kiwix.org before sharing it).
"""

from __future__ import annotations

PACKS: list[dict] = [
    {
        "id": "medical",
        "title": "Medical",
        "description": "Medical encyclopedias and practical medical guides for when no doctor is reachable.",
        "books": [
            {"name": "wikipedia_en_medicine", "flavour": "maxi"},  # WikiMed, 1.9 GB
            {"name": "mdwiki_en_all", "flavour": "maxi"},  # MDWiki, 2.3 GB
            {"name": "zimgit-medicine_en", "flavour": ""},  # Medical Library, 70 MB
        ],
    },
    {
        "id": "survival",
        "title": "Survival",
        "description": "Water, food, shelter and recovery after a disaster, plus outdoor and gardening answers.",
        "books": [
            {"name": "zimgit-post-disaster_en", "flavour": ""},  # Post Disaster Resource Library, 645 MB
            {"name": "zimgit-water_en", "flavour": ""},  # Water Treatment Library, 21 MB
            {"name": "zimgit-food-preparation_en", "flavour": ""},  # Food for Preppers, 98 MB
            {"name": "outdoors.stackexchange.com_en_all", "flavour": ""},  # The Great Outdoors Q&A, 142 MB
            {"name": "gardening.stackexchange.com_en_all", "flavour": ""},  # Gardening Q&A, 933 MB
        ],
    },
    {
        "id": "education",
        "title": "Education",
        "description": "Interactive science and maths simulations, open textbooks and courses.",
        "books": [
            {"name": "phet_en_all", "flavour": ""},  # PhET simulations, 109 MB
            {"name": "wikibooks_en_all", "flavour": "nopic"},  # Wikibooks, 3.5 GB
            {"name": "wikiversity_en_all", "flavour": "nopic"},  # Wikiversity, 1.6 GB
        ],
    },
    {
        "id": "radio",
        "title": "Ham radio and SDR",
        "description": "Amateur radio, electronics and signal processing (software-defined radio) reference.",
        "books": [
            {"name": "ham.stackexchange.com_en_all", "flavour": ""},  # Amateur Radio Q&A, 77 MB
            {"name": "dsp.stackexchange.com_en_all", "flavour": ""},  # Signal Processing Q&A, 379 MB
            {"name": "electronics.stackexchange.com_en_all", "flavour": ""},  # Electronics Q&A, 4.3 GB
        ],
    },
]

# Wikipedia comes in three sizes per language (the catalogue's flavours).
WIKIPEDIA_FLAVOURS = {
    "mini": "Introduction of every article, no pictures",
    "nopic": "Full articles, no pictures",
    "maxi": "Full articles with pictures",
}


def wikipedia_name(lang: str) -> str:
    return f"wikipedia_{lang}_all"
