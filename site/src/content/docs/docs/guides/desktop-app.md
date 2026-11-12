---
title: Desktop app
description: A OneMind app for Mac and Windows is being written. Until it ships, use the dashboard in your browser.
status: in-review
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

:::note[Coming soon]
There is no OneMind desktop app on `main` and nothing to download yet. A first version is written and waiting in an open pull request.
:::

## Use the dashboard today

Everything a desktop app would show is already in the dashboard, in any modern browser:

- Browse to your hub at `http://<hub-address>:8080` and sign in with your access token ([First steps](../../getting-started/first-steps/)).
- Bookmark it. The dashboard keeps you signed in only until you close the tab, so keep the token somewhere safe, such as a password manager.
- On a Mac without a spare machine, you can run a practice hub in Docker: [Try it on a Mac](../../getting-started/mac/).

## What the desktop app will do

The first version, for Mac and Windows, is planned as a small app in the menu bar or system tray that:

- **finds your OneMind** on your home network by itself, so you do not need to know its address;
- **pairs** with it once, after you approve the new device on the hub;
- shows the **status** of your machines at a glance and **opens the dashboard** in your browser;
- shows a **notification when a request is waiting**. By design, clicking it opens the request; it never approves it for you.

Later versions are planned to add your OneMind's shared folders as drives on the computer.
