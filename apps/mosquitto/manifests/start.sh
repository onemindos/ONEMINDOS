#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Starts Mosquitto with the ConfigMap's mosquitto.conf, plus an optional bridge to the OneMind NATS
# server's MQTT listener (issue #199, FLD-02). Mosquitto's config file cannot read environment
# variables, so this script writes the runtime config from the app's settings and secret first.
#
# Why a bridge: NATS accepts only MQTT 3.1.1 clients (server/mqtt.go at v2.15.2 refuses any other
# protocol level). Mosquitto accepts MQTT 5, 3.1.1 and 3.1, and its built-in bridge speaks 3.1.1 to
# NATS, so MQTT 5 devices reach the NATS bus through Mosquitto.
#
# Inputs (all optional; with NATS_MQTT_HOST empty the bridge is off and Mosquitto runs as before):
#   NATS_MQTT_HOST      NATS MQTT listener host name (setting nats_mqtt_host)
#   NATS_MQTT_PORT      its port, default 1883 (setting nats_mqtt_port)
#   NATS_MQTT_USERNAME  NATS user for the bridge (setting nats_mqtt_username)
#   NATS_MQTT_PASSWORD  its password (Secret mosquitto-nats-bridge, entered by the owner)
#   NATS_BRIDGE_DOWN    "true" also carries NATS -> devices (setting nats_bridge_down, default false)
#   MOSQUITTO_RUN_DIR   where the runtime config is written, default /mosquitto/run (an emptyDir)
set -eu

base=${MOSQUITTO_BASE_CONF:-/mosquitto/config/mosquitto.conf}
run=${MOSQUITTO_RUN_DIR:-/mosquitto/run}
conf="$run/mosquitto.conf"
host=${NATS_MQTT_HOST:-}
port=${NATS_MQTT_PORT:-1883}
user=${NATS_MQTT_USERNAME:-}
pass=${NATS_MQTT_PASSWORD:-}
down=${NATS_BRIDGE_DOWN:-false}

fail() { echo "start.sh: $*" >&2; exit 64; }

# Every value goes into a config line, so a value with a space or a line break could add its own
# config lines. Refuse those instead of quoting (Mosquitto's config format has no escaping).
case "$host" in *[!A-Za-z0-9.-]*) fail "nats_mqtt_host may hold only letters, digits, '.' and '-'";; esac
case "$port" in ''|*[!0-9]*) fail "nats_mqtt_port must be a number";; esac
if [ "$port" -lt 1 ] || [ "$port" -gt 65535 ]; then fail "nats_mqtt_port must be 1-65535"; fi
nl='
'
tab=$(printf '\t')
cr=$(printf '\r')
has_space() { case "$1" in *" "*|*"$tab"*|*"$nl"*|*"$cr"*) return 0;; esac; return 1; }
if has_space "$user"; then fail "nats_mqtt_username must not contain spaces or line breaks"; fi
if has_space "$pass"; then fail "the bridge password must not contain spaces or line breaks"; fi
case "$down" in true|false) ;; *) fail "nats_bridge_down must be true or false";; esac
if [ -n "$pass" ] && [ -z "$user" ]; then fail "a bridge password needs nats_mqtt_username"; fi

umask 077   # the runtime config can hold the bridge password
mkdir -p "$run"
cp "$base" "$conf"

if [ -n "$host" ]; then
	{
		echo
		echo "# --- bridge to NATS, written by start.sh ---"
		echo "connection onemind-nats"
		echo "address $host:$port"
		# NATS accepts protocol level 4 (3.1.1) only. try_private would send level 0x84 (Mosquitto's
		# "I am a bridge" flag), which NATS refuses, so it is off.
		echo "bridge_protocol_version mqttv311"
		echo "try_private false"
		echo "remote_clientid onemind-mosquitto-bridge"
		# No $SYS/broker/connection/... state messages to NATS: they are Mosquitto-internal.
		echo "notifications false"
		if [ -n "$user" ]; then echo "remote_username $user"; fi
		if [ -n "$pass" ]; then echo "remote_password $pass"; fi
		# Devices -> NATS: every local topic T is published on NATS as mqtt/up/T (NATS subject
		# mqtt.up.T). The bridge's local subscription is "no local" (src/bridge.c at v2.1.2), so a
		# message that came in over the bridge never goes back out.
		echo 'topic # out 1 "" mqtt/up/'
		# NATS -> devices: mqtt/down/T on NATS (subject mqtt.down.T) arrives locally as T. A
		# separate prefix means the bridge never subscribes to its own output, so nothing loops or
		# arrives twice. Off unless the owner turns it on.
		if [ "$down" = true ]; then echo 'topic # in 1 "" mqtt/down/'; fi
	} >> "$conf"
	echo "start.sh: bridge to NATS at $host:$port on (down direction: $down)"
else
	echo "start.sh: bridge to NATS off (nats_mqtt_host is empty)"
fi

exec mosquitto -c "$conf"
