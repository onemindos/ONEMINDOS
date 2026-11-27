#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check a resolved Android release classpath and the packaged manifest against D-032."""

import argparse
import re
from pathlib import Path
from xml.etree import ElementTree

DEPENDENCY = re.compile(r"\bcom\.google\.(?:android\.gms|firebase|mlkit)(?:[.:]|\b)")
MANIFEST_ENTRY = re.compile(
    r"\b(?:com\.google\.(?:android\.gms|android\.c2dm|firebase|mlkit)|"
    r"expo\.modules\.notifications\.service\.ExpoFirebaseMessagingService)(?:\.|\b)"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dependencies", type=Path, help="Gradle releaseRuntimeClasspath report")
    parser.add_argument("manifest", type=Path, help="APK manifest XML from apkanalyzer")
    args = parser.parse_args()

    lines = args.dependencies.read_text().splitlines()
    if not any(line.startswith("releaseRuntimeClasspath ") for line in lines):
        parser.error("missing Gradle releaseRuntimeClasspath report")
    root = ElementTree.parse(args.manifest).getroot()
    if root.tag != "manifest" or root.find("application") is None:
        parser.error("missing packaged Android application manifest")

    dependencies = sorted({line.strip() for line in lines if DEPENDENCY.search(line)})
    manifest = sorted({value for element in root.iter() for value in element.attrib.values()
                       if MANIFEST_ENTRY.search(value)})
    if dependencies or manifest:
        for value in dependencies:
            print(f"Forbidden Android dependency: {value}")
        for value in manifest:
            print(f"Forbidden Android manifest entry: {value}")
        return 1
    print("Android release contains no Google Play Services, Firebase or ML Kit dependencies or manifest entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
