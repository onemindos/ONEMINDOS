---
pr: 1020
branch: bundle/b11-map
---
List offline basemap packs with their local size, bounds, zoom range, and declared attribution, and serve PMTiles byte ranges from the same opened archive. Tests read a real fixture tile with upstream requests disabled (#652). Map pack installation and removal use approved actions, signed region catalogs and verified atomic downloads.
