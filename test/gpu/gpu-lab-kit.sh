#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# GPU lab kit (S-5): the first real test of the GPU image variant, run as root ON the booted GPU machine
# (a rented one is fine). It checks the chain one link at a time and stops at the first broken link, so the
# failing line says what to fix. Nothing here changes the box except a throwaway namespace, removed at the end.
#   sh gpu-lab-kit.sh            # all links
#   sh gpu-lab-kit.sh --no-model # skip the model download (links 1-5 only)
set -u
K="k3s kubectl"
NS=gpu-lab
ok()   { printf 'PASS %s\n' "$1"; }
bad()  { printf 'FAIL %s\n     fix: %s\n' "$1" "$2"; cleanup; exit 1; }
cleanup() { $K delete ns "$NS" --ignore-not-found --wait=false >/dev/null 2>&1 || true; }

# 1. the image is the GPU variant, and it was built for this kernel
[ -f /usr/lib/onemind/gpu-info.txt ] || bad "1 this is not the GPU image" "boot an image built with BOARD=x86_64-efi-nvidia"
grep -q "kernel=$(uname -r)" /usr/lib/onemind/gpu-info.txt || bad "1 modules built for another kernel: $(cat /usr/lib/onemind/gpu-info.txt)" "rebuild the image"
ok "1 GPU image ($(cat /usr/lib/onemind/gpu-info.txt))"

# 2. an NVIDIA card is on the bus and the driver owns it
lspci -nn | grep -qi '\[10de:' || bad "2 no NVIDIA card on the PCI bus" "rent a machine with an NVIDIA GPU"
lsmod | grep -q '^nvidia ' || bad "2 nvidia module not loaded (Secure Boot on? nouveau holding the card?)" "journalctl -u onemind-nvidia-setup; dmesg | grep -i nvidia"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || bad "2 nvidia-smi failed" "dmesg | grep -i nvidia"
ok "2 driver loaded"

# 3. the gateway-side facts: onemindd must report the GPU in its heartbeat (it reads /proc/driver/nvidia)
[ -d /proc/driver/nvidia ] || bad "3 /proc/driver/nvidia missing" "driver did not initialise"
ok "3 /proc/driver/nvidia present, so onemindd reports gpu.nvidia=true"

# 4. the container stack: runtime, RuntimeClass, device plugin advertising the GPU
command -v nvidia-container-runtime >/dev/null || bad "4 nvidia-container-runtime missing" "toolkit install step failed"
nvidia-container-cli info >/dev/null 2>&1 || bad "4 nvidia-container-cli cannot see the driver" "nvidia-container-cli -k -d /dev/tty info"
$K get runtimeclass nvidia >/dev/null 2>&1 || bad "4 RuntimeClass nvidia missing" "systemctl status onemind-nvidia-setup; ls /data/k3s/server/manifests"
n=0
while [ "$n" -lt 60 ]; do
  g=$($K get node -o jsonpath='{.items[0].status.allocatable.nvidia\.com/gpu}' 2>/dev/null)
  [ -n "$g" ] && [ "$g" != 0 ] && break
  n=$((n + 1)); sleep 5
done
[ -n "${g:-}" ] && [ "$g" != 0 ] || bad "4 node does not advertise nvidia.com/gpu after 5 minutes" "$K -n kube-system logs ds/nvidia-device-plugin"
ok "4 node advertises nvidia.com/gpu=$g"

# 5. a pod can use the GPU
cleanup; $K create ns "$NS" >/dev/null
cat <<'EOF' | $K -n "$NS" apply -f - >/dev/null
apiVersion: v1
kind: Pod
metadata: {name: smi}
spec:
  runtimeClassName: nvidia
  restartPolicy: Never
  securityContext: {runAsNonRoot: true, runAsUser: 1000, seccompProfile: {type: RuntimeDefault}}
  containers:
    - name: smi
      image: docker.io/library/debian:trixie-slim
      command: ["nvidia-smi", "-L"]
      env: [{name: NVIDIA_DRIVER_CAPABILITIES, value: "utility"}]
      securityContext: {allowPrivilegeEscalation: false, capabilities: {drop: ["ALL"]}}
      resources: {limits: {nvidia.com/gpu: 1}}
EOF
$K -n "$NS" wait --for=jsonpath='{.status.phase}'=Succeeded pod/smi --timeout=180s >/dev/null 2>&1 || bad "5 pod could not run nvidia-smi" "$K -n $NS describe pod smi"
ok "5 pod sees the GPU: $($K -n "$NS" logs smi | head -1)"
[ "${1:-}" = "--no-model" ] && { cleanup; echo "links 1-5 passed (model step skipped)"; exit 0; }

# 6. Ollama on the GPU, from the app's own overlay (apps/ollama/manifests-gpu)
$K kustomize /usr/lib/onemind/apps/ollama/manifests-gpu | $K -n "$NS" apply -f - >/dev/null || bad "6 could not apply the Ollama GPU overlay" "check /usr/lib/onemind/apps/ollama/manifests-gpu"
$K -n "$NS" rollout status deploy/ollama --timeout=600s >/dev/null || bad "6 Ollama did not start" "$K -n $NS describe pod -l app.kubernetes.io/name=ollama"
$K -n "$NS" exec deploy/ollama -- ollama pull qwen2.5:0.5b >/dev/null || bad "6 model download failed" "network on the rented machine"
$K -n "$NS" exec deploy/ollama -- ollama run qwen2.5:0.5b "Say OK" >/dev/null || bad "6 model did not answer" "$K -n $NS logs deploy/ollama"
ps=$($K -n "$NS" exec deploy/ollama -- ollama ps)
echo "$ps"
echo "$ps" | grep -q 'GPU' || bad "6 model ran but not on the GPU" "$K -n $NS logs deploy/ollama | grep -i -E 'cuda|gpu'"
ok "6 Ollama answered and ollama ps says GPU"
cleanup
echo "all links passed: record the GPU model, driver and 'ollama ps' output in the PR"
