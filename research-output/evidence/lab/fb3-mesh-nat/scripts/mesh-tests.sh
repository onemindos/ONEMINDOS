#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# T1b reachability, T1c no inbound port, T4 ACL, T2 DERP fallback, E1 hard NAT.
set -uo pipefail; . "$(dirname "$0")/lib.sh"; S=$(cd "$(dirname "$0")" && pwd)
IPA=$(tsip home-a); IPB=$(tsip home-b); HUB=$(tsip cloud); L=$R/mesh; mkdir -p $L
banner(){ nsx "$1" timeout 8 ncat -w 5 --recv-only "$2" "$3" 2>/dev/null | head -1; }
probe(){ nsx "$1" python3 -I $S/tls-probe.py "$HUB" 7422 $R/ca/ca.crt 2>&1; }
lat(){ grep -oE 'in [0-9.]+ms' | grep -oE '[0-9.]+' | sort -n | awk '{a[NR]=$1} END{print (NR? a[int((NR+1)/2)] : "null")}'; }
# ---- T1b
AB=$(banner home-a $IPB 9001); BA=$(banner home-b $IPA 9001); PA=$(probe home-a); PB=$(probe home-b)
tsc home-a ping -c 30 --until-direct $IPB > $L/t1b-ping-until-direct.txt 2>&1
DIRECT=$(grep -cE 'via [0-9.]+:[0-9]+' $L/t1b-ping-until-direct.txt)
tsc home-a ping -c 20 $IPB > $L/t1b-ping20-direct.txt 2>&1; LAT_DIRECT=$(lat < $L/t1b-ping20-direct.txt)
log "T1b A->B:9001 '$AB' B->A:9001 '$BA' A->hub:7422 '$PA' B->hub:7422 '$PB' direct_pongs=$DIRECT median_direct_ms=$LAT_DIRECT"
[[ $AB == allowed-9001-home-b && $BA == allowed-9001-home-a && $PA == *"TLSv1.3"* && $PB == *"TLSv1.3"* && $DIRECT -ge 1 ]] && V=PASS || V=FAIL
res T1b $V "$(jq -n --arg ab "$AB" --arg ba "$BA" --arg pa "$PA" --arg pb "$PB" --argjson d $DIRECT --arg l "$LAT_DIRECT" '{a_to_b_9001:$ab,b_to_a_9001:$ba,a_hub_7422_tls:$pa,b_hub_7422_tls:$pb,direct_pongs:$d,median_direct_ms:$l}')"
# ---- T1c
for n in nat-a nat-b; do nsx $n nft list ruleset > $L/t1c-$n-ruleset.txt; done
FWD=$(cat $L/t1c-nat-*-ruleset.txt | grep -cE 'dnat|redirect|tproxy')
WANACC=$(cat $L/t1c-nat-*-ruleset.txt | grep -E 'iifname "wan"' | grep -v 'drop' | grep -c accept)
# capture both routers' WAN while the homes exchange traffic directly
for n in nat-a nat-b; do nsx $n timeout 15 tcpdump -nni wan -c 400 udp > $L/t1c-$n-wan-udp.txt 2>/dev/null & done
sleep 1; tsc home-a ping -c 10 $IPB >/dev/null 2>&1; banner home-a $IPB 9001 >/dev/null; wait
P2P=$(grep -cE "($NATA_WAN\.[0-9]+ > $NATB_WAN\.[0-9]+|$NATB_WAN\.[0-9]+ > $NATA_WAN\.[0-9]+)" $L/t1c-nat-a-wan-udp.txt)
for n in nat-a nat-b; do nsx $n conntrack -L -p udp > $L/t1c-$n-conntrack-udp.txt 2>/dev/null; done
# outside probes: from the cloud and from the other router's WAN address; watch the inside interface
SCANOK=1; for tgt in "nat-a $NATA_WAN home-a" "nat-b $NATB_WAN home-b"; do set -- $tgt
  for src in cloud $( [ $1 = nat-a ] && echo nat-b || echo nat-a ); do
    # only NEW inbound attempts: a bare SYN, UDP not belonging to tailscaled's own flows, or an echo request
    nsx $3 timeout 40 tcpdump -nni eth0 -c 50 "not src net $LANA.0/24 and not src net $LANB.0/24 and ((tcp[tcpflags] & (tcp-syn|tcp-ack) == tcp-syn) or (udp and not src port 41641 and not src port 3478) or icmp[icmptype] == icmp-echo)" > $L/t1c-$3-inside-during-scan-from-$src.txt 2>/dev/null &
    sleep 1
    nsx $src nmap -Pn -n -sS -p1-1024,41641 --max-retries 1 -T4 $2 > $L/t1c-scan-$1-from-$src-tcp.txt 2>&1
    nsx $src nmap -Pn -n -sU -p41641,3478 --max-retries 1 $2 > $L/t1c-scan-$1-from-$src-udp.txt 2>&1
    for p in 41641 3478 9001; do echo probe | nsx $src timeout 2 ncat -u -w1 $2 $p 2>/dev/null; done
    wait
    grep -qE '^[0-9]+/(tcp|udp) +open( |$)' $L/t1c-scan-$1-from-$src-tcp.txt $L/t1c-scan-$1-from-$src-udp.txt && SCANOK=0
    grep -qE "IP " $L/t1c-$3-inside-during-scan-from-$src.txt && SCANOK=0
  done; done
for n in nat-a nat-b; do nsx $n nft list counters > $L/t1c-$n-counters.txt; done
# every UDP flow's ORIGINAL direction must start inside the LAN
# every conntrack flow that involves the home node must have been ORIGINATED by the home node
OUTSIDE_ORIG=$(grep "$LANA.10" $L/t1c-nat-a-conntrack-udp.txt | awk '{for(i=1;i<=NF;i++) if($i ~ /^src=/){print $i; break}}' | grep -vc "src=$LANA.10"; true)
OUTSIDE_ORIG_B=$(grep "$LANB.10" $L/t1c-nat-b-conntrack-udp.txt | awk '{for(i=1;i<=NF;i++) if($i ~ /^src=/){print $i; break}}' | grep -vc "src=$LANB.10"; true)
HOMEFLOWS=$(( $(grep -c "$LANA.10" $L/t1c-nat-a-conntrack-udp.txt) + $(grep -c "$LANB.10" $L/t1c-nat-b-conntrack-udp.txt) ))
DROPS=$(grep -h -A1 -E 'wan_new_(in|fwd)' $L/t1c-nat-*-counters.txt | grep -oE 'packets [0-9]+' | tr '\n' ' ')
log "T1c forwards=$FWD wan_accepts=$WANACC p2p_udp_pkts_on_natA_wan=$P2P scans_clean=$SCANOK outside_originated_home_flows=A:$OUTSIDE_ORIG,B:$OUTSIDE_ORIG_B home_flows=$HOMEFLOWS drop_counters=[$DROPS]"
[[ $FWD -eq 0 && $WANACC -eq 0 && $P2P -gt 0 && $SCANOK -eq 1 && $OUTSIDE_ORIG -eq 0 && $OUTSIDE_ORIG_B -eq 0 && $HOMEFLOWS -gt 0 ]] && V=PASS || V=FAIL
res T1c $V "$(jq -n --argjson f $FWD --argjson w $WANACC --argjson p $P2P --argjson s $SCANOK --argjson oa $OUTSIDE_ORIG --argjson ob $OUTSIDE_ORIG_B --argjson hf $HOMEFLOWS --arg d "$DROPS" '{forward_rules:$f,wan_new_accepts:$w,direct_udp_packets_natA_wan:$p,outside_scans_no_answer:($s==1),home_udp_flows_checked:$hf,home_flows_originated_outside:{a:$oa,b:$ob},wan_new_drop_counters:$d}')"
# ---- T4 ACL
nsx home-b timeout 3 ncat -w2 --recv-only 127.0.0.1 9002 > $L/t4-b-local-9002.txt; nsx cloud timeout 3 ncat -w2 --recv-only 127.0.0.1 9002 > $L/t4-hub-local-9002.txt
OKA=0; DENB=0; DENH=0; : > $L/t4-attempts.txt
for i in 1 2 3; do
  a=$(banner home-a $IPB 9001); b=$(nsx home-a timeout 8 ncat -w 5 --recv-only $IPB 9002 2>&1 | head -1); h=$(nsx home-a timeout 8 ncat -w 5 --recv-only $HUB 9002 2>&1 | head -1)
  echo "attempt $i: B:9001='$a' B:9002='$b' hub:9002='$h'" >> $L/t4-attempts.txt
  [[ $a == allowed-9001-home-b ]] && OKA=$((OKA+1)); [[ $b != denied-* ]] && DENB=$((DENB+1)); [[ $h != denied-* ]] && DENH=$((DENH+1)); done
log "T4 $(tr '\n' ' ' < $L/t4-attempts.txt) | B local 9002='$(cat $L/t4-b-local-9002.txt)' hub local='$(cat $L/t4-hub-local-9002.txt)'"
[[ $OKA -eq 3 && $DENB -eq 3 && $DENH -eq 3 && $(cat $L/t4-b-local-9002.txt) == denied-9002-home-b && $(cat $L/t4-hub-local-9002.txt) == denied-9002-hub ]] && V=PASS || V=FAIL
res T4 $V "$(jq -n --argjson a $OKA --argjson b $DENB --argjson h $DENH '{allowed_b_9001_ok:$a,denied_b_9002_blocked:$b,denied_hub_9002_blocked:$h,attempts:3}')"
# ---- T2 DERP fallback: drop every UDP packet from home-a's LAN to the WAN
nsx nat-a nft add rule inet fw udpblock counter drop
nsx nat-a conntrack -D -p udp >/dev/null 2>&1
T2S=$(date +%s); DERPOK=0
for i in $(seq 1 30); do sleep 3; tsc home-a ping -c 1 --timeout 3s $IPB > $L/t2-probe.txt 2>&1; grep -q 'via DERP(onemind-hub)' $L/t2-probe.txt && { DERPOK=1; break; }; done
FALLBACK_S=$(( $(date +%s)-T2S ))
nsx nat-a timeout 15 tcpdump -nni wan -c 400 "host $NATA_WAN" > $L/t2-nat-a-wan.txt 2>/dev/null &
sleep 1; tsc home-a ping -c 20 $IPB > $L/t2-ping20-derp.txt 2>&1; AB2=$(banner home-a $IPB 9001); PA2=$(probe home-a); wait
LAT_DERP=$(lat < $L/t2-ping20-derp.txt); VIA=$(grep -c 'via DERP(onemind-hub)' $L/t2-ping20-derp.txt)
UDPOUT=$(grep -cE "IP $NATA_WAN\.[0-9]+ > .*UDP" $L/t2-nat-a-wan.txt); TCP443=$(grep -cE "IP $NATA_WAN\.[0-9]+ > $HUB_PUB\.443: " $L/t2-nat-a-wan.txt)
nsx nat-a nft list counter inet fw lan_udp_blocked >/dev/null 2>&1; BLK=$(nsx nat-a nft list chain inet fw udpblock | grep -oE 'packets [0-9]+')
log "T2 derp_after_s=$FALLBACK_S A->B:9001='$AB2' A->hub:7422='$PA2' via_derp_pongs=$VIA/20 median_derp_ms=$LAT_DERP udp_out_on_wan=$UDPOUT tcp443_out=$TCP443 blocked=$BLK"
[[ $DERPOK -eq 1 && $AB2 == allowed-9001-home-b && $PA2 == *TLSv1.3* && $VIA -ge 1 && $UDPOUT -eq 0 && $TCP443 -gt 0 ]] && V=PASS || V=FAIL
# unblock, time the return to direct (observation)
nsx nat-a nft flush chain inet fw udpblock; T2U=$(date +%s); BACK=null
for i in $(seq 1 90); do tsc home-a ping -c 1 --timeout 2s $IPB > $L/t2-back.txt 2>&1; grep -qE 'via [0-9.]+:[0-9]+' $L/t2-back.txt && { BACK=$(( $(date +%s)-T2U )); break; }; sleep 2; done
log "T2 back to direct after ${BACK}s"
res T2 $V "$(jq -n --argjson f $FALLBACK_S --arg ab "$AB2" --arg pa "$PA2" --argjson v $VIA --arg ld "$LAT_DIRECT" --arg lr "$LAT_DERP" --argjson u $UDPOUT --argjson t $TCP443 --arg blk "$BLK" --arg back "$BACK" '{derp_path_after_s:$f,a_to_b_9001:$ab,a_hub_7422_tls:$pa,via_derp_pongs_of_20:$v,median_ms:{direct:$ld,derp:$lr},udp_from_natA_wan:$u,tcp443_to_hub:$t,udp_block_counter:$blk,back_to_direct_after_s:$back}')"
# ---- E1 hard NAT on B (masquerade random = endpoint-dependent mapping); observation
nsx nat-b nft flush chain ip nat postrouting; nsx nat-b nft add rule ip nat postrouting oifname wan masquerade random
nsx nat-b conntrack -D -p udp >/dev/null 2>&1; nsx nat-a conntrack -D -p udp >/dev/null 2>&1; sleep 20
tsc home-a ping -c 40 --until-direct $IPB > $L/e1-ping.txt 2>&1
E1=$(grep -qE 'via [0-9.]+:[0-9]+' $L/e1-ping.txt && echo direct || (grep -q 'via DERP' $L/e1-ping.txt && echo derp || echo none))
E1B=$(banner home-a $IPB 9001)
nsx nat-b conntrack -L -p udp > $L/e1-nat-b-conntrack.txt 2>/dev/null
log "E1 hard-NAT-B path=$E1 A->B:9001='$E1B' last='$(tail -1 $L/e1-ping.txt)'"
res E1 OBSERVED "$(jq -n --arg p "$E1" --arg b "$E1B" --arg last "$(grep pong $L/e1-ping.txt | tail -1)" '{path:$p,a_to_b_9001:$b,last_pong:$last}')"
nsx nat-b nft flush chain ip nat postrouting; nsx nat-b nft add rule ip nat postrouting oifname wan masquerade
nsx nat-b conntrack -D -p udp >/dev/null 2>&1; nsx nat-a conntrack -D -p udp >/dev/null 2>&1
sleep 10; tsc home-a ping -c 30 --until-direct $IPB > $L/e1-restore.txt 2>&1; log "E1 restored: $(tail -1 $L/e1-restore.txt)"
