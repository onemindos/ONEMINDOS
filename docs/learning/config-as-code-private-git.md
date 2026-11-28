<!-- SPDX-License-Identifier: Apache-2.0 -->
# Keep your box settings in private Git

Use a Git server you control, such as a private repository on your own Forgejo
server. If you use a hosted service, set repository visibility to **Private**
before the first push and grant access only to the people who manage the box.
A private repository makes it possible to review, compare, and recover versions
of `settings.yaml` without publishing the names and schedules of your household.

In a local checkout of that private repository, export the box's configuration:

```sh
onemind config export --dir box
git add box/settings.yaml
git diff --cached
git commit -m "Record box settings"
git push
```

Review each file before adding it. `settings.yaml` can reveal the box name, time
zone, update windows, and backup choices. The other YAML files can identify
accounts and roles, installed applications, and when backup or automation jobs
run. Keep any files you choose to track in the same private repository. Exported
YAML excludes passwords and their hashes, passkeys, tokens, and backup
destination credentials. Restrict repository access and keep a separate encrypted
backup of your data and recovery kit.

After editing `box/settings.yaml`, check what would change against the live box:

```sh
onemind config diff --dir box
onemind config apply --dir box
```

The second command requests an approval. Review the plan in **Approvals** on the
box and approve it there. If the box changes in the meantime, run a fresh diff
and request again. You can preview the same files in **Settings → Recovery and
reset → Configuration**. Changes to accounts, app installation, and live
automation schedules use their own settings screens.

Related design: [Box export and import §5.3](../architecture/BOX-EXPORT-IMPORT.md).
