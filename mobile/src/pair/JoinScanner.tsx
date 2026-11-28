// SPDX-License-Identifier: Apache-2.0
// The camera view that reads the box's join QR (issue 716). It only reads text: what the text means, and
// whether it is safe, is decided by pair.ts (readJoin, trustBox). The first QR seen is handed over once.
import { CameraView, useCameraPermissions, type BarcodeScanningResult } from '../device/camera';
import { useRef } from 'react';
import { View } from 'react-native';
import { Button, Notice, P, s as base } from '../ui/bits';
import { radiusControl } from '../ui/theme';

export function JoinScanner({ onCode, onCancel }: { onCode: (text: string) => void; onCancel: () => void }) {
  const [permission, ask] = useCameraPermissions();
  const done = useRef(false);

  const seen = (r: BarcodeScanningResult) => {
    if (done.current || !r.data) return;
    done.current = true;
    onCode(r.data);
  };

  const cancel = <Button testID="scan-cancel" variant="secondary" label="Cancel" onPress={onCancel} />;
  if (!permission) return <View style={base.wrap}>{cancel}</View>;
  if (!permission.granted)
    return (
      <View style={{ gap: 8 }}>
        <Notice
          tone="warn"
          text={
            permission.canAskAgain
              ? 'OneMind needs the camera to read the code on your box. Nothing is recorded or sent.'
              : 'Camera access is off for OneMind. Turn it on in the phone settings, or type the code below.'
          }
        />
        <View style={base.wrap}>
          {permission.canAskAgain && <Button testID="scan-allow" label="Allow the camera" onPress={() => void ask()} />}
          {cancel}
        </View>
      </View>
    );
  return (
    <View style={{ gap: 8 }}>
      <CameraView
        testID="join-camera"
        style={{ width: '100%', aspectRatio: 1, borderRadius: radiusControl, overflow: 'hidden' }}
        facing="back"
        barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
        onBarcodeScanned={seen}
      />
      <P muted small>Point the camera at the join code your box shows (Add a machine on the dashboard).</P>
      <View style={base.wrap}>{cancel}</View>
    </View>
  );
}
