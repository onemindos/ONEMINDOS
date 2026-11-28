#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Require TLS on TAK's configured network inputs and connectors before starting the server.
# Usage: onemind-tak-check-config.sh [CoreConfig.xml]
set -euo pipefail
exec python3 -I - "${1:-/data/config/CoreConfig.xml}" <<'PY'
import sys
from xml.etree import ElementTree

config = sys.argv[1]
ns = "{http://bbn.com/marti/xml/config}"


def refuse(reason):
    sys.exit(f"onemind: {config}: {reason}, refusing to start")


class ConfigTreeBuilder(ElementTree.TreeBuilder):
    def doctype(self, name, pubid, system):
        # Use the same self-contained document for both validation and startup.
        refuse("CoreConfig must not declare a DTD")


try:
    parser = ElementTree.XMLParser(target=ConfigTreeBuilder())
    root = ElementTree.parse(config, parser=parser).getroot()
except (OSError, ElementTree.ParseError, LookupError, ValueError):
    refuse("cannot read or parse CoreConfig XML")

networks = root.findall(ns + "network")
if root.tag != ns + "Configuration" or len(networks) != 1:
    refuse("expected TAK Configuration with one network section")

# CoreConfig.xsd declares datafeed as an input subtype and defaults connector tls to true.
input_types = {ns + "input", ns + "datafeed"}
listener_types = input_types | {ns + "connector"}
for listener in networks[0]:
    if listener.tag not in listener_types:
        continue
    if listener.tag in input_types and listener.get("protocol") != "tls":
        refuse('network inputs require protocol="tls"')
    if listener.get("tls", "true").strip() not in {"true", "1"}:
        refuse("network listeners require TLS")
PY
