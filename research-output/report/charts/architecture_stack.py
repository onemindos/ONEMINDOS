"""Draws the OneMind layered architecture (report figure). Content from 01 §1, §8 (rev. 4) and 10/29."""
import sys, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
out = sys.argv[1]
layers = [  # (title, fill, edge, boxes)
 ("7 · Cloud (optional, self-hostable): today's DOKS cluster becomes the hub / Omni tier", "#F1ECFA", "#7B5EA7",
  ["Cloud hub\nupdate server · relay", "Market mirror\n(offline bundles too)", "Off-site encrypted\nbackups", "Build + signing CI\n(offline root key)", "Backstage\ndeveloper portal"]),
 ("6 · Dashboard and clients", "#EAF5EA", "#3F8F4F",
  ["OneMind dashboard\n(one web app / PWA)", "iOS · Android · Mac · Win\npush · QR · passkeys", "ATAK · iTAK\nCloudTAK", "XR browsers\nAndroid XR · visionOS", "Omarchy\nplugin"]),
 ("5 · AI and agents", "#FDF0DE", "#C07A1F",
  ["Hermes agents\none identity, many bodies", "Outside AI clients\n(Claude, ChatGPT) via MCP", "Local model router\nllama.cpp · vLLM", "Agent sandbox\n(gVisor)"]),
 ("4 · Capability layer: the ONLY door for people, apps and AI", "#FFF3C4", "#C9A227",
  ["Capability gateway\nMCP · REST · CLI · Skills", "Approvals\n(phone, passkey)", "Action ledger\n(append-only audit)", "Identity\nlocal OIDC, offline", "aiPolicy flags\n(may this go to AI?)"]),
 ("3 · k3s app platform (every box with ≥ 4 GB RAM and an SSD)", "#E3EDFA", "#2F5D9E",
  ["Market controller\nonemind.app.yaml → Helm", "NATS JetStream\nTHE BUS", "Apps: Home Assistant,\nTAK Server, Frigate …", "Backup agent\nrestic, verified restores", "Capability detection\nNFD + GPU discovery"]),
 ("2 · Node: the OneMind OS image (one per box)", "#ECEFF4", "#5A6B85",
  ["Read-only root, A/B\nUbuntu 26.04 (Debian leg)", "RAUC updates +\nfresh-signal gate", "LUKS2 data\npartition", "Signed extensions\nsysext · driver packs", "Flavors: Jetson L4T,\nGPU-server Ubuntu"]),
 ("1 · Devices", "#FBEDED", "#B04A4A",
  ["Robots\nROS 2 in containers", "Drones\nPX4 · MAVLink", "IoT: Zigbee, Thread,\nMatter, ESPHome", "IIoT: OPC UA, Modbus,\nSparkplug B, CAN", "Mesh: Meshtastic,\nLoRaWAN, batman-adv", "Small devices\n= NATS leaf"]),
]
W, H = 15.5, 13.2
fig, ax = plt.subplots(figsize=(W, H)); ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")
x0, x1 = 0.2, 12.4; band_h = 1.62; gap = 0.18; top = H - 0.25
ys = []
for i, (title, fill, edge, boxes) in enumerate(layers):
    y = top - (i + 1) * band_h - i * gap; ys.append(y)
    ax.add_patch(FancyBboxPatch((x0, y), x1 - x0, band_h, boxstyle="round,pad=0.02,rounding_size=0.12", fc=fill, ec=edge, lw=1.6))
    ax.text(x0 + 0.15, y + band_h - 0.2, title, fontsize=11.5, fontweight="bold", color="#1A202C", va="top")
    n = len(boxes); bw = (x1 - x0 - 0.3 - (n - 1) * 0.15) / n
    for j, b in enumerate(boxes):
        bx = x0 + 0.15 + j * (bw + 0.15)
        ax.add_patch(FancyBboxPatch((bx, y + 0.12), bw, band_h - 0.66, boxstyle="round,pad=0.02,rounding_size=0.08", fc="white", ec=edge, lw=0.9))
        ax.text(bx + bw / 2, y + 0.12 + (band_h - 0.66) / 2, b, fontsize=9.0, ha="center", va="center", color="#1A202C")
# Marketplace column
mx0, mx1 = 12.75, W - 0.15
my0, my1 = ys[4], ys[0] + band_h
ax.add_patch(FancyBboxPatch((mx0, my0), mx1 - mx0, my1 - my0, boxstyle="round,pad=0.02,rounding_size=0.12", fc="#E9F5F5", ec="#2F8F8F", lw=1.6))
ax.text((mx0 + mx1) / 2, my1 - 0.2, "Marketplace", fontsize=11.5, fontweight="bold", ha="center", va="top")
steps = ["Third-party\npublisher", "onemind plugin\ninit · validate", "Automated +\nhuman review", "OneMind\ncountersignature", "Signed index\n+ kill list"]
sh = (my1 - my0 - 0.9) / len(steps)
for k, s in enumerate(steps):
    sy = my1 - 0.6 - (k + 1) * sh
    ax.add_patch(FancyBboxPatch((mx0 + 0.15, sy + 0.08), mx1 - mx0 - 0.3, sh - 0.25, boxstyle="round,pad=0.02,rounding_size=0.08", fc="white", ec="#2F8F8F", lw=0.9))
    ax.text((mx0 + mx1) / 2, sy + 0.08 + (sh - 0.25) / 2, s, fontsize=9.4, ha="center", va="center")
    if k < len(steps) - 1:
        ax.annotate("", xy=((mx0 + mx1) / 2, sy + 0.02), xytext=((mx0 + mx1) / 2, sy + 0.12), arrowprops=dict(arrowstyle="-|>", color="#2F8F8F"))
ax.annotate("", xy=(x1 + 0.02, ys[4] + band_h / 2), xytext=(mx0, ys[4] + band_h / 2), arrowprops=dict(arrowstyle="-|>", color="#2F8F8F", lw=1.8))
ax.text((x1 + mx0) / 2, ys[4] + band_h / 2 + 0.12, "signed apps", fontsize=8, ha="center", rotation=0, color="#2F8F8F")
# key flows on the left margin as notes
notes = [(ys[1] + 0.05, "every human action\npasses the gateway"), (ys[2] + 0.05, "every AI action\npasses the gateway"), (ys[6] + band_h + 0.02, "adapters, bridges and leaf links feed the bus")]
for y, t in notes:
    ax.text(x1 - 0.12, y, "▼ " + t if "\n" not in t else t, fontsize=8.2, ha="right", va="bottom", style="italic", color="#4A5568")
ax.text(0.2, 0.05, "Read bottom-up: a device joins a node; the node's image boots k3s; apps declare capabilities; the gateway is the single enforcement point "
        "for people and AI; the cloud is optional.", fontsize=9, color="#4A5568")
plt.savefig(out, dpi=110, bbox_inches="tight", facecolor="white")
