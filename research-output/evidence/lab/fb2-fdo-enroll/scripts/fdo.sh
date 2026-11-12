#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# LAB-fb2-fdo-enroll T1-T5 and E1-E6. Services on loopback inside the VM; keys made at run time, never kept.
set -uo pipefail; S=$(cd "$(dirname "$0")" && pwd); . $S/lib.sh
RUN=${1:?run id}; R=$OUT/fdo-run-$RUN; RS=$R/res; rm -rf $R; mkdir -p $RS
W=/opt/fb/fdo; pkill -f go-fdo- 2>/dev/null; sleep 1; rm -rf $W; mkdir -p $W/{keys,db,dl,dev,dev2}; K=$W/keys
exec > >(tee $R/run.log) 2>&1
log "== fdo run $RUN"
gen(){ openssl ecparam -name prime256v1 -genkey -out $K/$1_key.der -outform der 2>/dev/null; openssl req -x509 -key $K/$1_key.der -keyform der -out $K/$1_cert.pem -days 30 -subj "/O=Lab/CN=$1" 2>/dev/null; }
for k in manufacturer device_ca owner owner2; do gen $k; done
echo "onemind-join:v1?code=$(openssl rand -hex 6)&ca=$(openssl rand -hex 32)&role=worker" > $W/dl/join-bundle.txt
BUNDLE_SHA=$(sha256sum $W/dl/join-bundle.txt | cut -c1-64)
owner_cfg(){ cat > $W/$1.yaml <<Y
log: {level: debug}
db: {type: sqlite, dsn: "file:$W/db/$1.db"}
http: {ip: 127.0.0.1, port: "$2"}
device_ca: {cert: $K/device_ca_cert.pem}
owner:
  key: $K/$3_key.der
  service_info:
    fsims:
      - fsim: fdo.download
        params:
          dir: $W/dl
          files:
            - {src: join-bundle.txt, dst: $W/dev/join-bundle.txt}
      - fsim: fdo.command
        params:
          cmd: sh
          args: ["-c", "id -u > $W/dev/marker-uid; echo onboarded > $W/dev/marker"]
          return_stdout: true
Y
}
owner_cfg own 8043 owner; owner_cfg own2 8044 owner2
go-fdo-server --log-level=debug rendezvous 127.0.0.1:8041 --db-type sqlite --db-dsn "file:$W/db/rv.db" > $R/rv.log 2>&1 &
go-fdo-server --log-level=debug manufacturing 127.0.0.1:8038 --db-type sqlite --db-dsn "file:$W/db/mfg.db" \
  --manufacturing-key $K/manufacturer_key.der --device-ca-cert $K/device_ca_cert.pem --device-ca-key $K/device_ca_key.der \
  --owner-cert $K/owner_cert.pem > $R/mfg.log 2>&1 &
go-fdo-server owner --config $W/own.yaml > $R/owner.log 2>&1 &
go-fdo-server owner --config $W/own2.yaml > $R/owner2.log 2>&1 &
H=""; for i in $(seq 60); do H=$(for p in 8041 8038 8043 8044; do curl -fsS -o /dev/null -w '%{http_code} ' http://127.0.0.1:$p/health; done); [ "$H" = "200 200 200 200 " ] && break; sleep 2; done
log "health: $H"
curl -fsS -X POST http://127.0.0.1:8038/api/v1/rvinfo -H 'Content-Type: text/plain' \
  --data-raw '[{"dns":"localhost","ip":"127.0.0.1","device_port":"8041","owner_port":"8041","protocol":"http","delay_seconds":10}]' -o /dev/null -w 'rvinfo %{http_code}\n'
# The rendezvous accepts TO0 only for devices whose certificate chains to a trusted device CA (api/device-ca.yaml)
curl -sS -X POST http://127.0.0.1:8041/api/v1/device-ca -H 'Content-Type: application/x-pem-file' --data-binary @$K/device_ca_cert.pem -o $R/rv-device-ca-import.json -w 'rv device-ca %{http_code}\n'
for p in 8043 8044; do curl -fsS -X POST http://127.0.0.1:$p/api/v1/owner/redirect -H 'Content-Type: text/plain' \
  --data-raw "[{\"dns\":\"localhost\",\"port\":\"$p\",\"protocol\":\"http\",\"ip\":\"127.0.0.1\"}]" -o /dev/null -w "redirect $p %{http_code}\n"; done
# ---- T1 DI
cd $W/dev
go-fdo-client device-init http://127.0.0.1:8038 --device-info fb2-lab-device --serial-number LAB-0001 --key ec256 --blob $W/dev/cred.bin > $R/di.log 2>&1; DI_RC=$?
go-fdo-client print --blob $W/dev/cred.bin > $R/cred-before.txt 2>&1
GUID=$(grep -oE '[0-9a-fA-F]{32}' $R/cred-before.txt | head -1)
VC=$(curl -sS -o $W/ov.pem -w '%{http_code}' http://127.0.0.1:8038/api/v1/vouchers/$GUID); VSZ=$(stat -c %s $W/ov.pem 2>/dev/null || echo 0)
[[ "$H" = "200 200 200 200 " && $DI_RC -eq 0 && -n "$GUID" && $VC = 200 && $VSZ -gt 100 ]] && V=PASS || V=FAIL
res $RS T1 $V "$(jq -n --arg h "$H" --argjson rc $DI_RC --arg g "$GUID" --arg vc $VC --argjson vs $VSZ '{health:$h,di_rc:$rc,guid:$g,voucher_http:$vc,voucher_bytes:$vs}')"
# ---- T2 no approval -> no onboarding (same process continues into T3)
go-fdo-client onboard --key ec256 --kex ECDH256 --blob $W/dev/cred.bin --default-working-dir $W/dev > $R/onboard-t2t3.log 2>&1 &
OBPID=$!; T2START=$(date +%s); sleep 120
C2=$(grep -c 'FIDO Device Onboard Complete' $R/onboard-t2t3.log); F2=$([ -f $W/dev/join-bundle.txt ] && echo yes || echo no)
TO1F=$(grep -c 'TO1 failed' $R/onboard-t2t3.log); ALIVE=$(kill -0 $OBPID 2>/dev/null && echo yes || echo no)
[[ $C2 -eq 0 && $F2 = no ]] && V=PASS || V=FAIL
res $RS T2 $V "$(jq -n --argjson c $C2 --arg f $F2 --argjson t $TO1F --arg a $ALIVE '{complete_lines:$c,bundle_file:$f,to1_failures_in_120s:$t,process_alive:$a}')"
# ---- T3 approval card, then import; the same process must finish
{ echo "APPROVAL CARD (stand-in for the phone): node.join via FDO"; echo " device GUID: $GUID"; echo " device info: fb2-lab-device  serial: LAB-0001";
  echo " manufacturer cert sha256: $(openssl x509 -in $K/manufacturer_cert.pem -outform der | sha256sum | cut -c1-16)…"; echo " decision: APPROVED by owner (stand-in)"; } | tee $R/approval-card.txt
APPROVED_AT=$(date +%s)
IC=$(curl -sS -o $R/import-owner.txt -w '%{http_code}' -X POST http://127.0.0.1:8043/api/v1/owner/vouchers --data-binary @$W/ov.pem)
DONE=no; for i in $(seq 150); do grep -q 'FIDO Device Onboard Complete' $R/onboard-t2t3.log && { DONE=yes; break; }; sleep 2; done
T3SEC=$(( $(date +%s) - APPROVED_AT )); sleep 2
GOT_SHA=$(sha256sum $W/dev/join-bundle.txt 2>/dev/null | cut -c1-64); MARK=$(cat $W/dev/marker 2>/dev/null); MUID=$(cat $W/dev/marker-uid 2>/dev/null)
SAMEPID=$(kill -0 $OBPID 2>/dev/null && echo running || echo exited)
[[ $IC =~ ^2 && $DONE = yes && "$GOT_SHA" = "$BUNDLE_SHA" && "$MARK" = onboarded ]] && V=PASS || V=FAIL
res $RS T3 $V "$(jq -n --arg ic $IC --arg d $DONE --argjson s $T3SEC --arg w $BUNDLE_SHA --arg g "$GOT_SHA" --arg m "$MARK" --arg u "$MUID" --arg p $SAMEPID --argjson pid $OBPID '{owner_import_http:$ic,completed:$d,seconds_after_approval:$s,bundle_sha256_owner:$w,bundle_sha256_device:$g,command_marker:$m,command_ran_as_uid:$u,onboard_process_after:$p,onboard_pid:$pid,restarted:false}')"
kill $OBPID 2>/dev/null
go-fdo-client print --blob $W/dev/cred.bin > $R/cred-after.txt 2>&1
GUID2=$(grep -oE '[0-9a-fA-F]{32}' $R/cred-after.txt | head -1)
res $RS E3 OBS "$(jq -n --arg a "$GUID" --arg b "$GUID2" '{guid_before_to2:$a,guid_after_to2:$b,changed:($a!=$b)}')"
res $RS E4 OBS "$(jq -n --arg u "$MUID" '{fdo_command_executed_on_device_as_uid:$u,note:"owner-supplied shell ran on the device during TO2"}')"
# ---- T4 wrong owner
IC2=$(curl -sS -o $R/import-owner2.txt -w '%{http_code}' -X POST http://127.0.0.1:8044/api/v1/owner/vouchers --data-binary @$W/ov.pem)
[[ ! $IC2 =~ ^2 ]] && V=PASS || V=FAIL
res $RS T4 $V "$(jq -n --arg c $IC2 --arg b "$(head -c 200 $R/import-owner2.txt)" '{owner2_import_http:$c,body:$b}')"
# ---- E5 control: can the device re-onboard before revocation? then T5 revoke and retry
curl -sS http://127.0.0.1:8043/api/v1/owner/devices > $R/owner-devices-before-revoke.json
sqlite3 $W/db/own.db .schema > $R/owner-db-schema.sql
ctl(){ timeout 120 go-fdo-client onboard --key ec256 --kex ECDH256 --blob $W/dev/cred.bin --default-working-dir $W/dev > $R/$1.log 2>&1; grep -c 'FIDO Device Onboard Complete' $R/$1.log; }
CTRL=$(ctl onboard-control-before-revoke)
res $RS E5 OBS "$(jq -n --argjson c $CTRL '{reonboard_completed_before_revoke:($c>0),note:"control for T5"}')"
TABLES=$(sqlite3 $W/db/own.db "select name from sqlite_master where type='table'" | grep -i -E 'voucher|replacement|to0|session' | tr '\n' ' ')
for t in $TABLES; do echo "rows in $t before: $(sqlite3 $W/db/own.db "select count(*) from $t")"; sqlite3 $W/db/own.db "delete from $t"; done | tee $R/revoke.txt
REV=$(ctl onboard-after-revoke)
[[ $REV -eq 0 ]] && V=PASS || V=FAIL
res $RS T5 $V "$(jq -n --argjson c $REV --arg t "$TABLES" --argjson ctl $CTRL '{reonboard_completed_after_revoke:($c>0),tables_cleared:$t,no_delete_api_in_v1_0_2:true,control_before_revoke_completed:($ctl>0)}')"
# ---- E6 a second device: approved, then revoked before its first power-on
cd $W/dev2; go-fdo-client device-init http://127.0.0.1:8038 --device-info fb2-lab-device-2 --serial-number LAB-0002 --key ec256 --blob $W/dev2/cred.bin > $R/di2.log 2>&1
G3=$(go-fdo-client print --blob $W/dev2/cred.bin 2>/dev/null | grep -oE '[0-9a-fA-F]{32}' | head -1)
curl -sS -o $W/ov2.pem http://127.0.0.1:8038/api/v1/vouchers/$G3; IC3=$(curl -sS -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8043/api/v1/owner/vouchers --data-binary @$W/ov2.pem)
sleep 15; for t in $TABLES; do sqlite3 $W/db/own.db "delete from $t"; done
timeout 120 go-fdo-client onboard --key ec256 --kex ECDH256 --blob $W/dev2/cred.bin --default-working-dir $W/dev2 > $R/onboard-dev2-revoked.log 2>&1
E6C=$(grep -c 'FIDO Device Onboard Complete' $R/onboard-dev2-revoked.log); E6TO1=$(grep -c 'TO1 succeeded' $R/onboard-dev2-revoked.log)
res $RS E6 OBS "$(jq -n --arg ic $IC3 --argjson c $E6C --argjson t $E6TO1 '{import_http:$ic,completed_after_revoke:($c>0),to1_succeeded_lines:$t}')"
# ---- E1 reflash: credential blob gone
mv $W/dev/cred.bin $W/dev/cred.bin.gone
timeout 30 go-fdo-client onboard --key ec256 --kex ECDH256 --blob $W/dev/cred.bin --default-working-dir $W/dev > $R/onboard-wiped.log 2>&1; E1RC=$?
res $RS E1 OBS "$(jq -n --argjson rc $E1RC --arg e "$(tail -3 $R/onboard-wiped.log | tr '\n' ' ' | cut -c1-300)" '{rc:$rc,tail:$e}')"
# ---- E2 software TPM (swtpm CUSE is not used: linuxtpm.Open needs a character device; try the tpm-vtpm-proxy-free route)
if [ -e /dev/tpmrm0 ]; then E2="vm has /dev/tpmrm0"; else E2="no TPM character device in the VM; swtpm socket mode cannot be opened by linuxtpm.Open (client rejects 'simulator'), so E2 not run"; fi
res $RS E2 OBS "$(jq -n --arg n "$E2" '{note:$n}')"
pkill -f go-fdo-server; log "== fdo run $RUN end"
cp $W/*.yaml $R/ 2>/dev/null; sed -i "s#$W#<fdo-work>#g" $R/*.yaml $R/*.log $R/*.txt 2>/dev/null
jq -s '{spike:"fb2-fdo-enroll",run:"'$RUN'",verdict:(if ([.[]|select(.id|test("^T"))|.verdict]|all(.=="PASS")) then "PASS" else "FAIL" end),results:.}' $RS/*.json > $R/results.json
jq -r '.verdict, (.results[]|"\(.id) \(.verdict)")' $R/results.json
