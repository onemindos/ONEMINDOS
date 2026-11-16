<!-- SPDX-License-Identifier: Apache-2.0 -->
# Phone app, live: from the Mac simulator to your iPhone

**For:** Zeus · **Serves:** M-LIVE (founder goal 2026-11-15), issue [#314](https://github.com/onemindos/ONEMINDOS/issues/314) (MOB-LIVE-01), [#234](https://github.com/onemindos/ONEMINDOS/issues/234) (the box this app talks to).
**Honest status:** the app's data layer and all main screens were run against a **real gateway** (not the demo) by tests, see §6. The simulator and iPhone steps (§1, §3, §4) are **later**: founder decision 2026-11-15, the iOS Simulator runtime (a multi-GB download) is not installed yet, so no agent has run them. They are written so you can follow them when you are ready; tell us what differs.

## 0. Words you need
- **Hub:** the OneMind box (a VM on your Mac, the Beelink, a droplet). The phone talks only to it.
- **Simulator:** an iPhone that runs as a window on your Mac. Free, no Apple account.
- **Metro:** the small program on your Mac that serves the app's code to a *development* build while you work.
- **Owner token:** the long secret the box shows once at setup. It is your password for the phone until passkeys work on the phone (§7).

## 1. One-time setup on the Mac (LATER: needs the simulator runtime)
```sh
brew install node@22          # skip if `node -v` already says 22 or newer
cd <your ONEMINDOS folder>/mobile
npm ci
```
In **Xcode → Settings → Components**, install the **iOS Simulator** runtime (a large download, several GB). Check with `xcrun simctl list devices`: it must list iPhones.

## 2. Pick the hub the phone will talk to
| You want | Hub address to type in the app |
|---|---|
| A hub running on this Mac (developer gateway) | `http://127.0.0.1:8080` (simulator only; see §2a) |
| The Mac UTM VM from #234 | `http://onemind.local:8080` (or the VM's IP, port 8080) |
| The Beelink | `http://onemind.local:8080` (or its IP) |

Plain `http://` shows a yellow warning in the app: what you send can be read on the network. That is acceptable on your own home Wi-Fi while testing; the `https://…:8443` address uses a certificate your phone does not trust yet, so it fails. iOS allows plain http to local names and addresses (`NSAllowsLocalNetworking` in `mobile/app.json`).

### 2a. A throwaway hub on the Mac (no VM), for trying the app
```sh
make -C core run                                  # gateway on 127.0.0.1:8080, dev tokens
# if port 8080 is taken: ONEMIND_PORT=8099 make -C core run
# to let your iPhone reach it as well: ONEMIND_HOST=0.0.0.0 make -C core run
```
The dev owner token is `dev-owner-token-change-me`. **These tokens are public in the repo: use them only for this throwaway hub and never on a box other people can reach.**

For a real box (#234) the owner token appears **once** at setup (`docs/see-onemind/`, when merged): copy it into your password manager.

## 3. Run the app in the Mac simulator (LATER)
```sh
cd mobile
npx expo run:ios        # builds, installs, opens the Simulator, starts Metro (first build takes several minutes)
```
Walk this list. Each line is something the app must do; if one fails, note the screen and what you saw.

1. **Connect:** type the hub address, tap **Use an access token instead**, paste the token, tap **Connect with the token**. You land on **Home**, showing the **hub's** name (not "OneMind Demo").
2. **Home:** nodes, installed apps, pending approvals, recent activity. A new box shows one node (itself).
3. **Apps:** the Market list. Open an app, tap **Ask to install**. The app only **files a request**; it never installs by itself.
4. **Approvals:** the request is listed with its exact parameters. **Approve** or **Deny**. (With only a token and no passkey, an owner can approve from the phone; with a passkey the phone asks for it.)
5. **More → Settings:** shows who you are (role from the hub), the connection state and **Disconnect**.
6. Kill the app and open it again: it signs in by itself (the token is kept in the iPhone's Keychain).

## 4. Run it on your real iPhone (same Wi-Fi as the hub) (LATER, UNVERIFIED)
1. iPhone: **Settings → Privacy & Security → Developer Mode → on** (restarts the phone).
2. Plug the iPhone into the Mac, unlock it, tap **Trust**.
3. Xcode needs a signing identity: **Xcode → Settings → Accounts → add your Apple ID** (a free account is enough; the app then expires after 7 days and must be rebuilt).
4. Build onto the phone:
```sh
cd mobile
npx expo run:ios --device     # pick your iPhone from the list; if asked for a team, choose your Apple ID
```
5. First launch: iPhone asks for **Local Network** access. Tap **Allow**; without it the phone cannot see the hub.
6. The hub must be reachable from the phone: a VM must use **bridged networking** (UTM → the VM → Network → Bridged), not "Shared"; and the Mac, phone and hub must be on the same Wi-Fi network (a guest network usually isolates devices). Use the hub's **IP address** if `onemind.local` does not resolve on the phone.
7. Do the §3 list on the phone.

## 5. If something does not work
| What you see | Likely cause | Fix |
|---|---|---|
| "The hub did not answer within 10 s" | wrong address, VM on "Shared" network, phone on another Wi-Fi, Local Network permission denied | check the address in Safari on the phone first; iPhone Settings → OneMind → Local Network on |
| "Not linked to this name" on passkey sign-in | passkeys need a public, linked name (§7) | use **Use an access token instead** |
| Connect says unauthorized | token typed wrong or the hub was reset | use the token shown at setup; on the throwaway hub the dev token |
| Xcode: "No signing certificate" | no Apple ID in Xcode | §4 step 3 |
| Files screen: "storage not available" | the hub has no shared-files storage yet | expected on a fresh box |

## 6. What was verified by an agent (2026-11-15, evidence)
Against the developer gateway (`make -C core run`, real SQLite and NATS, the real Market seed), with the app's own code:
- `mobile/src/api/live.test.ts`: health, `/openapi.json` feature detection, `/v1/instance`, `/v1/nodes`, `/v1/apps`, `/v1/me`, alerts, notifications, backups, automation, and a full **request → pending → deny** cycle. Run it with `ONEMIND_LIVE_HUB=http://127.0.0.1:8099 npx jest src/api/live.test.ts`.
- `mobile/src/live.app.test.tsx`: the whole app on a real hub: Connect with a token → Home (not the demo's) → Apps (the hub's own catalog) → Approvals → Settings, with no error banner. Same environment variable.
- Not covered by these tests (needs a device): drawing on a real screen, passkeys, push, the live-update stream (it needs a real network stack; the tests use the polling fallback), the iOS Local Network prompt.

## 7. Passkeys on the phone need one decision
A passkey only works for a name the app is linked to. A box called `onemind.local` cannot be linked. See `mobile/README.md`, "Passkeys: one decision needed". Until you choose, sign in with the owner token (this guide).
