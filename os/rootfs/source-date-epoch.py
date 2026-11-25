#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Print SOURCE_DATE_EPOCH for a Debian archive snapshot timestamp (reproducible-builds.org spec).

The epoch of an image is the moment of the snapshot it is built from (os/rootfs/debian.args SNAPSHOT=), so it is a
function of the commit and needs no clock: two builds of one commit, on any day, use the same value.
  source-date-epoch.py 20261111T000000Z   ->  1794355200
  source-date-epoch.py none               ->  (prints nothing; the Ubuntu hedge leg has no snapshot)
"""
import calendar
import re
import sys
import time


def epoch(snapshot):
    if not re.fullmatch(r"\d{8}T\d{6}Z", snapshot):
        return None
    return calendar.timegm(time.strptime(snapshot, "%Y%m%dT%H%M%SZ"))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: source-date-epoch.py <snapshot timestamp | none>")
    e = epoch(sys.argv[1])
    if e is not None:
        print(e)
