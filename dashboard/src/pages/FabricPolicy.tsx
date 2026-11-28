// SPDX-License-Identifier: Apache-2.0
import { Card } from '@onemind/ui';
import type { components } from '@onemind/sdk';
import { usePoll } from '../lib/hooks';
import { read, usePermSdk } from '../lib/permissions';
import { Load } from './parts';

export function FabricPolicy() {
  const sdk = usePermSdk();
  const snapshot = usePoll(() => read(sdk.call<components['schemas']['FabricPolicy']>({ method: 'GET', path: '/v1/fabric/policy' })), 15_000);

  return <Card title="Machine policy delivery">
    <Load res={snapshot} what="Loading the machine policy">
      {(policy) => <>
        <p>Policy version {policy.epoch}. Agent stop {policy.stop.agents ? 'on' : 'off'}. Motion lockout {policy.stop.motion_lockout ? 'on' : 'off'}.</p>
        {policy.error && <p role="alert">Policy delivery failed: {policy.error}</p>}
        {Object.keys(policy.published).length > 0
          ? <ul aria-label="Published machine policies">
            {Object.entries(policy.published).map(([id, epoch]) => <li key={id}>{id}: version {epoch}</li>)}
          </ul>
          : <p>No machine policy deliveries reported.</p>}
      </>}
    </Load>
  </Card>;
}
