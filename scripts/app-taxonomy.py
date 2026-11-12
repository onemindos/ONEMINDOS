#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Normalise apps/_intake/candidates.csv to the Market taxonomy (docs/design/TAXONOMY.md).

Adds four columns: category (Market slug), subtags (';'-separated, from the closed list
per category), deploy_class and placement. The research-run category is kept, renamed
category_v0. The input is only the CSV itself plus the rules and overrides below, so the
output is deterministic and the script is idempotent (running it twice changes nothing).
It also rewrites the category shown in CANDIDATES.md (batches, Top 100 table) and the
generated counts block between the taxonomy markers.

  python3 -I scripts/app-taxonomy.py            # rewrite in place
  python3 -I scripts/app-taxonomy.py --check    # exit 1 if a rewrite would change a file
"""
import argparse, csv, io, re, sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "apps/_intake/candidates.csv"
MD_PATH = ROOT / "apps/_intake/CANDIDATES.md"
AS_OF = date(2026, 11, 12)  # the date the CSV facts were fetched; fixed for determinism

# slug -> (display name, icon name). Order is the Market chip order. TAXONOMY.md §1.
CATEGORIES = {
    "home": ("Home & IoT", "home"),
    "files": ("Files & Photos", "folder"),
    "media": ("Media", "play"),
    "notes": ("Notes & Knowledge", "note"),
    "productivity": ("Productivity", "tasks"),
    "communication": ("Chat & Social", "chat"),
    "ai": ("AI & Agents", "agent"),
    "automation": ("Automation", "flow"),
    "network": ("Network & Security", "lock"),
    "monitoring": ("Monitoring", "activity"),
    "news": ("News & Intel", "radar"),
    "developer": ("Developer", "code"),
    "family": ("Family & Health", "heart"),
    "finance": ("Finance", "wallet"),
    "learning": ("Learning & Games", "book"),
    "field": ("Field & Robotics", "radio"),
}

# Research-run category (category_v0) -> default Market slug and default subtags.
V0 = {
    "Home & IoT": ("home", ""), "Files & Photos": ("files", ""), "Media": ("media", ""),
    "Media: download automation": ("media", "downloads"),
    "Productivity & Knowledge": ("productivity", ""), "Social & Communication": ("communication", ""),
    "AI & Models": ("ai", ""), "Automation": ("automation", ""), "Security & Network": ("network", ""),
    "Monitoring & Intel": ("monitoring", ""), "Developer": ("developer", ""),
    "Family & Home Life": ("family", ""), "Health & Fitness": ("family", "fitness"),
    "Finance": ("finance", ""), "Bitcoin & Crypto": ("finance", "bitcoin"),
    "Education & Offline": ("learning", ""), "Games": ("learning", "games"),
    "Desktop & VMs": ("developer", "vm-desktop"), "Field, Mesh & TAK": ("field", "mesh"),
    "Other": ("productivity", "utility"),
}

# Productivity & Knowledge rows that are notes, wikis, bookmarks or whiteboards.
NOTES_RE = re.compile(
    r"note|memo|wiki|trilium|karakeep|docmost|linkwarden|excalidraw|bookstack|joplin|siyuan|blinko|"
    r"affine|silverbullet|wallabag|obsidian|hedgedoc|logseq|outline|docsify|codimd|cryptpad|mind-?map|"
    r"my-mind|tldraw|tiddlywiki|shaarli|linkace|shiori|^slash$|whiteboard|whitebophir|spacedeck|"
    r"alexandrie|textarea|etherpad|drawio|tableaunoir|fiduswriter|suitenumerique-docs|^md$|overleaf|"
    r"^novel$|turtl|cowyo|journiv|plainpad|nullboard|^mind$")

# Closed sub-tag vocabulary per category, with id patterns. First match order = tag order.
SUBTAGS = {
    "home": [("hub", r"home-?assistant|openhab|domoticz|gladys|iobroker|jeedom|fhem|homebridge|ha-fusion|yuvomi|hass-"),
             ("mqtt", r"mosquitto|mqtt|emqx|rabbitmq"), ("zigbee", r"zigbee"), ("zwave", r"zwave"),
             ("matter", r"matter|otbr"), ("cameras", r"frigate|motioneye|scrypted|strix|nvr"),
             ("energy", r"emoncms|energy"), ("firmware", r"esphome"),
             ("industrial", r"plc|scada|modbus|mbusd|enocean"), ("3d-printing", r"octoprint|mainsail|spoolman|manyfold")],
    "files": [("cloud", r"nextcloud|owncloud|ocis|opencloud|seafile|^cells$|bewcloud|cloudreve|alist|openlist|filestash|spacedrive|mydrive|sync-in"),
              ("photos", r"immich|photo|lychee|piwigo|^slink$|foldergram|picsur|exiftool"),
              ("sync", r"syncthing|rclone|livesync|syncstorage|rmfakecloud|sync-in"),
              ("sharing", r"send|share|drop|transfer|psitransfer|plik|gokapi|filepizza|privatebin|microbin|pastefy|enclosed|^ots$|yeetfile|hat-sh|directorylister|h5ai|projectsend|palmr|^hfs$|copyparty|cryptgeon|hermitstash|xbackbone|originless"),
              ("documents", r"paperless|papra|readur|scanserv"),
              ("backup", r"backup|duplicati|restic|borg|backrest|plakar|kopia"),
              ("storage", r"minio|seaweed|samba|webdav|versitygw|armadietto|ipfs|sftpgo|filebrowser|filegator|filerise|tinyfilemanager|^ifm$|gossa|ftpgrab"),
              ("calendar-contacts", r"radicale|baikal|davis|agendav|calendar"),
              ("convert", r"convert|^vert$|mazanoke|transmute|morphos")],
    "media": [("video", r"jellyfin|emby|pms-docker|stremio|universalmediaserver|videola|mediatheque|invidious|piped|viewtube|tunarr|threadfin|dispatcharr|xteve|holoplay|fireshare|stash|legacy"),
              ("music", r"navidrome|music|mstream|swingmusic|koel|mopidy|ampache|gonic|headphones|lidarr|slimserver|your-spotify|its-mytabs|audacity|moodist"),
              ("books", r"calibre|kavita|komga|booklore|shelfmark|readarr|lazylibrarian|openbooks|booksonic|cops|bicbucstriim|koinsight|kapowarr|mylar|suwayomi|audiobookshelf|grimmory"),
              ("podcasts", r"podfetch|gpodder|gopodder|mygpo|opodsync|podcast"),
              ("downloads", r"sonarr|radarr|lidarr|readarr|bazarr|whisparr|qbittorrent|transmission|deluge|rutorrent|flood|sabnzbd|nzb|jdownloader|pyload|metube|yt-dlp|cobalt|pinchflat|tubearchivist|youtarr|downtify|gopeed|rdt-client|torrent|^qui$|slskd|upload-assistant|unpackerr|cross-seed|recyclarr|profilarr|cleanuparr|autobrr|pymedusa|sickchill|lidarr|barrage"),
              ("indexers", r"prowlarr|jackett|bitmagnet|librex|privtracker"),
              ("requests", r"seerr|ombi|petio|reiverr|wizarr|maintainerr|jellystat|tautulli|embystat|kometa|movary|yamtrack"),
              ("live", r"owncast|mediamtx|restreamer"), ("transcode", r"handbrake|unmanic|mkvtoolnix")],
    "notes": [("notes", r"note|memo|trilium|joplin|siyuan|blinko|silverbullet|logseq|obsidian|plainpad|textarea|journiv|dailytxt|jotty|dumbpad|turtl|^mind$"),
              ("wiki", r"wiki|bookstack|docmost|outline|docsify|tiddly|showdoc|codex-docs|alexandrie"),
              ("bookmarks", r"karakeep|linkwarden|linkace|shaarli|shiori|^slash$"),
              ("read-later", r"wallabag|13ft|ladder"),
              ("whiteboard", r"excalidraw|tldraw|whiteboard|whitebophir|spacedeck|drawio|tableaunoir|mind-?map|my-mind"),
              ("docs", r"hedgedoc|codimd|etherpad|cryptpad|affine|fiduswriter|overleaf|^novel$|suitenumerique|^md$|nullboard|cowyo")],
    "productivity": [("office", r"onlyoffice|euro-office|grist|teable|nocodb|stirling|bentopdf|pdf|languagetool"),
                     ("tasks", r"vikunja|^plane$|kanboard|leantime|openproject|focalboard|wekan|planka|^kan$|tasks|todo|dumbdo|dumbkan|fizzy|super-productivity|redmine|mantis"),
                     ("scheduling", r"cal-diy|rallly|easyappointments|croodle|librebooking|^grr$|pretix|indico|pretalx"),
                     ("time", r"kimai|solidtime|traggo|timeoff"),
                     ("forms", r"formbricks|limesurvey|ohmyform|pytition|fider|^answer$|question2answer"),
                     ("business", r"odoo|twenty|espocrm|dolibarr|orangehrm|snipe-it|glpi|ofbiz|monica|galette|admidio|civicrm|mautic|agora|arkalib|fab-manager"),
                     ("helpdesk", r"freescout|osticket|peppermint|bileto"),
                     ("website", r"ghost|wordpress|^halo$|joomla|^grav$|backdrop|concretecms|automad|bludit|wondercms|htmly|pluxml|yellow|^zola$|^hugo$|pelican|vvveb|drupal|linkstack|omeka|yeswiki|hotglue|indexhibit|299ko|phpboost|ojs|isso|cusdis"),
                     ("shop", r"bagisto|prestashop|medusajs|abantecart"),
                     ("signing", r"docuseal|documenso"),
                     ("utility", r"yourls|shlink|reveal-js|reactive-resume|svgedit|svg-path-editor|qr|pinkarrows|snapotter|omni-tools")],
    "communication": [("chat", r"mattermost|rocket|thelounge|campfire|chitchatter|vocechat|convos|ergo|inspircd|kiwiirc|glowing-bear|openwa|whatsapp|telegram|signal|discord|threema|simplex|tachyon|commet|prose|converse|movim|databag|irc|biboumi"),
                      ("matrix", r"synapse|element|cinny|fluffychat|tuwunel|dendrite|matrix|hydrogen|ketesa|mollysocket"),
                      ("email", r"mail|roundcube|sogo|snappymail|cypht|rspamd|dmarc|postfix|stalwart|sessy"),
                      ("video-calls", r"jitsi|mirotalk|screego|galene|^meet$|element-call|peer-calls|jangouts|spreed"),
                      ("voice", r"mumble|coturn"),
                      ("forum", r"discourse|nodebb|phpbb|mybb|flarum|lemmy|humhub|zusam|agorakit|^community$"),
                      ("fediverse", r"mastodon|misskey|pixelfed|peertube|friendica|diaspora|bookwyrm|^elk$|phanpy|enafore|glitch|writefreely|loops|^pds$|nostr|bonfire|redlib|libreddit|nitter|libremdb|hub-monorepo|^buzz$|go-ssb|route96|usocial|khatru"),
                      ("newsletter", r"listmonk|mixpost|postiz"),
                      ("bridge", r"matterbridge|appservice|mautrix")],
    "ai": [("chat", r"open-webui|librechat|lobehub|nextchat|chatgpt|chatbot|chatpad|litechat|sillytavern|^anse$|hermes-webui|anything-llm|llama-gpt|serge|plurality|mi-gpt"),
           ("llm-runtime", r"ollama|localai|llama-cpp|vllm|sglang|llmfit|qwen|glm-4|minicpm|llava|gaianet"),
           ("agents", r"openclaw|hermes-agent|agent|goose|openhands|paperclip|picoclaw|nemoclaw|spacebot|deer-flow|dify|flowise|langflow|maxkb|bisheng|fastgpt|refly|cheshire|astrbot|langbot|tradingagents|junior|taskingai|^lev$|honcho|deepseek-harness|hivekeep"),
           ("rag", r"ragflow|weknora|cognee|trustgraph|hindsight|mempalace|engram|open-notebook|local-deep-research|anything-llm|hister|strata|^laya$|locius"),
           ("coding", r"opencode|^codex$|claude-code|context7|open-design|lynxprompt"),
           ("image", r"comfyui|stable-diffusion|sd-webui|rembg|turbodiffusion|hunyuan3d|stable-fast-3d|jaaz|midjourney|duix|live2d|ekko"),
           ("speech", r"whisper|tts|speech|kokoro|cosyvoice|fish-speech|silero|speaches|murmur|speakrs|openreader|funclip"),
           ("audio", r"ace-step|yue2|uvr5"),
           ("ocr", r"ocr|surya|docling|unstructured|firecrawl|crawl4ai"),
           ("search", r"searxng|^vane$|yt-navigator"),
           ("translation", r"translate|hunyuan-mt|mtranserver|pdfmathtranslate"),
           ("training", r"llamafactory|unsloth|label-studio"),
           ("gateway", r"litellm|langfuse|9router|freetoken|metamcp|vramarket|orales")],
    "automation": [("workflows", r"n8n|node-red|activepieces|windmill|trigger|hatchet|huginn|dagu"),
                   ("notifications", r"ntfy|gotify|apprise|notifiarr"),
                   ("jobs", r"qinglong|olivetin|webhook|semaphore")],
    "network": [("passwords", r"vaultwarden|passbolt|keeweb|teampass|passky|2fauth"),
                ("sso", r"authentik|logto|pocket-id|tinyauth|^dex$|ldap"),
                ("vpn", r"wg-easy|wireguard|tailscale|headscale|headplane|netbird|zerotier|ztnet|zero-ui|ztncui|nostr-vpn"),
                ("dns", r"adguard|pi-hole|dnsserver|unbound|domain-locker|gandi|dumbwhois"),
                ("ddns", r"ddns|lucky"),
                ("proxy", r"nginx|proxy|zoraxy|openresty|traefik|squid|v2raya|^mtg$|flaresolverr|cloudflared|playit|holesail|wsproxy|^gateway$"),
                ("remote-access", r"rustdesk|guacamole|warpgate|sshwifty|termix|nexterm|wetty"),
                ("firewall", r"crowdsec|nftables|falco"),
                ("speedtest", r"speed|smokeping|watchyourlan|netronome|ifconfig"),
                ("tor", r"^tor$")],
    "monitoring": [("uptime", r"uptime|statping|lunalytics|cachet|phpservermon|peanut|scrutiny"),
                   ("metrics", r"grafana|prometheus|netdata|glances|beszel|zabbix|node-exporter|monitorix|dashdot|phpsysinfo|x-prober|opcache"),
                   ("logs", r"loki|dozzle|logdy|syslog|openobserve|jaeger"),
                   ("analytics", r"umami|matomo|fathom|analytics|superset|metabase|wakapi"),
                   ("dashboards", r"homarr|homepage|dashy|homer|glance|homehub|thinkdashboard"),
                   ("admin", r"webmin|cockpit|phplicensewatcher")],
    "news": [("rss", r"rss|^v2$|commafeed|yarr|tt-rss|tinyfeed|selfoss|leed|readflow|^fusion$"),
             ("archive", r"archive"), ("change-detection", r"changedetection"),
             ("osint", r"web-check|spiderfoot|opencti|intelowl|misp|gods-eye"),
             ("search", r"whoogle|yacy")],
    "developer": [("git", r"gitea|gogs|onedev|forgejo|gitlist|opengist|gitingest"),
                  ("ci", r"jenkins|woodpecker|actions-runner"),
                  ("ide", r"code-server|^coder$|jupyter|docker-stacks|^jean$"),
                  ("database", r"postgres|mysql|mariadb|mongo|influx|couchdb|clickhouse|sqlite|adminer|cloudbeaver|pgweb|phpmyadmin|bytebase|libredb|kafka|denokv|pgbackweb|azimutt|webdatastudio"),
                  ("api-backend", r"pocketbase|directus|convex|hoppscotch|soketi|jsonhero|jsoncrack|martin|^cube$"),
                  ("low-code", r"appsmith|tooljet|budibase|baserow|nocobase|streamlit"),
                  ("containers", r"portainer|dockge|komodo|arcane|^cup$|nomad|chaos-mesh"),
                  ("search-engine", r"meilisearch|elasticsearch|opensearch"),
                  ("design", r"penpot|blender|fontcompare"),
                  ("vm-desktop", r"windows|macos|qemu|virt|redroid|neko|firefox|incus|lxd|steam-headless"),
                  ("tools", r"it-tools|cyberchef|mailpit|whoami|shields|atuin|hello-world|networking-toolbox|exiftool")],
    "family": [("recipes", r"mealie|recipes|kitchenowl"), ("groceries", r"grocy|kitchenowl"),
               ("inventory", r"homebox|koillection"), ("genealogy", r"gramps|webtrees"),
               ("travel", r"trek|^trip$|adventurelog|wanderer|airtrail|flightlog"),
               ("health", r"openemr|cgm|fasten|ovumcy"),
               ("fitness", r"wger|endurain|workout|fittrackee|opengym|sparkyfitness|wingfit"),
               ("habits", r"habit|donetick|ryot"), ("vehicles", r"lubelog|hammond|tracktor"),
               ("garden", r"hortusfox")],
    "finance": [("budget", r"^actual|firefly|data-importer|^sure$|maybe|wallos|ihatemoney|dumbbudget|hausverwaltung"),
                ("investing", r"ghostfolio|wealthfolio|rotki|valorgrid"),
                ("invoicing", r"invoice|invio|akaunting|fossbilling|paymenter|itflow"),
                ("bitcoin", r"bitcoin|btc|electrs|mempool|fulcrum|specter|sats|public-pool|bitaxe|datum|^ord$|^jam$|bisq|seedtool|hashrate|miner|canary|chainforensics|blind-pin|am-i-exposed|helipad|toshi|bitbalance|bitwatch|sv2|pogolo|deepsea|bassin|nutstash|cashu|fedimint|bitboard|robosats|shopstr"),
                ("lightning", r"lightning|lnd|lnbits|^rtl$|thunderhub|^ln-|lnswitch|peerswap|chantools|circuitbreaker|nostr-wallet|lndk|cln-|sphinx"),
                ("crypto", r"ethereum|kaspa|monero|dcr|elements|tdex|cesium|bch"),
                ("trading", r"freqtrade|octobot|^nofx$|trading")],
    "learning": [("courses", r"moodle|kolibri|ctfd|scratch|dodoc|razzia"),
                 ("offline-knowledge", r"kiwix|project-nomad"), ("languages", r"lute|lingva"),
                 ("game-server", r"minecraft|palworld|satisfactory|terraria|luanti|pufferpanel|^panel$|^wings$|lodestone|mineos|steam"),
                 ("emulation", r"emulatorjs|retroarch|romm|nextgba"),
                 ("games", r"hextris|2048|terraforming|virtualtabletop|geoquest|20euros|^81$|lan-games|secretsanta")],
    "field": [("mesh", r"mesh|reticulum"), ("tak", r"tak"), ("radio", r"cloudlog|wavelog"),
              ("gps", r"traccar|ulogger|reitti"), ("robotics", r"isaaclab|^ros"),
              ("maps", r"umap|facilmap")],
}
SUBTAGS = {c: [(t, re.compile(p)) for t, p in rules] for c, rules in SUBTAGS.items()}

# Per-id corrections: "<id> <category> [subtag;subtag]". A row here overrides the v0 category
# (the research categoriser was keyword based and is wrong for these) and, when given, the subtags.
OVERRIDES = """
comfyui ai image
blender developer design
dify ai agents
deer-flow ai agents
streamlit developer low-code
vane ai search
open-notebook ai rag
bisheng ai agents
fastgpt ai agents
refly ai agents
isaaclab field robotics
docker-stacks developer ide
pdfmathtranslate ai translation
mtranserver ai translation
snapdrop files sharing
hfs files sharing
alist files cloud
openlist files cloud
cloudreve files cloud
alist-sync files sync
radicale files calendar-contacts
passbolt-docker network passwords
matomo monitoring analytics
fathom monitoring analytics
invoiceshelf finance invoicing
fossbilling finance invoicing
paymenter finance invoicing
itflow finance invoicing
ihatemoney finance budget
dumbbudget finance budget
beaverhabits family habits
tracktor family vehicles
donetick family habits
openemr family health
project-nomad learning offline-knowledge
ojs productivity website
docker-firefox developer vm-desktop
nexterm network remote-access
yarr news rss
commafeed news rss
tt-rss news rss
fusion news rss
tinyfeed news rss
upvote-rss news rss
selfoss news rss
leed news rss
readflow news rss
gods-eye-view news osint
umap field maps
facilmap field maps
13ft notes read-later
ladder notes read-later
glance monitoring dashboards
answer communication forum
humhub communication forum
community communication forum
agorakit communication forum
isso communication forum
cusdis communication forum
sheetable productivity office
rclone files sync
restic files backup
borg files backup
backrest files backup
plakar files backup
borgwarehouse files backup
yuno-archive files backup
coturn communication voice
phpmyadmin developer database
pgweb developer database
adminerevo developer database
couchdb developer database
kafka-container developer database
dex network sso
phpldapadmin network sso
warpgate network remote-access
guacamole-server network remote-access
wetty network remote-access
incus developer vm-desktop
lxd developer vm-desktop
lxd-ui developer vm-desktop
lxd-dashboard developer vm-desktop
dagu automation workflows
webhook automation jobs
olivetin automation jobs
apprise automation notifications
notifiarr automation notifications
headplane network vpn
zero-ui network vpn
ztncui network vpn
wireguard-ui network vpn
versitygw files storage
rspamd communication email
parse-dmarc communication email
sessy communication email
ifconfig-io network speedtest
ftpgrab files storage
wakapi developer tools
shields developer tools
nftables-blacklist network firewall
cashpilot finance
gomft files sync
spftoolbox communication email
httpsh network remote-access
archivist news archive
v2 news rss
freshrss news rss
changedetection-io news change-detection
archivebox news archive
rss-bridge news rss
wewe-rss news rss
web-check news osint
analytics monitoring analytics
audacity media music
jsoncrack-com developer api-backend
yourls productivity utility
directorylister files sharing
sharevb-it-tools developer tools
rmfakecloud files sync
whoami developer tools
its-mytabs media music
dailytxt notes notes
mind notes notes
dumbwhois network dns
pinkarrows productivity utility
agewasm files sharing
hunyuan3d-1 ai image
hausverwaltung finance budget
garmin-to-fittrackee family fitness
coworkeenextjs productivity business
h5ai files sharing
awesome-digital-human-live2d ai image
lingva-translate learning languages
gossa files storage
ulogger-server field gps
self-hosted-livesync-server notes notes
armadietto files storage
secretsanta family
fontcompare developer design
trustyhash files
clickhouse developer database
zabbix monitoring metrics
baikal files calendar-contacts
neko developer vm-desktop
samba files storage
slskd media downloads
docker-transmission-openvpn media downloads
firefox developer vm-desktop
syslog-ng monitoring logs
yacy-search-server news search
whoogle-search news search
mailflow communication email
email-oauth2-proxy communication email
scrypted home cameras
lunalytics monitoring uptime
myspeed network speedtest
smokeping network speedtest
cesium finance crypto
firefly finance
simple-torrent media downloads
tor network tor
urbit-umbrel developer
cyberchef developer tools
cryptgeon files sharing
pyload media downloads
omni-tools productivity utility
octoprint home 3d-printing
mainsail home 3d-printing
manyfold home 3d-printing
calibre-web-automated media books
booklore media books
koinsight media books
wanderer family travel
adventurelog family travel
trip family travel
airtrail family travel
flightlog family travel
linkstack productivity website
linkstack-docker productivity website
flatnotes notes notes
notediscovery notes notes
jotty notes notes
poznote notes notes
dumbpad notes notes
zeronote notes notes
leafwiki notes wiki
lubelog family vehicles
super-productivity productivity tasks
kan productivity tasks
keeweb network passwords
teampass network passwords
passky-server network passwords
passky-website network passwords
reitti field gps
mail-archiver communication email
hortusfox-web family garden
thinkdashboard monitoring dashboards
homehub monitoring dashboards
habitica family habits
threema-web communication chat
agendav files calendar-contacts
open-web-calendar files calendar-contacts
hash-calendar files calendar-contacts
davis files calendar-contacts
baikal-docker files calendar-contacts
stalwart communication email
restreamer media live
wingfit family fitness
excalidraw-persist notes whiteboard
podcastnode-umbrel media podcasts
gotify-server automation notifications
wekan productivity tasks
planka productivity tasks
tasks-md productivity tasks
redmine productivity tasks
hugo productivity website
crawl4ai ai ocr
context7 ai coding
astrbot ai agents
langbot ai agents
qinglong automation jobs
semaphore automation jobs
falco network firewall
koillection family inventory
showdoc notes wiki
wings learning game-server
docker-minecraft-bedrock-server learning game-server
ipfs-webui files storage
pastefy files sharing
claude-code ai coding
drupal productivity website
docker-flarum communication forum
self-host-planning-poker productivity
corentinth-it-tools developer tools
php-dynamic-qr-code productivity utility
mini-qr productivity utility
minio files storage
seaweedfs files storage
jaeger monitoring logs
influxdb developer database
unbound network dns
exiftool files photos
docker-virt-manager developer vm-desktop
redroid-doc developer vm-desktop
qemu developer vm-desktop
cube developer api-backend
listmonk communication newsletter
grav productivity website
indico productivity scheduling
pretalx productivity scheduling
monica productivity business
wavelog field radio
cloudlog field radio
invidious media video
piped media video
redlib communication fediverse
rsshub news rss
zipline files sharing
romm learning emulation
retroarch learning emulation
emulatorjs learning emulation
nextgba learning emulation
music-assistant-server media music
cobalt media downloads
pinchflat media downloads
tubearchivist media downloads
youtarr media downloads
metube media downloads
upload-assistant media downloads
codex-docs notes wiki
mineos-node learning game-server
next-image-transformation developer api-backend
yt-dlp media downloads
lychee files photos
piwigo files photos
photoview files photos
mi-gpt ai chat
mi-gpt-tts ai speech
huginn automation workflows
langfuse ai gateway
tradingagents ai agents
junior-investor ai agents
stash media video
openreader ai speech
ddns-updater network ddns
traccar field gps
homebridge home hub
spoolman home 3d-printing
cloudflare-ddns network ddns
lightningmate finance lightning
bitboard finance bitcoin
data-importer finance budget
gaianet-node ai llm-runtime
hub-monorepo communication fediverse
nostream communication fediverse
umbrel-nostr-relay communication fediverse
khatru-pyramid communication fediverse
nostrudel communication fediverse
meshchatx field mesh
ctfd learning courses
moodle learning courses
kiwix-tools learning offline-knowledge
snipe-it productivity business
glpi productivity business
orangehrm productivity business
medusajs-medusa productivity shop
bagisto productivity shop
prestashop productivity shop
abantecart-src productivity shop
shopstr finance bitcoin
reactive-resume productivity utility
languagetool productivity office
dozzle monitoring logs
termix network remote-access
sshwifty network remote-access
weblate developer tools
speedtest-tracker network speedtest
pds communication fediverse
sd-webui-forge-classic ai image
seblucas-cops media books
rvolz-bicbucstriim media books
grimmory media books
azimutt developer database
neodb communication fediverse
monetr finance budget
netboot-xyz network
"""
OVR = {}
for line in OVERRIDES.strip().splitlines():
    parts = line.split()
    OVR[parts[0]] = (parts[1], parts[2].split(";") if len(parts) > 2 else None)

# Deployment classes (TAXONOMY.md §2). Candidates are upstream projects, so they are never
# `private` (owner's own); `core` and `plugin` are the few the OS documents as such.
CORE = {"restic"}  # the OS backup agent and pre-update snapshots (contract §10.1)
PLUGIN = {"hermes-agent",  # agent principal (contract §7, §11.2)
          "uptime-kuma"}   # typed widget + notification action (PLUGIN-UI.md §5)

# Placement (TAXONOMY.md §3.1). Default `any` = any node that runs apps (hub or worker).
HUB = {"adguardhome", "pi-hole", "docker-pi-hole", "dnsserver", "unbound", "headscale",
       "wg-easy", "nginx-proxy-manager", "zoraxy", "openresty-manager", "netboot-xyz"}
WORKER = {"plane", "odoo", "openproject", "elasticsearch", "opensearch", "clickhouse", "superset",
          "docker-superset", "peertube", "discourse", "mastodon-mastodon", "onlyoffice-documentserver",
          "openobserve", "windows", "macos", "windows-arm", "docker-steam-headless",
          "palworld-server-docker", "satisfactory-server", "jenkins", "isaaclab"}
WORKER_AI = {"llm-runtime", "image", "training", "speech", "audio"}


def classify(row):
    rid, v0 = row["id"], row["category_v0"]
    cat, default_sub = V0[v0]
    if v0 == "Productivity & Knowledge" and NOTES_RE.search(rid):
        cat = "notes"
    subs = None
    if rid in OVR:
        cat, subs = OVR[rid]
    if subs is None:
        subs = [t for t, rx in SUBTAGS[cat] if rx.search(rid)]
        if not subs and default_sub and any(t == default_sub for t, _ in SUBTAGS[cat]):
            subs = [default_sub]
    subs = list(dict.fromkeys(subs))[:3]
    valid = {t for t, _ in SUBTAGS[cat]}
    bad = [s for s in subs if s not in valid]
    if bad:
        sys.exit(f"{rid}: subtag {bad} not in the {cat} vocabulary")
    return cat, subs


def release_age_days(last_release):
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})$", last_release)
    if not m or last_release.startswith("none"):
        return None
    return (AS_OF - date(*map(int, m.groups()))).days


def deploy_class(row):
    rid, tier = row["id"], row["tier_proposed"]
    if tier in ("excluded", "parked"):
        return "none"
    if tier == "list-only":
        return "list-only"
    if rid in CORE:
        return "core"
    if rid in PLUGIN:
        return "plugin"
    age = release_age_days(row["last_release"])
    if age is not None and age <= 365 and len(row["stores"]) >= 2:
        return "market-verified"
    return "market-community"


def placement(row, cat, subs):
    rid = row["id"]
    if rid in HUB:
        return "hub"
    if rid in WORKER or (cat == "ai" and WORKER_AI & set(subs)):
        return "worker"
    return "any"


def build_csv():
    raw = CSV_PATH.read_text()
    lines = raw.splitlines(keepends=True)
    comments = [l for l in lines if l.startswith("#")]
    body = "".join(l for l in lines if not l.startswith("#"))
    rows = list(csv.DictReader(io.StringIO(body)))
    header = list(csv.DictReader(io.StringIO(body)).fieldnames)
    if "category_v0" not in header:
        header[header.index("category")] = "category_v0"
        for r in rows:
            r["category_v0"] = r.pop("category")
    base = [h for h in header if h not in ("category", "subtags", "deploy_class", "placement")]
    out_header = base + ["category", "subtags", "deploy_class", "placement"]
    for r in rows:
        cat, subs = classify(r)
        r["category"], r["subtags"] = cat, ";".join(subs)
        r["deploy_class"], r["placement"] = deploy_class(r), placement(r, cat, subs)
    note = ("# Columns category, subtags, deploy_class and placement are generated by scripts/app-taxonomy.py "
            "(docs/design/TAXONOMY.md); category_v0 is the research-run category.\n")
    comments = [c for c in comments if "scripts/app-taxonomy.py" not in c] + [note]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=out_header, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r[k] for k in out_header})
    return "".join(comments) + buf.getvalue(), rows


def build_md(rows):
    md = MD_PATH.read_text()
    by_repo = {r["github"]: r for r in rows}
    name = lambda r: CATEGORIES[r["category"]][0]

    def batch_item(m):
        r = by_repo.get(m.group(1))
        return m.group(0) if r is None else f"(`{m.group(1)}`, {name(r)}, {m.group(2)},"

    def batch_line(line):
        if not line.startswith("**Batch "):
            return line
        return re.sub(r"\(`([^`]+)`, (?:[^,()`]+, )?(L[0-9?]),", batch_item, line)

    def top_row(line):
        m = re.match(r"^(\| \d+ \| [^|]+ \| `([^`]+)` \| )[^|]+( \|.*)$", line)
        if not m or m.group(2) not in by_repo:
            return line
        return f"{m.group(1)}{name(by_repo[m.group(2)])}{m.group(3)}"

    md = "\n".join(top_row(batch_line(l)) for l in md.split("\n"))
    md = md.replace("| # | App | Upstream | Category | Stores |", "| # | App | Upstream | Market category | Stores |")

    cats = Counter(r["category"] for r in rows)
    dcs = Counter(r["deploy_class"] for r in rows)
    pls = Counter(r["placement"] for r in rows)
    queue = Counter(r["category"] for r in rows if r["tier_proposed"] == "queue")
    block = ["<!-- taxonomy:begin (generated by scripts/app-taxonomy.py; do not edit) -->",
             "## Market categories and deployment classes", "",
             "Each row is normalised to the Market taxonomy in [`docs/design/TAXONOMY.md`](../../docs/design/TAXONOMY.md) "
             "by [`scripts/app-taxonomy.py`](../../scripts/app-taxonomy.py): `category` (one of 16), `subtags`, "
             "`deploy_class` and `placement`. The research-run category is kept as `category_v0`. "
             "The batches and the Top 100 table below show the Market category. `deploy_class` here is a target: "
             "CI sets the real tier when an app is added (contract §9.4).", "",
             "| Category | Slug | All rows | `queue` rows |", "|---|---|---|---|"]
    for slug, (disp, _) in CATEGORIES.items():
        block.append(f"| {disp} | `{slug}` | {cats[slug]} | {queue[slug]} |")
    block += ["", "| Deploy class | Rows |", "|---|---|"]
    for k in ("core", "plugin", "market-verified", "market-community", "list-only", "none"):
        block.append(f"| `{k}` | {dcs[k]} |")
    block += ["", "| Placement | Rows |", "|---|---|"]
    for k in ("hub", "worker", "leaf", "any"):
        block.append(f"| `{k}` | {pls[k]} |")
    block.append("<!-- taxonomy:end -->")
    block = "\n".join(block)
    if "<!-- taxonomy:begin" in md:
        md = re.sub(r"<!-- taxonomy:begin.*?<!-- taxonomy:end -->", lambda _: block, md, flags=re.S)
    else:
        md = md.replace("## Proposed queue batches", block + "\n\n## Proposed queue batches", 1)
    return md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    new_csv, rows = build_csv()
    new_md = build_md(rows)
    changed = [p for p, t in ((CSV_PATH, new_csv), (MD_PATH, new_md)) if p.read_text() != t]
    if a.check:
        for p in changed:
            print(f"out of date: {p.relative_to(ROOT)}")
        return 1 if changed else 0
    for p, t in ((CSV_PATH, new_csv), (MD_PATH, new_md)):
        p.write_text(t)
    print(f"{len(rows)} rows; rewrote {len(changed)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
