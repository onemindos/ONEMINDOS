# SPDX-License-Identifier: Apache-2.0
"""Host tool for the Jetson board (runs on the owner's flashing host, Python 3 stdlib only).

  add-data <nvidia_ab.xml> <out.xml>   copy NVIDIA's rootfs A/B layout and add the OneMind data
                                        partition (`onemind-data`) after APP_b, growing to the end of
                                        the disk; NVIDIA's own file is never edited
  record --out <json> [flags]           write the layout record (jetson-layout.json): the flags an
                                        OTA payload must match (onemind_jetson.LAYOUT_FLAGS)

NVIDIA's A/B NVMe layout (r39.2.1 flash_l4t_t234_nvme_rootfs_ab.xml) gives APP and APP_b fixed
sizes (APPSIZE, allocation 0x8) and nothing after APP_b but secondary_gpt, so the disk's rest is
unused; the non-A/B layout grows APP with allocation 0x808, the same attribute used here.
UNVERIFIED on hardware until LT-JET-01 step 1 records `lsblk -o NAME,SIZE,PARTLABEL`.
"""
import argparse, hashlib, json, re, sys
import xml.etree.ElementTree as ET

DATA = "onemind-data"


PARTITION = """
        <partition name="onemind-data" type="data">
            <allocation_policy> sequential </allocation_policy>
            <filesystem_type> basic </filesystem_type>
            <size> 1073741824 </size>
            <file_system_attribute> 0 </file_system_attribute>
            <allocation_attribute> 0x808 </allocation_attribute>
            <align_boundary> 16384 </align_boundary>
            <percent_reserved> 0 </percent_reserved>
            <description> OneMind data partition: k3s and OneMind state, kept across slot switches
              and OTA. Empty at flash; formatted ext4 on first boot (onemind-jetson-data). </description>
        </partition>"""


def add_data(src, dst):
    """Insert the partition as text right after APP_b, so NVIDIA's file (licence header, comments,
    formatting) is copied byte for byte; the XML parser only checks the input and the result."""
    text = open(src, encoding="utf-8").read()
    names = lambda root: [p.get("name") for d in root.iter("device") for p in d.findall("partition")]
    before = names(ET.fromstring(text.encode()))
    if "APP_b" not in before:
        raise SystemExit(f"{src}: no APP_b partition (not a rootfs A/B layout)")
    if DATA in before:
        raise SystemExit(f"{src} already has a {DATA} partition")
    m = re.search(r'<partition\s+name="APP_b"[^>]*>.*?</partition>', text, re.S)
    if not m:
        raise SystemExit(f"{src}: cannot find the APP_b element text")
    out = text[:m.end()] + PARTITION + text[m.end():]
    after = names(ET.fromstring(out.encode()))
    i = after.index("APP_b")
    if after[i + 1] != DATA or len(after) != len(before) + 1:
        raise SystemExit("internal error: onemind-data not placed right after APP_b")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(out)


def record(a):
    with open(a.layout_xml, "rb") as f:
        xml_sha = hashlib.sha256(f.read()).hexdigest()
    rec = {"schema": "onemind.io/jetson-layout/v1", "compatible": a.compatible, "target_board": a.target_board,
           "rootfs_ab": True, "rootfs_retry_count_max": a.retry, "external_device": a.external_device,
           "rootfs_size": a.rootfs_size, "rootfs_enc": False, "uefi_secure_boot": False,
           "l4t": a.l4t, "layout_xml": a.layout_xml_name, "layout_xml_sha256": xml_sha}
    with open(a.out, "w") as f:
        json.dump(rec, f, indent=2, sort_keys=True)
        f.write("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jetson_layout.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ad = sub.add_parser("add-data"); ad.add_argument("src"); ad.add_argument("dst")
    r = sub.add_parser("record")
    r.add_argument("--out", required=True); r.add_argument("--layout-xml", required=True)
    r.add_argument("--layout-xml-name", required=True); r.add_argument("--l4t", required=True)
    r.add_argument("--compatible", default="onemind-jetson-orin"); r.add_argument("--target-board", required=True)
    r.add_argument("--external-device", required=True); r.add_argument("--rootfs-size", default="nvidia-default")
    r.add_argument("--retry", type=int, default=3)
    a = ap.parse_args(argv)
    if a.cmd == "add-data":
        add_data(a.src, a.dst)
    else:
        record(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
