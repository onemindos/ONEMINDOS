---
title: Phone app
description: The OneMind app for Android and iPhone. What it does, what it does not do yet, and how developers can try it today.
status: mixed
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

:::note[Not in the app stores yet]
The phone app's code is on `main` and works in iPhone and Android test builds, but it is **not** in the App Store or Google Play. Today you can only run it by building it yourself from the source, which needs developer tools (Xcode for iPhone, the Android SDK for Android). Everyone else: use the dashboard in your phone's browser, which is built to work on a phone-sized screen.
:::

The phone app is a window into your OneMind, not part of it. It talks **only to your own hub**; nothing goes through a OneMind cloud. Like the dashboard, it never decides anything itself: every change is a request on the hub, and only an owner can approve it.

## What it does <span class="om-tag om-tag--warn">build it yourself</span>

| Screen | What you see and do |
|---|---|
| **Connect** | Type your hub's address and your access token. The app checks the token with the hub before saving anything. |
| **Home** | Your OneMind's name and version, machines by status, installed apps, waiting approvals and recent activity. |
| **Nodes** | One card per machine. A machine that has stopped reporting says "Not live" and when its numbers are from. |
| **Apps** | The catalog with licence, tier, last scan and links. **Ask to install** or remove creates a request; it is greyed out, with the reason, when the app is [blocked](../apps/#why-an-app-can-be-blocked). |
| **Approvals** | Waiting requests with the exact request, who asked (a person or an AI agent), when, and when it expires. **Approve** or **Deny**. The tab shows how many are waiting. |
| **Activity** | Every request, newest first, with who asked, who decided and the result. |
| **Settings** | The connection, notification permission, **Send a test alert**, and **Disconnect**, which wipes the address and token from the phone. |

**Your token is kept in the phone's secure store** (the iPhone Keychain, or Android's encrypted storage). On iPhone it is never synced to iCloud or restored onto another phone.

## Try the demo

On the Connect screen, under **Or try the demo**, choose Owner, Adult or Agent. The demo runs entirely on the phone with made-up data (four machines, six apps, one waiting request from an AI agent) and never uses the network. It is a good way to see what each role may do.

## Connect to your hub

1. Your phone must be able to reach the hub: on the same Wi-Fi, or through a private VPN (see [Remote access](../remote-access/)).
2. Enter the hub's address, for example `http://<hub-address>:8080`, and the owner token.
3. Tap **Connect**.

If the address starts with `http://`, the app warns you that the token can be read by anyone watching the network. That is true of a developer install today; use it only on a network you trust. Requests give up after 10 seconds, so a wrong address fails quickly.

The app cannot know your role until the hub tells it. If you connect with a token that is not the owner's, the Approve button turns off after the hub refuses the first attempt.

## Notifications

**Today:** while the app is open, it checks the hub every 10 seconds and shows a notification for a new request waiting for approval, a request that finished, a machine going offline or coming back, and a new machine joining. **Nothing arrives while the app is closed.**

**Coming soon:** real push notifications that never show your data to Apple or Google. On Android through your own ntfy server (UnifiedPush); on iPhone, a push that only says "something needs you", after which the phone fetches the details from your own hub.

## Coming soon

- Store releases for Android and iPhone.
- Pairing by scanning a QR code, and HTTPS with your box's own certificate.
- **Phone photo backup** to your OneMind. The phone side is built (backup off by default, Wi-Fi only by default, an optional charging-only rule, all photos or chosen albums, uploads that resume after an interruption), and the app shows a Photo backup card on Home. But the Photos service on the hub that receives the photos does not exist yet, so the app says so and sends nothing.
- An audit log screen, and more than one hub at a time.

## For developers

Build steps for the iPhone simulator and an Android debug build are in [`mobile/README.md`](https://github.com/onemindos/ONEMINDOS/blob/main/mobile/README.md). The demo also opens from the link `onemind://demo?as=owner`.
