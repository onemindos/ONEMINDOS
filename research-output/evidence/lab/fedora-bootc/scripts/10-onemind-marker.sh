#!/bin/bash
# greenboot required check: the OneMind image marker must be present and non-empty.
test -s /usr/share/onemind/version || { echo "onemind marker missing" >&2; exit 1; }
echo "onemind image: $(cat /usr/share/onemind/version)"
