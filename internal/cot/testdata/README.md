<!-- SPDX-License-Identifier: Apache-2.0 -->
# CoT test fixtures

Hand-written for OneMind from the public description of the CoT event format
(Apache-2.0, like the rest of this repo). None of them is copied from a TAK
repository. Coordinates are in open water or on public landmarks; uids and
callsigns are made up.

- `sa-team-member.xml`: a TAK client's own position ("self SA"), with contact,
  group, takv, track and status.
- `spot-marker.xml`: a point marker with remarks and a link to its creator.
- `unknown-detail.xml`: a marker with detail elements this package does not
  model; they must survive a decode and re-encode.
