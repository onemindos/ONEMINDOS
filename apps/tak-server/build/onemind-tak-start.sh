#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Start TAK Server inside OneMind's image (apps/tak-server/build/Dockerfile).
#
# It does what upstream's docker/configureInDocker.sh does (start the config, messaging, API and
# retention processes from /opt/tak), plus the first-start steps upstream leaves to a person:
#   1. make the certificate authority, the server certificate and an admin client certificate with the
#      upstream scripts (makeRootCa.sh, makeCert.sh), protected by the box-generated TAK_CERT_PASSWORD
#      instead of the default "atakatak", and keep them on /data/certs;
#   2. write /data/config/CoreConfig.xml from the shipped example: the database on 127.0.0.1 with the
#      box-generated TAK_DB_PASSWORD, the new keystore password, federation HTTPS (8444) off;
#   3. bring the database schema up to date (SchemaManager.jar upgrade, every start: it is idempotent);
#   4. register the admin certificate once the server answers (UserManager.jar certmod -A).
# Any TAK process exiting makes the container exit, so Kubernetes restarts the pod.
set -euo pipefail

: "${TAK_DB_PASSWORD:?TAK_DB_PASSWORD is not set (spec.secrets tak-server-secrets)}"
: "${TAK_CERT_PASSWORD:?TAK_CERT_PASSWORD is not set (spec.secrets tak-server-secrets)}"
export STATE="${STATE:-NA}" CITY="${CITY:-NA}" ORGANIZATIONAL_UNIT="${ORGANIZATIONAL_UNIT:-OneMind}"

TAK=/opt/tak
umask 077
mkdir -p /data/config /data/logs

# Escape a value for an XML attribute, then for the right-hand side of a sed s|||.
xml_sed_escape() {
  printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/"/\&quot;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' \
    | sed -e 's/[\\|&]/\\&/g'
}

durable_move() {  # durable_move SRC DST: rename into place and flush, so a power cut leaves old or new
  sync "$1" 2>/dev/null || sync
  mv -T "$1" "$2"
  sync "$(dirname "$2")" 2>/dev/null || sync
}

# 1. Certificates, once.
if [ ! -f /data/certs/files/ca.pem ]; then
  echo "onemind: first start, making the certificate authority"
  rm -rf /data/certs.new
  cp -a "$TAK/certs.dist" /data/certs.new
  (
    cd /data/certs.new
    export CAPASS="$TAK_CERT_PASSWORD" PASS="$TAK_CERT_PASSWORD"
    ./makeRootCa.sh --ca-name "OneMind-TAK-CA-$(date -u +%Y%m%d%H%M)"
    ./makeCert.sh server takserver
    ./makeCert.sh client admin
  )
  rm -rf /data/certs
  durable_move /data/certs.new /data/certs
fi

# 2. CoreConfig.xml, once. Neither password can change afterwards: the keystores keep the first
#    CERT_PASSWORD, and the database keeps the first DB_PASSWORD (the postgres image applies
#    POSTGRES_PASSWORD only when it creates the data directory), so a rotated secret is not supported.
if [ ! -f /data/config/CoreConfig.xml ]; then
  cert_pass="$(xml_sed_escape "$TAK_CERT_PASSWORD")"
  db_pass="$(xml_sed_escape "$TAK_DB_PASSWORD")"
  sed -e 's|jdbc:postgresql://tak-database:5432/cot|jdbc:postgresql://127.0.0.1:5432/cot|' \
      -e "s|\(<connection url=\"jdbc:postgresql://127.0.0.1:5432/cot\" username=\"martiuser\" password=\"\)[^\"]*\"|\1${db_pass}\"|" \
      -e "s|keystorePass=\"atakatak\"|keystorePass=\"${cert_pass}\"|g" \
      -e "s|truststorePass=\"atakatak\"|truststorePass=\"${cert_pass}\"|g" \
      -e '/_name="fed_https"/d' \
      "$TAK/CoreConfig.example.xml" > /data/config/CoreConfig.xml.new
  durable_move /data/config/CoreConfig.xml.new /data/config/CoreConfig.xml
fi
# Refuse to start with a listener that is not the TLS-only default (checked on every start, so an edit
# to /data/config/CoreConfig.xml cannot silently open a plain-text or other transport).
/usr/local/bin/onemind-tak-check-config.sh /data/config/CoreConfig.xml
[ -f /data/config/UserAuthenticationFile.xml ] || : > /data/config/UserAuthenticationFile.xml

# 3. Database schema (the database sidecar is already accepting connections).
cd "$TAK"
java -jar db-utils/SchemaManager.jar upgrade

# 4. The TAK processes, as configureInDocker.sh starts them; heaps come from the pod (deployment.yaml).
pids=()
java -jar "-Xmx${CONFIG_MAX_HEAP:-512}m" -Dspring.profiles.active=config takserver.war & pids+=($!)
java -jar "-Xmx${MESSAGING_MAX_HEAP:-2048}m" -Dspring.profiles.active=messaging takserver.war & pids+=($!)
java -jar "-Xmx${API_MAX_HEAP:-2048}m" -Dspring.profiles.active=api -Dkeystore.pkcs12.legacy takserver.war & pids+=($!)
java -jar "-Xmx${RETENTION_MAX_HEAP:-256}m" takserver-retention.jar & pids+=($!)

# 5. Register the admin certificate once the API port answers (guide Appendix B; Docker form §6.2).
if [ ! -f /data/config/.admin-registered ]; then
  (
    for _ in $(seq 1 90); do
      if (exec 3<>/dev/tcp/127.0.0.1/8443) 2>/dev/null; then
        if java -jar utils/UserManager.jar certmod -A certs/files/admin.pem; then
          : > /data/config/.admin-registered
          echo "onemind: admin certificate registered"
        fi
        exit 0
      fi
      sleep 10
    done
    echo "onemind: API did not answer; admin certificate not registered" >&2
  ) &
fi

# Only the TAK processes count: the registration helper finishing must not stop the pod.
wait -n "${pids[@]}"
echo "onemind: a TAK Server process exited; stopping the pod so it restarts" >&2
exit 1
