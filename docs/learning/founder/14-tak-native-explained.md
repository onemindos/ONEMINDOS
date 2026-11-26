<!-- SPDX-License-Identifier: Apache-2.0 -->
# "OneMind is TAK native", explained

**Asked by:** the founder, 2026-11-26 ("a native cot bridge ... it will also connect to our map ... as native as we can ... onemindos is tak native").
**Serves:** decision [D-032](../../DECISIONS.md), M-LIVE [#234](https://github.com/onemindos/ONEMINDOS/issues/234). The full technical design, with sources, is [docs/architecture/TAK-NATIVE-COT-BRIDGE.md](../../architecture/TAK-NATIVE-COT-BRIDGE.md).

## The short answer

OneMind will **speak TAK's language itself**. When you switch it on, every phone or laptop running ATAK, iTAK, WinTAK or TAKX on the same network sees your OneMind machines, sensors and cameras as dots on its map, and OneMind's map shows the dots those TAK devices share. No TAK Server is needed for that. TAK Server and TAKX become optional apps you can install from the Market when you want the extra power.

## The words

- **TAK** (Team Awareness Kit): the family of shared-map apps. ATAK (Android), iTAK (iPhone), WinTAK and its successor TAKX (desktop), and TAK Server (the hub that relays between them and adds missions, file sharing and links between organisations).
- **CoT** (Cursor on Target): the message format. One CoT message is a tiny XML note: *"thing X, of kind Y, is at this latitude and longitude, valid from this time until that time."* A TAK map draws a dot for each one.
- **Stale time:** when the message stops being true. After it, the dot fades. That is how a TAK map stays current without anyone deleting anything.
- **Multicast:** one message sent to "everyone on this network who is listening". TAK phones on the same Wi-Fi share their positions this way on one fixed address (`239.2.3.1`, port `6969`), with no server.
- **Bridge:** a small translator. Ours turns OneMind's positions into CoT and CoT into OneMind map markers.
- **Protobuf:** a compact binary format. Newer TAK devices can switch from XML to it ("TAK Protocol version 1"); we start with XML and add protobuf later.

## Why build it into OneMind instead of making it an app

You asked for "as native as we can". A Market app would have three problems today:

1. **It could not hear the TAK phones.** Listening to multicast needs the app to sit directly on the box's network. Apps are not allowed to do that yet (that permission, called E2, comes later), for safety.
2. **It would stop when the app platform stops.** The built-in bridge runs inside `onemindd`, the small program that runs on every OneMind machine, even a Raspberry Pi in a vehicle, even when the app platform (k3s) is down.
3. **"TAK native" would really mean "TAK installable".**

So **the design recommends** making the bridge part of OneMind, but **off until you turn it on** in Settings → Apps. This is a recommendation, not yet your decision: built-in vs plugin is listed as open in D-032 and the design doc §13. Its only connection to the rest of OneMind is the gateway, so it could still become a separately updated plugin later without changing anything else.

TAK Server and TAKX are different: they are big (TAK Server needs at least 4 CPU cores and 8 GB of memory, plus a database) and they are GPL-3.0 licensed, so they stay **out of the base image** and become optional Market apps, each built in its own repo. OneMind's own code stays Apache-2.0 and never copies GPL code.

## What it will and will not do

**Will:**
- Show your box, machines, sensors, cameras and alerts with a location on TAK devices on your network, and later on a TAK Server you choose.
- Show TAK markers and team positions on the OneMind map, as a layer you can hide.
- Work fully offline: no internet, no server, no cloud.

**Will never:**
- **Act on a TAK message.** If a TAK device sends something that asks OneMind to *do* something (a task, a route, "point the camera here"), it becomes an approval card. Only a person approves (D-027).
- **Share a person's location** unless you opt that person in and they are an adult.
- **Share a child's location.** Never, whatever any other setting says. This rule is written into the code itself, not only into the settings: the translator refuses a person unless it is told both "adult" and "opted in", so a forgotten setting means nothing is sent.
- **Make a radio transmit.** Radios still transmit only on your tap (D-024).
- **Share anything until you turn it on.** It is off by default, and it stays on your local network unless you link a TAK Server.

## How it will be built (the phases)

1. **P1:** the translator (done in this first PR, with tests) and the service. Your machines show up on ATAK on the same Wi-Fi and on the OneMind map.
2. **P2:** TAK markers show on the OneMind map.
3. **P3:** a secure link to a TAK Server, with certificates OneMind keeps on the box.
4. **P4:** TAK Server and TAKX as Market apps.
5. **P5:** tasking from TAK becomes approval cards.
6. **P6:** the compact protobuf format.

## A small surprise from checking the sources

There is **no map in the OneMind dashboard yet**. The map that exists is the **Offline Maps** app, and the gateway already serves live positions, sites and map packs. So "connect to our map" means: feed the bridge's markers into the same position stream the Offline Maps viewer (and later the dashboard map) reads.

## What we still need from you

The open questions are listed in the design doc, §13. The main ones: is this 1.0 or 1.1; when you turn it on, should it share only the box or all machines; and which TAK Server should it link to first.
