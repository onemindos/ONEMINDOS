---
pr: pending
branch: claude/atlas-phone-map
---
The phone app gets the Map tab from the Atlas design (13b): sites, fresh, stale and offline counts, class filters, a plan with every asset as a tile that prints its value and age, a card for the tapped asset with each value's own age, a list view for assets without a position, and a plain empty state when nothing reports. It reads the same sources as the desktop will: sites over the gateway sites route and asset values over the asset event stream through the gateway, never NATS. When the connection drops the last map stays on screen and the ages keep counting. The plan is drawn with react-native-svg, so no new native dependency is added; MapLibre and offline map packs stay a later step.
