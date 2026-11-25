export DEBIAN_FRONTEND=noninteractive HOME=/root
apt-get update -qq
apt-get install -y -qq chromium chromium-driver python3-selenium python3-cryptography openssl libnss3-tools tcpdump iproute2 curl > /root/prov.log 2>&1
echo PROV-DONE >> /root/prov.log
