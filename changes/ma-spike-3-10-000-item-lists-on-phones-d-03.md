---
pr: pending
branch: ma/spike-3-10-000-item-lists-on-phones-d-03
---
Spike 3 (D-032, long lists on the phone): a dev-only Long list spike screen in the mobile app shows 10,000 generated rows (title, subtitle, date, checkbox) with a live search box and a switch between React Native FlatList and Shopify FlashList (MIT, pinned at the Expo 58 version). It shows only in a dev build or with EXPO_PUBLIC_ONEMIND_SPIKES=1, reads nothing from the box, and has Jest tests for rendering, filtering and the flag. mobile/docs/long-list-spike.md says how to measure frame times on a phone with adb dumpsys gfxinfo. The on-phone numbers are not measured yet.
