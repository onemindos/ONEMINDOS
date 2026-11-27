// SPDX-License-Identifier: Apache-2.0
import { requireNativeModule } from 'expo';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { File } from 'expo-file-system';
import { useRef, useState } from 'react';
import { View } from 'react-native';
import { Button, Notice, P, s as base } from '../ui/bits';
import { radiusControl } from '../ui/theme';

type JoinQr = { readCameraPhoto(uri: string): Promise<string | null> };

export function JoinScanner({ onCode, onCancel }: { onCode: (text: string) => void; onCancel: () => void }) {
  const [permission, ask] = useCameraPermissions();
  const [ready, setReady] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [notice, setNotice] = useState<string>();
  const camera = useRef<CameraView>(null);
  const busy = useRef(false);
  const done = useRef(false);

  async function scan() {
    if (!camera.current || busy.current || done.current) return;
    busy.current = true;
    setScanning(true);
    setNotice(undefined);
    let code: string | null = null;
    try {
      const photo = await camera.current.takePictureAsync({ quality: 0.6, skipProcessing: true });
      const file = new File(photo.uri);
      try {
        code = await requireNativeModule<JoinQr>('OneMindJoinQr').readCameraPhoto(file.uri);
      } finally {
        file.delete();
      }
      if (!code && !done.current) setNotice('No join code found. Fill the frame with the code and try again.');
    } catch {
      if (!done.current) setNotice('The camera could not read the code. Try again or type the code below.');
      return;
    } finally {
      busy.current = false;
      if (!done.current) setScanning(false);
    }
    if (code && !done.current) {
      done.current = true;
      onCode(code);
    }
  }

  const cancel = <Button testID="scan-cancel" variant="secondary" label="Cancel" onPress={() => {
    done.current = true;
    onCancel();
  }} />;
  if (!permission) return <View style={base.wrap}>{cancel}</View>;
  if (!permission.granted) {
    return (
      <View style={{ gap: 8 }}>
        <Notice tone="warn" text={permission.canAskAgain
          ? 'OneMind needs the camera to read the code on your box. The scan stays on this phone.'
          : 'Camera access is off for OneMind. Turn it on in the phone settings, or type the code below.'} />
        <View style={base.wrap}>
          {permission.canAskAgain && <Button testID="scan-allow" label="Allow the camera" onPress={() => void ask()} />}
          {cancel}
        </View>
      </View>
    );
  }
  return (
    <View style={{ gap: 8 }}>
      <CameraView ref={camera} testID="join-camera"
        style={{ width: '100%', aspectRatio: 1, borderRadius: radiusControl, overflow: 'hidden' }}
        facing="back" onCameraReady={() => setReady(true)} />
      <P muted small>Point the camera at the join code your box shows (Add a machine on the dashboard).</P>
      {notice && <Notice tone="warn" text={notice} />}
      <View style={base.wrap}>
        <Button label={scanning ? "Scanning…" : "Scan code"} disabled={!ready || scanning} onPress={() => void scan()} />
        {cancel}
      </View>
    </View>
  );
}
