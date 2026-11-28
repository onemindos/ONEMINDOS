# SPDX-License-Identifier: Apache-2.0
"""Live CUPS regression, run as root in an isolated OneMind rootfs container.

Mount the repo at /src and run python3 -I /src/test/printing/check.py.
Use the default bridge network so TCP has a non-loopback address to test.
"""

import http.client
import os
from pathlib import Path
import re
import select
import socket
import ssl
import struct
import subprocess
import time


CUPS = Path("/etc/cups")
SOCKET = "/run/cups/cups.sock"
QUEUE = "OneMindRelease"
RESOURCE = f"/printers/{QUEUE}"
PAGE = Path("/usr/share/cups/data/default-testpage.pdf")


def run(*argv, **kwargs):
    return subprocess.run(argv, capture_output=True, text=True, check=True, timeout=15, **kwargs).stdout


def attribute(tag, name, value):
    name = name.encode()
    value = value.encode()
    return bytes([tag]) + struct.pack("!H", len(name)) + name + struct.pack("!H", len(value)) + value


def ipp(host, operation, *, job=None, document=b""):
    resource = RESOURCE if job is None else f"/jobs/{job}"
    uri = f"ipps://{host}:631{resource}"
    target = "printer-uri" if job is None else "job-uri"
    data = (struct.pack("!BBHI", 2, 0, operation, 1) + b"\x01"
            + attribute(0x47, "attributes-charset", "utf-8")
            + attribute(0x48, "attributes-natural-language", "en")
            + attribute(0x45, target, uri)
            + attribute(0x42, "requesting-user-name", "root"))
    if document:
        data += attribute(0x49, "document-format", "application/pdf")
    data += b"\x03" + document
    conn = http.client.HTTPSConnection(host, 631, timeout=10, context=ssl._create_unverified_context())
    try:
        conn.request("POST", resource, data, {"Content-Type": "application/ipp"})
        res = conn.getresponse()
        payload = res.read()
        code = struct.unpack_from("!H", payload, 2)[0] if res.status == 200 else None
        return res.status, code
    finally:
        conn.close()


def assert_denied(host, operation, **kwargs):
    result = ipp(host, operation, **kwargs)
    assert result in {(401, None), (403, None), (200, 0x0401), (200, 0x0402), (200, 0x0403)}, (
        f"operation {operation:#x} was not denied on {host}: {result}")


def wait_for_cups(process):
    for _ in range(100):
        assert process.poll() is None, "cupsd exited during startup"
        if Path(SOCKET).is_socket():
            return
        time.sleep(0.1)
    raise AssertionError("CUPS local socket did not become ready")


def assert_device_tls():
    key_dir = CUPS / "ssl"
    assert not list(key_dir.glob("*.key")), "fixture starts with a generated CUPS key"
    conn = http.client.HTTPSConnection("127.0.0.1", 631, timeout=15,
                                       context=ssl._create_unverified_context())
    try:
        conn.request("GET", "/")
        response = conn.getresponse()
        assert response.status == 200, response.status
        response.read()
    finally:
        conn.close()
    keys = list(key_dir.glob("*.key"))
    assert len(keys) == 1 and keys[0].stat().st_mode & 0o077 == 0, keys


def check_release(receiver):
    port = receiver.getsockname()[1]
    run("lpadmin", "-h", SOCKET, "-p", QUEUE, "-E", "-v", f"socket://127.0.0.1:{port}",
        "-m", "drv:///sample.drv/generic.ppd", "-o", "printer-is-shared=true")
    lan = socket.gethostbyname(socket.gethostname())
    assert not lan.startswith("127."), "the fixture needs a non-loopback LAN address"
    assert ipp(lan, 0x000B) == (200, 0), "Get-Printer-Attributes must reach the shared queue from the LAN"
    document = PAGE.read_bytes()
    for host in (lan, "127.0.0.1"):
        assert_denied(host, 0x0002, document=document)  # Print-Job
        assert_denied(host, 0x0005)  # Create-Job
    local_submit = subprocess.run(
        ["runuser", "-u", "nobody", "--", "lp", "-h", SOCKET, "-d", QUEUE, str(PAGE)],
        stdin=subprocess.DEVNULL, capture_output=True, timeout=15,
    )
    assert local_submit.returncode != 0, "unprivileged Unix socket print succeeded"
    assert not select.select([receiver], [], [], 0.1)[0], "a rejected job reached the printer"

    queued = run("lp", "-h", SOCKET, "-d", QUEUE, "-H", "hold", "-o", "raw", str(PAGE))
    job_id = re.search(rf"{QUEUE}-(\d+)", queued).group(1)
    assert not select.select([receiver], [], [], 0.1)[0], "a held job printed before authorization"
    for host in (lan, "127.0.0.1"):
        assert_denied(host, 0x000D, job=job_id)  # Release-Job
    assert not select.select([receiver], [], [], 0.1)[0], "an unauthorized release reached the printer"

    run("lp", "-h", SOCKET, "-i", f"{QUEUE}-{job_id}", "-H", "resume")
    receiver.settimeout(10)
    connection, _ = receiver.accept()
    with connection, connection.makefile("rb") as printed:
        assert printed.read(len(document)) == document, "the printer did not receive the approved document"


def main():
    if os.geteuid() != 0 or not Path("/.dockerenv").exists():
        raise SystemExit("Run this fixture as root in an isolated Docker container.")
    assert not Path("/etc/ssl/private/ssl-cert-snakeoil.key").exists()
    assert not Path("/etc/ssl/certs/ssl-cert-snakeoil.pem").exists()
    assert (CUPS / "ssl").is_dir()
    assert not list(Path("/usr/lib/onemind/cups-default/ssl").iterdir())
    dropin = Path("/usr/lib/systemd/system/cups.service.d/10-onemind.conf").read_text()
    umask = int(re.search(r"(?m)^UMask=(\d+)$", dropin).group(1), 8)
    with subprocess.Popen(["/usr/sbin/cupsd", "-f"], umask=umask) as process:
        try:
            wait_for_cups(process)
            assert_device_tls()
            with socket.create_server(("127.0.0.1", 0)) as receiver:
                check_release(receiver)
        except Exception:
            for log in ("access_log", "error_log"):
                path = Path("/var/log/cups", log)
                if path.exists():
                    print(path.read_text()[-8000:])
            raise
        finally:
            process.terminate()
    print("PASS: device TLS, denied unattended IPP, and owner release")


if __name__ == "__main__":
    main()
