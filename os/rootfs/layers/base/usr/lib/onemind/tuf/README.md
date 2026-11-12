<!-- SPDX-License-Identifier: Apache-2.0 -->
# TUF trust roots shipped in the image

`onemindd update` (internal/update) trusts `/usr/lib/onemind/tuf/<channel>/root.json` and nothing on `/data` (os/update/CHANNEL.md §2).
The release pipeline places each channel's `root.json` here after the offline root ceremony. Until a root is present, `onemind-update.service` stays inert (`ConditionPathExistsGlob`).
