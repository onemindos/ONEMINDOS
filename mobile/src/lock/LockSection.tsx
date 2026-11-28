// SPDX-License-Identifier: Apache-2.0
// Settings > Lock OneMind (issue #704).
import { useState } from 'react';
import { View } from 'react-native';
import { Button, Card, H2, Notice, P, Row, s } from '../ui/bits';
import { RELOCK_MS, useLock } from './LockProvider';

export function LockSection() {
  const { available, enabled, setEnabled } = useLock();
  const [msg, setMsg] = useState<string>();
  const toggle = async () => {
    setMsg(undefined);
    if (!(await setEnabled(!enabled))) setMsg('Not changed: unlock was cancelled or failed.');
  };
  return (
    <>
      <H2>Lock OneMind</H2>
      <Card testID="lock-section">
        <Row label="Lock" value={enabled ? 'on' : 'off'} />
        <P muted small>
          {`With the lock on, OneMind asks for your face, fingerprint or phone PIN when it opens and after ${RELOCK_MS / 1000} s in the background. Photo backup and alerts keep working while it is locked.`}
        </P>
        {available === false && <Notice tone="warn" text="Set up a screen lock or fingerprint on this phone first." />}
        {msg && <Notice tone="warn" text={msg} />}
        <View style={s.wrap}>
          <Button
            testID="lock-toggle"
            variant="secondary"
            label={enabled ? 'Turn lock off' : 'Turn lock on'}
            disabled={!enabled && !available}
            onPress={() => void toggle()}
          />
        </View>
      </Card>
    </>
  );
}
