#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Printing proof, run inside the guest by firstboot.py (FP1-FP3, sections 20 and 26).
# Root sets up the test queue and the gateway checks the owner's passkey. The harness judges KEY=value lines.
#   print-proof.sh baseline   first boot: packages, services, defaults, a non-owner is refused, add a queue, print
#   print-proof.sh again      after a reboot or an A/B update: the queue and the defaults are still there, print again
mode=${1:-baseline}
cd / || exit 1
PPD=/run/onemind-print-test.ppd
OUT=/run/cups/onemind-print-test.prn
Q=OneMindTest

# cupsctl refuses to set FileDevice, so the line in cups-files.conf is edited and cupsd restarted.
file_device() {
  sed -i '/^FileDevice/d' /etc/cups/cups-files.conf
  echo "FileDevice $1" >> /etc/cups/cups-files.conf
  systemctl restart cups.service
  for _ in $(seq 1 30); do lpstat -r 2>/dev/null | grep -q 'is running' && break; sleep 1; done
}
DESC="OneMind QEMU proof queue"

echo "PKGS=$(for p in cups cups-daemon cups-client cups-filters cups-ipp-utils ipp-usb; do
  dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q 'install ok installed' || printf 'missing-%s,' "$p"; done)ok"
echo "BROWSED=$(dpkg-query -W -f='${Status}' cups-browsed 2>/dev/null | grep -q 'install ok installed' && echo present || echo absent)"
echo "BINS=$(for f in /usr/sbin/cupsd /usr/sbin/ipp-usb /usr/lib/cups/filter/pdftopdf /usr/lib/cups/backend/driverless /usr/lib/cups/cgi-bin/admin.cgi /usr/bin/ipptool; do
  [ -x "$f" ] || printf 'missing-%s,' "$f"; done)ok"
echo "ACTIVE=$(systemctl is-active cups.service)"
echo "LISTEN=$(ss -H -ltn | awk '$4 ~ /:631$/ {print $4}' | tr '\n' ,)"
for m in etc/cups var/spool/cups var/cache/cups var/lib/ipp-usb; do
  echo "MNT_$(echo "$m" | tr '/-' '__')=$(findmnt -n -o SOURCE "/$m" | head -1)"
done
# where /data starts: "/" on ext4, "/@" on the btrfs layout (#152); the binds' roots are "<that>/state/..."
echo "DROOT=$(findmnt -n -o FSROOT /data | head -1)"
echo "CTL=$(cupsctl | grep -E '^_(remote_admin|remote_any|share_printers|user_cancel_any)=' | sort | tr '\n' ' ')"
echo "HTTP_ROOT=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:631/)"
echo "HTTP_ADMIN=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:631/admin)"
echo "FILEDEV_BEFORE=$(grep -c '^FileDevice[[:space:]]*[Yy]' /etc/cups/cups-files.conf)"

if [ "$mode" = baseline ]; then
  runuser -u nobody -- lpadmin -p NotOwner -E -v file:/dev/null -m raw >/dev/null 2>&1
  echo "NONOWNER_RC=$?"
  lpstat -p NotOwner >/dev/null 2>&1 && echo "NONOWNER_QUEUE=present" || echo "NONOWNER_QUEUE=absent"
  cat > "$PPD" <<'PPDEOF'
*PPD-Adobe: "4.3"
*FormatVersion: "4.3"
*FileVersion: "1.0"
*LanguageVersion: English
*LanguageEncoding: ISOLatin1
*PCFileName: "onemind.ppd"
*Manufacturer: "OneMind"
*Product: "(OneMind PDF test queue)"
*ModelName: "OneMind PDF test queue"
*ShortNickName: "OneMind PDF test queue"
*NickName: "OneMind PDF test queue"
*PSVersion: "(3010.000) 0"
*LanguageLevel: "3"
*ColorDevice: False
*DefaultColorSpace: Gray
*FileSystem: False
*Throughput: "1"
*LandscapeOrientation: Plus90
*TTRasterizer: Type42
*cupsVersion: 2.4
*cupsSNMPSupplies: False
*cupsFilter2: "application/vnd.cups-pdf application/pdf 0 -"
*OpenUI *PageSize: PickOne
*DefaultPageSize: Letter
*PageSize Letter/Letter: "<</PageSize[612 792]>>setpagedevice"
*PageSize A4/A4: "<</PageSize[595 842]>>setpagedevice"
*CloseUI: *PageSize
*OpenUI *PageRegion: PickOne
*DefaultPageRegion: Letter
*PageRegion Letter/Letter: "<</PageSize[612 792]>>setpagedevice"
*PageRegion A4/A4: "<</PageSize[595 842]>>setpagedevice"
*CloseUI: *PageRegion
*DefaultImageableArea: Letter
*ImageableArea Letter/Letter: "18 18 594 774"
*ImageableArea A4/A4: "18 18 577 824"
*DefaultPaperDimension: Letter
*PaperDimension Letter/Letter: "612 792"
*PaperDimension A4/A4: "595 842"
PPDEOF
  file_device yes
  lpadmin -p "$Q" -E -v "file:$OUT" -P "$PPD" -D "$DESC"
  echo "ADD_RC=$?"
else
  file_device yes
  echo "QUEUE=$(lpstat -p "$Q" 2>&1 | head -1)"
  echo "DESC=$(lpstat -l -p "$Q" 2>/dev/null | sed -n 's/^[[:space:]]*Description: //p')"
fi

# A "file:" device is refused unless FileDevice Yes: on only for the add and the print, then off again.
rm -f "$OUT"
lp -h /run/cups/cups.sock -d "$Q" -t onemind-testpage /usr/share/cups/data/default-testpage.pdf </dev/null
echo "DIRECT_SUBMIT_RC=$?"
receipt=$(/usr/bin/onemind-print-hold "$Q" onemind-testpage </usr/share/cups/data/default-testpage.pdf)
job=$(printf '%s\n' "$receipt" | head -1)
title=$(printf '%s\n' "$receipt" | tail -1)
lp -h /run/cups/cups.sock -i "$job" -H resume </dev/null
echo "DIRECT_RELEASE_RC=$?"
runuser -u onemind -- /usr/lib/onemind/gateway/venv/bin/python3 -I /run/print-approve.py /run/print-authenticator.py "$job" "$title" "$OUT"
echo "LP_RC=$?"
for _ in $(seq 1 90); do
  [ -s "$OUT" ] && [ -z "$(lpstat -o "$Q" 2>/dev/null)" ] && break
  sleep 1
done
echo "OUT_HEAD=$(head -c 4 "$OUT" 2>/dev/null)"
echo "OUT_SIZE=$(stat -c %s "$OUT" 2>/dev/null || echo 0)"
rm -f "$OUT"
file_device no
echo "FILEDEV_AFTER=$(grep -c '^FileDevice[[:space:]]*[Yy]' /etc/cups/cups-files.conf)"
echo "PRINT-PROOF-DONE"
