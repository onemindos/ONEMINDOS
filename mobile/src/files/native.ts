// SPDX-License-Identifier: Apache-2.0
// The phone side of Files: the system document picker (expo-document-picker), streaming a download to disk
// (expo-file-system) and the OS share sheet (expo-sharing). All MIT, Expo SDK 58. iOS needs no extra
// permission for any of these; Android uses the system picker and a FileProvider the module registers itself.
import { Directory, DocumentPicker, File, FileMode, Paths, Sharing } from '../device/files';
import type { FilesDevice, LocalFile } from '../lib/filesTransfer';

const safe = (name: string) => name.replace(/[\\/:*?"<>|]/g, '_');

export function asLocalFile(f: File, name: string, size = f.size): LocalFile {
  return {
    name,
    size,
    async read(offset, length) {
      const h = f.open(FileMode.ReadOnly);
      try {
        h.offset = offset;
        return await h.readBytes(length);
      } finally {
        h.close();
      }
    },
    sha256: async () => (await f.digest('SHA-256')).toLowerCase(),
  };
}

export const nativeFiles: FilesDevice = {
  async pick() {
    const r = await DocumentPicker.getDocumentAsync({ copyToCacheDirectory: true, multiple: false });
    const a = r.canceled ? undefined : r.assets[0];
    if (!a) return undefined;
    const f = new File(a.uri);
    return asLocalFile(f, a.name, a.size ?? f.size);
  },
  async download(req, name) {
    const dir = new Directory(Paths.cache, 'onemind-downloads');
    dir.create({ idempotent: true, intermediates: true });
    const out = await File.downloadFileAsync(req.url, new File(dir, safe(name)), { headers: req.headers, idempotent: true });
    return out.uri;
  },
  async share(uri, name) {
    if (!(await Sharing.isAvailableAsync())) throw new Error('Sharing is not available on this device');
    await Sharing.shareAsync(uri, { dialogTitle: name });
  },
};
