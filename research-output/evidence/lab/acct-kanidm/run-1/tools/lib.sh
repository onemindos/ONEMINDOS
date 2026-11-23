#!/bin/bash
# Shared helpers for the AK-n scripts. Source it with T=<test id> set.
# run "<command>": prints "+ <command>" exactly as written (secrets are read from files inside the
# command, so their values never appear), then the command's real output, into run-1/<T>.txt.
R=/root/aklab; RUN=$R/run-1; SEC=$R/secrets
mkdir -p "$RUN"; install -d -m 700 "$SEC"
export AK_SECRETS=$SEC AK_CA=/etc/kanidm/ca.pem HOME=/root
PY="python3 -I $R/aklab.py"
note(){ echo "# $*" | tee -a "$RUN/$T.txt"; }
run(){ echo "+ $1" | tee -a "$RUN/$T.txt"; local rc; set +e; ( eval "$1" ) 2>&1 | tee -a "$RUN/$T.txt"; rc=${PIPESTATUS[0]}; set -e; echo "  (exit $rc)" | tee -a "$RUN/$T.txt"; return 0; }
stamp(){ note "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }
kpid(){ systemctl show -p MainPID --value kanidmd; }
rss(){ local p; p=$(kpid); grep -E '^(VmRSS|VmHWM)' /proc/$p/status | tr -s ' ' | tr '\n' ' '; echo; }
# idm_admin CLI session: the password is read from the secrets file into the environment only.
admin_login(){ KANIDM_PASSWORD="$(cat $SEC/idm_admin.password)" kanidm login -D idm_admin >/dev/null 2>&1 && echo "idm_admin login ok" || echo "idm_admin login FAILED"; }
admin_relogin(){ KANIDM_PASSWORD="$(cat $SEC/idm_admin.password)" kanidm reauth -D idm_admin >/dev/null 2>&1 || admin_login; }
k(){ kanidm "$@" -D idm_admin; }
# Reset token: issued by the admin, kept in the secrets dir, only its expiry line is shown.
reset_token(){ # reset_token <person> <secret-name> [ttl]
  local o tok; o=$(kanidm person credential create-reset-token "$1" ${3:+--ttl $3} -D idm_admin 2>&1)
  tok=$(printf '%s\n' "$o" | sed -n 's/.*use-reset-token \([^ ]*\).*/\1/p' | head -1)
  if [ -n "$tok" ]; then printf '%s' "$tok" > "$SEC/$2"; chmod 600 "$SEC/$2"
    echo "reset link issued for $1 (link and token kept in the secrets dir, not printed)"; printf '%s\n' "$o" | grep -i 'expire at'
  else echo "no reset token parsed; CLI output first line: $(printf '%s\n' "$o" | head -1 | cut -c1-60)"; fi
}
# maxrss <cmd...>: run a command, print its exit code, wall time and peak RSS (getrusage of the child).
maxrss(){ python3 -I -c "import resource,subprocess,sys,time; t=time.time(); r=subprocess.run(sys.argv[1:]); u=resource.getrusage(resource.RUSAGE_CHILDREN); print('exit', r.returncode, 'elapsed_s', round(time.time()-t, 2), 'max_rss_kB', u.ru_maxrss)" "$@"; }
