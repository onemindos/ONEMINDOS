// SPDX-License-Identifier: Apache-2.0
// Nodes: one card per machine from GET /v1/nodes. Status is the gateway's verdict aged on the
// hub clock, so a stale or offline machine keeps its last values but never looks live.
import { EmptyState, NodeCard, PageHeader, StateView } from '@onemind/ui';
import { useHub } from '../data/hub';

export function Nodes() {
  const hub = useHub();
  const nodes = hub.nodes.data;
  const stale = hub.freshness === 'stale' || hub.freshness === 'offline';
  return (
    <>
      <PageHeader title="Nodes" lede="The machines in this OneMind. Each sends a heartbeat every 10 s; after 30 s without one it is stale, after 2 minutes offline." />
      {nodes === undefined ? (
        hub.nodes.error ? (
          <StateView state="error" error={{ error: hub.nodes.error.code === 'network' ? 'unreachable' : hub.nodes.error.code === 'unauthenticated' ? 'unauthenticated' : 'not_found', message: hub.nodes.error.message }} onRetry={hub.reloadAll} />
        ) : (
          <StateView state="loading" what="Loading nodes" skeleton="list" />
        )
      ) : nodes.length === 0 ? (
        <EmptyState icon="nodes" title="No machines have reported yet" command="onemind node join">
          <p>The hub lists a machine after its first heartbeat. Adding nodes from here comes with CORE-FABRIC (join codes).</p>
        </EmptyState>
      ) : (
        <>
          {stale && (
            <p className="om-note om-tone-warn" role="status">
              The hub has not answered for a while. These are the last values it sent, not live.
            </p>
          )}
          <ul className="dash-grid" aria-label="Nodes">
            {nodes.map((n) => (
              <li key={n.node_id}>
                <NodeCard node={{ ...n, status: hub.nodeStatus(n) }} now={hub.now} />
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
