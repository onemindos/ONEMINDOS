// SPDX-License-Identifier: Apache-2.0
// Settings > About: the device card a family member reads. Box name, version, how long it has been
// on, how full the disk is and how much memory it has, then Log out. Every number is one the hub
// reports (GET /v1/os/about, per node); a missing number is left out, never made up. Restart and
// Shut down are not here: the hub serves no power route yet (system controls, #146), and a button
// that does nothing would be worse than none.
import { Button, Card, Meter } from '@onemind/ui';
import type { AboutBox } from '../api/client';
import { diskText, memText, uptimeText } from '../lib/aboutText';

type Node = AboutBox['nodes'][number];

export function DeviceCard({ name, version, node, onLogOut }: { name: string; version?: string; node?: Node; onLogOut: () => void }) {
  const total = node?.disk_total_gb;
  const free = node?.disk_free_gb;
  const haveDisk = typeof total === 'number' && typeof free === 'number' && total > 0;
  return (
    <Card title={name} level={2}>
      <dl className="om-facts">
        {version && (
          <div>
            <dt>Version</dt>
            <dd>{version}</dd>
          </div>
        )}
        {node?.uptime_s != null && (
          <div>
            <dt>Running for</dt>
            <dd>{uptimeText(node.uptime_s)}</dd>
          </div>
        )}
        {node?.mem_total_mb != null && (
          <div>
            <dt>Memory</dt>
            <dd>{memText(node.mem_total_mb)}</dd>
          </div>
        )}
      </dl>
      {haveDisk && <Meter label="Storage" value={total - free} max={total} valueText={`${diskText(total - free)} of ${diskText(total)} used`} />}
      <div className="dash-actions">
        <Button onClick={onLogOut}>Log out</Button>
      </div>
    </Card>
  );
}
