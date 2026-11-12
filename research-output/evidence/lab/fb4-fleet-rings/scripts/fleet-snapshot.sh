#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# LAB-fb4-fleet-rings: hub-side status snapshot and footprint (E2, E4) for a given run directory.
set -uo pipefail; S=$(cd "$(dirname "$0")" && pwd); . $S/fleet-lib.sh
R=$OUT/${1:?run dir}; mkdir -p $R/snap; HUBIP=$(cat $W/hubip)
kc hub -n fleet-default get bundle demo -o json | jq '{generation:.metadata.generation,observedGeneration:.status.observedGeneration,summary:.status.summary,display:.status.display,partitions:.status.partitions,unavailable:.status.unavailable,unavailablePartitions:.status.unavailablePartitions,conditions:.status.conditions}' > $R/snap/bundle.json
kc hub get bundledeployments -A -o json | jq '[.items[]|select(.metadata.name=="demo")|{ns:.metadata.namespace,deploymentID:.spec.deploymentID,staged:.spec.stagedDeploymentID,applied:.status.appliedDeploymentID,ready:.status.ready,display:.status.display}]' > $R/snap/bundledeployments.json
kc hub -n fleet-default get clusters.fleet.cattle.io -o json | jq '[.items[]|{site:.metadata.labels.site,ring:.metadata.labels.ring,display:.status.display,summary:.status.summary,agentLastSeen:.status.agent.lastSeen}]' > $R/snap/clusters.json
for c in hub box-1 site-b site-a; do docker exec k3d-$c-server-0 crictl stats -o json 2>/dev/null | jq -c --arg c $c '[.stats[]|{c:$c,name:.attributes.labels["io.kubernetes.container.name"],ns:.attributes.labels["io.kubernetes.pod.namespace"],mem_mib:(((.memory.workingSetBytes.value // "0")|tonumber)/1048576|floor)}]|map(select(.ns=="cattle-fleet-system" or .ns=="cattle-fleet-local-system"))'; done | jq -s 'add' > $R/snap/fleet-footprint.json
docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}}' > $R/snap/docker-stats.txt
for c in hub box-1; do docker exec k3d-$c-server-0 crictl images 2>/dev/null | grep -E 'fleet|pause' ; done | sort -u > $R/snap/images.txt
docker exec k3d-hub-server-0 crictl images --digests 2>/dev/null | grep fleet > $R/snap/fleet-image-digests.txt
free -m > $R/snap/free.txt; date -u +%FT%TZ > $R/snap/at.txt; echo snapshot done
