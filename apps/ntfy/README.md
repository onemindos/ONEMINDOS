<!-- SPDX-License-Identifier: Apache-2.0 -->
# ntfy

**What it is:** ntfy is a small HTTP publish/subscribe notification server. A script, a service or the OneMind gateway sends a message with a plain `PUT`/`POST` to a *topic*, and phones (the ntfy Android/iOS apps), browsers and desktops subscribed to that topic get a push notification. In OneMind it is the v0 delivery path for alerts and approval requests to the owner's phone (brief 30 D-B9.6, Alerts module), and the contract §7 demo installs it ("install ntfy").

| | |
|---|---|
| Upstream | https://github.com/binwiederhier/ntfy |
| Docs | https://docs.ntfy.sh/ |
| Website | https://ntfy.sh/ |
| Version | v2.37.2 (released 2026-11-04, tag commit `05109571fd09`) |
| Image | `docker.io/binwiederhier/ntfy:v2.37.2@sha256:1875ddcf815c8a3c981d6d78c67a93452d0abba79b1ab9520b1f5f5238902bd7` (multi-arch index: linux/amd64, linux/arm64, linux/arm/v6, linux/arm/v7) |
| Licence | `Apache-2.0 OR GPL-2.0` (dual: [LICENSE](https://github.com/binwiederhier/ntfy/blob/05109571fd0931affb6f92b17bbfd62c4d2ea68a/LICENSE) and [LICENSE.GPLv2](https://github.com/binwiederhier/ntfy/blob/05109571fd0931affb6f92b17bbfd62c4d2ea68a/LICENSE.GPLv2)). OneMind uses it under the Apache-2.0 option. Market class **L1** (permissive): `research-output/evidence/license-matrix.csv` row "ntfy (push, APPS Alerts)" [C-LIC-050], `research-output/13-apps-market-plugins.md` |
| Icon | A neutral generated icon with initials. The ntfy name and logo are trademarks of ntfy LLC and need written consent to use with a product ([docs/terms.md](https://github.com/binwiederhier/ntfy/blob/05109571fd0931affb6f92b17bbfd62c4d2ea68a/docs/terms.md#trademarks)), so the upstream logo is not shipped. |

## How it runs here

- One `Deployment` (`Recreate`, 1 replica) and a `ClusterIP` Service `ntfy` on port **8080** (the web UI and API).
- State lives on the 1 GiB PVC `ntfy-data` at `/var/lib/ntfy`: `cache.db` (message cache, so subscribers can fetch missed messages after a restart) and `user.db` (users and access control).
- It runs as UID/GID 1000, not root, with no privilege escalation, all Linux capabilities dropped and the default seccomp profile. The image itself has no `USER`, but upstream documents running it as any `UID:GID`. Because a non-root process cannot bind port 80 without `NET_BIND_SERVICE`, it listens on `:8080` (`NTFY_LISTEN_HTTP`).
- **Private by default:** `NTFY_AUTH_DEFAULT_ACCESS=deny-all` with login enabled, as upstream recommends for a private instance. Nobody can read or write a topic until the owner creates a user.
- Probes: readiness `GET /v1/ready`, liveness `GET /v1/health` ([docs: Health checks](https://docs.ntfy.sh/config/#health-checks)).

## Resources

| | CPU | Memory |
|---|---|---|
| Requests | 150m | 150Mi |
| Limits | 500m | 300Mi |

These come from the upstream Kubernetes and Kustomize examples ([docs: Kubernetes](https://docs.ntfy.sh/install/#kubernetes)). The Market lists `minMemoryMb: 256`, which fits a Pi 5 alongside the other seed apps.

## First run

Source: [docs: Access control](https://docs.ntfy.sh/config/#access-control), [Users and roles](https://docs.ntfy.sh/config/#users-and-roles) and [Example: private instance](https://docs.ntfy.sh/config/#example-private-instance).

1. Install ntfy from the Market and approve the action. It installs into the namespace `app-ntfy`.
2. Create an admin user. The command prompts for a password, so run it in a terminal:
   ```sh
   kubectl -n app-ntfy exec -it deploy/ntfy -- ntfy user add --role=admin <username>
   ```
   An `admin` user can read and write every topic. For a less-privileged user (for example one per phone), add it without `--role=admin` and grant topics with `ntfy access <username> <topic> rw`.
3. Open the web UI on port 8080 (for a quick test: `kubectl -n app-ntfy port-forward svc/ntfy 8080:8080`, then http://localhost:8080) and sign in.
4. Send a test message (with the user created above):
   ```sh
   curl -u <username> -d "Hello from OneMind" http://localhost:8080/onemind-test
   ```
5. On the phone, install the ntfy app, add this server and the user, and subscribe to the topic.

Phones outside the home network need the server reachable over HTTPS, and then `NTFY_BASE_URL` set to that URL. Attachments, Web Push and iOS instant notifications also need `base-url` ([docs: Configuration](https://docs.ntfy.sh/config/)). They are off in this v0 package.

## Not done yet

- No security scan summary yet: the Trivy, ClamAV and smoke-test parts of the §9.4 gate come in a later wave.
- `readOnlyRootFilesystem` is not set: it has not been tested against this image.
