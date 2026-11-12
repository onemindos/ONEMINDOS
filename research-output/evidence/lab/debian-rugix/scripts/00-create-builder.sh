#!/usr/bin/env bash
# Create the disposable Lima build VM. Usage: LAB=<dir outside repo> ./00-create-builder.sh
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
LAB=${LAB:?set LAB to a lab directory outside the repo}
export LIMA_HOME="$LAB/lima"
mkdir -p "$LIMA_HOME" "$LAB/work"
sed "s|{{.Env.LAB_WORK}}|$LAB/work|" "$HERE/lima-builder.yaml" > "$LAB/lima-builder.rendered.yaml"
limactl create --tty=false --name=dr "$LAB/lima-builder.rendered.yaml"
limactl start --tty=false dr
limactl shell dr -- sudo docker version --format '{{.Server.Version}}'
limactl shell dr -- sh -c 'cat /proc/sys/fs/binfmt_misc/qemu-x86_64'
