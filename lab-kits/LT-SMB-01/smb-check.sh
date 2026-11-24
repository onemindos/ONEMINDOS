#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# LT-SMB-01 (FILES-SHARE-01, #235): the part of the file-sharing check a script can do, from any Linux machine
# (or Lima VM) on the same network as the box. The Mac and Windows part is in README.md.
#
#   BOX=192.0.2.10 USER_A=alex PASS_A=... USER_B=bo PASS_B=... sh lab-kits/LT-SMB-01/smb-check.sh
#
# Needs smbclient (Debian: apt install smbclient). Prints PASS or FAIL per check; exit status 1 if any failed.
# The passwords come from the environment, never from arguments, so they stay out of the process list.
set -u
: "${BOX:?set BOX to the address of the box, a name or an IP}"
: "${USER_A:?}" "${PASS_A:?}" "${USER_B:?}" "${PASS_B:?}"
fail=0
ok() { printf 'PASS  %s\n' "$1"; }
bad() { printf 'FAIL  %s\n' "$1"; fail=1; }

# smbclient reads the password from $PASSWD, not from an argument.
as() { # as USER PASS args...
  u=$1; p=$2; shift 2
  PASSWD=$p smbclient "$@" -U "$u" 2>&1
}

# 1. the person sees their own share
out=$(as "$USER_A" "$PASS_A" -L "//$BOX" -m SMB3)
case $out in *"$USER_A"*) ok "$USER_A sees the $USER_A share" ;; *) bad "$USER_A does not see their share: $out" ;; esac

# 2. the person opens it and can write and read back
f="smb-check-$$.txt"
echo "hello" > "/tmp/$f"
out=$(as "$USER_A" "$PASS_A" "//$BOX/$USER_A" -m SMB3 -c "put /tmp/$f $f; ls $f; del $f")
case $out in *"putting file"*) ok "$USER_A writes into their own share" ;; *) bad "write failed: $out" ;; esac
rm -f "/tmp/$f"

# 3. another person cannot open it
out=$(as "$USER_B" "$PASS_B" "//$BOX/$USER_A" -m SMB3 -c "ls")
case $out in *NT_STATUS_ACCESS_DENIED*|*NT_STATUS_LOGON_FAILURE*|*tree\ connect\ failed*) ok "$USER_B is refused the $USER_A share" ;; *) bad "$USER_B got into the $USER_A share: $out" ;; esac

# 4. a wrong password is refused
out=$(as "$USER_A" "not-the-password" "//$BOX/$USER_A" -m SMB3 -c "ls")
case $out in *NT_STATUS_LOGON_FAILURE*) ok "a wrong password is refused" ;; *) bad "wrong password was not refused: $out" ;; esac

# 5. no guest, no anonymous
out=$(smbclient -N "//$BOX/$USER_A" -m SMB3 -c "ls" 2>&1)
case $out in *NT_STATUS_ACCESS_DENIED*|*NT_STATUS_LOGON_FAILURE*|*session\ setup\ failed*) ok "anonymous access is refused" ;; *) bad "anonymous access worked: $out" ;; esac

# 6. SMB1 is refused
out=$(PASSWD=$PASS_A smbclient -L "//$BOX" -U "$USER_A" -m NT1 2>&1)
case $out in *"$USER_A"*Disk*) bad "SMB1 was accepted: $out" ;; *) ok "SMB1 is refused" ;; esac

exit "$fail"
