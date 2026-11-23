<!-- SPDX-License-Identifier: Apache-2.0 -->
# Proposed minimum age for every Market app

**For Zeus to approve or change.** Founder decision 2026-11-21: "Yes, rate the apps." Build step: FAM-01 (#204), stacked on the age-preset work (Child 12, Teen 16). The rating lives in each app's manifest (`metadata.age_rating`, `metadata.age_reason`). To change one, edit that app's manifest or tell me the app and the number.

**Why this matters.** When an owner sets a rating limit on a child, any app without a rating is hidden. Before this change no app had one, so a child or teen would see nothing. Now the catalog rating is the default, and the owner can still override any single app.

**Rule used (full text in `apps/README.md`).** 0 safe for anyone; 7 simple tools with no open internet and no chat; 12 general tools with open internet or user content; 16 mature media, unfiltered chat or AI, download tools, social; 18 admin, infrastructure, money, passwords, adult. When unsure the higher number won. Ratings are about what the app does, not its brand.

## Counts

| Rating | Apps | Seen by a Child (limit 12) | Seen by a Teen (limit 16) |
|---|---|---|---|
| 0 | 4 | yes | yes |
| 7 | 3 | yes | yes |
| 12 | 17 | yes | yes |
| 16 | 25 | no | yes |
| 18 | 17 | no | no |

- A **Child** (limit 12) would see **24 of 66** apps.
- A **Teen** (limit 16) would see **49 of 66** apps.
- Only apps the owner also shares with that person are shown; the rating is one of several filters.

## All apps, lowest rating first

| Rating | App | Category | Reason |
|---|---|---|---|
| 0 | offline-maps | field | Offline street maps; no accounts, no chat, no internet. |
| 0 | kiwix | learning | Offline Wikipedia and reference libraries, the founder's example of safe for anyone. |
| 0 | kolibri | learning | Offline classroom lessons and exercises; no internet, no chat. |
| 0 | librespeed | network | Measures internet speed; no content and no settings to change. |
| 7 | mealie | family | Recipes and shopping lists; the only outside link is importing a recipe page. |
| 7 | excalidraw | notes | A whiteboard for sketches; content is only what the person draws. |
| 7 | bentopdf | productivity | Edits PDFs on the device only; no sharing, no internet, no chat. |
| 12 | gitea | developer | Code hosting with issues and comments; content is user-made. |
| 12 | penpot | developer | Design and prototyping with shared files; content is user-made. |
| 12 | homebox | family | Household inventory with prices, serial numbers and attachments. |
| 12 | copyparty | files | File server for uploading and sharing files; holds whatever people put in it. |
| 12 | nextcloud | files | Files, calendar and contacts with sharing; content is user-made. |
| 12 | audiobookshelf | media | Plays audiobooks and podcasts; podcast feeds come from the open internet. |
| 12 | calibre-web | media | Reads and downloads ebooks; the library holds whatever the owner added. |
| 12 | navidrome | media | Streams the owner's music; explicit lyrics are possible. |
| 12 | changedetection | news | Fetches and screenshots any web page the user types in. |
| 12 | freshrss | news | Reads news feeds from the open internet; the feeds are the user's choice. |
| 12 | karakeep | notes | Saves links and pages from the open internet; AI adds tags. |
| 12 | linkwarden | notes | Saves a copy of any page the user bookmarks from the open internet. |
| 12 | memos | notes | Notes that can be shared by link; content is user-made. |
| 12 | trilium | notes | Personal notes with optional sharing; content is user-made. |
| 12 | wiki-js | notes | A shared wiki with user-made pages. |
| 12 | ntfy | notifications | Sends and receives push messages; topics can come from outside the home. |
| 12 | vikunja | productivity | Shared task lists and boards; content is user-made. |
| 16 | anything-llm | ai | Chat with documents and agents on an AI model that has no age filter. |
| 16 | library-chat | ai | Chat with a local AI model over the offline library; model replies are not filtered. |
| 16 | librechat | ai | General AI chat with agents and many models; replies are not filtered. |
| 16 | ollama | ai | Runs any AI model with no filter, including ones the owner downloads. |
| 16 | searxng | ai | Web search across the open internet; results can include adult content. |
| 16 | code-server | developer | A full code editor with a terminal; can run commands and reach the network. |
| 16 | immich | files | Holds the whole household's private photos and videos; face recognition. |
| 16 | photoprism | files | Holds the household's private photos and videos; face recognition. |
| 16 | privatebin | files | Anonymous encrypted pastes that the server cannot read or moderate. |
| 16 | syncthing | files | Syncs folders with outside devices; a wrong device ID shares files. |
| 16 | bazarr | media | Part of the download pipeline; fetches subtitle files for downloaded films and series. |
| 16 | jellyfin | media | Plays movies and series from the owner's library; no content filter. |
| 16 | komga | media | Comics and manga library; mature titles are common and there is no filter. |
| 16 | lidarr | media | Part of the download pipeline; finds and fetches music from torrent and usenet sources. |
| 16 | metube | media | Downloads videos from YouTube and other sites with no content filter. |
| 16 | prowlarr | media | Manages torrent and usenet search sources for the download pipeline. |
| 16 | qbittorrent | media | Torrent client; downloads files from untrusted peers. |
| 16 | radarr | media | Part of the download pipeline; finds and fetches films from torrent and usenet sources. |
| 16 | seerr | media | Browse and request films and series, with posters of mature titles. |
| 16 | sonarr | media | Part of the download pipeline; finds and fetches series from torrent and usenet sources. |
| 16 | tautulli | media | Shows who watched what and when; a privacy log for the media server. |
| 16 | umami | monitoring | Records visitor behaviour on websites; personal data about other people. |
| 16 | uptime-kuma | monitoring | Probes any host or port the user enters and sends alerts; behaves like a scanner. |
| 16 | ghost | productivity | Publishes to the public web and sends newsletters; can take payments. |
| 16 | wordpress | productivity | Publishes a public website with comments and plugins. |
| 18 | hermes-agent | ai | An AI agent that can request actions on the box and message people. |
| 18 | openclaw | ai | An AI agent that takes actions on its own across services. |
| 18 | node-red | automation | Builds automations that act on devices and services. |
| 18 | jenkins | developer | Runs build and deploy scripts; can execute arbitrary code. |
| 18 | paperless-ngx | files | Scanned tax, bank, medical and identity documents. |
| 18 | actual-budget | finance | Household budgets and account balances: money information. |
| 18 | firefly-iii | finance | Personal finance: accounts, transactions and budgets. |
| 18 | esphome | home | Writes firmware onto devices and manages them on the home network. |
| 18 | home-assistant | home-automation | Controls the home: locks, heating, cameras and automations. |
| 18 | zigbee2mqtt | home-automation | Bridges and controls the home's lights, sensors and switches. |
| 18 | mosquitto | iot | Message hub for devices; whoever can publish can control them. |
| 18 | grafana | monitoring | Reads the box's data sources and can query databases; an admin dashboard. |
| 18 | metabase | monitoring | Connects to databases and runs queries on them; an admin and data tool. |
| 18 | prometheus | monitoring | Exposes internal metrics of the box and its apps, with an admin API. |
| 18 | adguard-home | network | Changes how every device on the network resolves names; an admin tool. |
| 18 | tor-remote-access | network | Opens a route to the box from the internet; changes network exposure. |
| 18 | vaultwarden | passwords | The household's password vault. |
