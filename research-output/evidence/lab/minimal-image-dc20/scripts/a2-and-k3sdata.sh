set -e
mkdir -p /var/lab/dc20/legA2 && cp /tmp/legA2-mkosi.conf /var/lab/dc20/legA2/mkosi.conf && cp -r /var/lab/dc20/legA/mkosi.extra /var/lab/dc20/legA2/
cd /var/lab/dc20/legA2; s=$(date +%s); mkosi --cache-dir=/var/lab/dc20/cache-a -f build > /var/lab/dc20/logs/build-a2.log 2>&1; echo "A2 build (cached) $(( $(date +%s)-s ))s"
mkdir -p /var/lab/dc20/out/legA2 && cp onemind-deb.raw /var/lab/dc20/out/legA2/disk.img
cd /var/lab/dc20; bash measure.sh legA2-debian-apparmor out/legA2/disk.img | tail -8
bash boot-test.sh legA2-debian-apparmor out/legA2/disk.img out/legA/kernel.config 6.12.116+deb13-amd64 2>&1 | grep -a "DC20-F1\|STATUS\|apparmor\|wall"
# k3s first-start payload (identical binary in both legs): scan what k3s unpacked
L=$(losetup -P -f --show f1/legB-buildroot/disk.img); mkdir -p /mnt/k3sdata; mount -o ro ${L}p2 /mnt/k3sdata
D=$(ls -d /mnt/k3sdata/var/lib/rancher/k3s/data/*/ | grep -v current | head -1); du -sb $D
mkdir -p out/measure/k3s-unpacked
GRYPE_DB_AUTO_UPDATE=false /opt/syft/syft scan dir:$D -q -o syft-json=out/measure/k3s-unpacked/syft.json
GRYPE_DB_AUTO_UPDATE=false /opt/grype/grype sbom:out/measure/k3s-unpacked/syft.json -q -o json > out/measure/k3s-unpacked/grype.json
GRYPE_DB_AUTO_UPDATE=false /opt/grype/grype sbom:out/measure/k3s-unpacked/syft.json -q --only-fixed -o json > out/measure/k3s-unpacked/grype-onlyfixed.json
ls $D/bin | tr '\n' ' '; echo
umount /mnt/k3sdata; losetup -d $L
python3 -I summarize.py out/measure/legA2-debian-apparmor out/measure/k3s-unpacked | grep -v "top packages"
python3 -I split.py out/measure/legA2-debian-apparmor | grep -E "nok3s|deb binary"
