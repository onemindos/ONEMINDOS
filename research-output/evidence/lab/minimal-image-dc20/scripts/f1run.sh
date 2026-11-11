cd /var/lab/dc20
bash boot-test.sh legA-debian out/legA/disk.img out/legA/kernel.config 6.12.116+deb13-amd64
bash boot-test.sh legB-buildroot out/legB/disk.img out/legB/kernel.config 6.12.112
echo F1-ALL-DONE
