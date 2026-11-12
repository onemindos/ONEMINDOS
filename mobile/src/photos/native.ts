// SPDX-License-Identifier: Apache-2.0
// The phone side: the photo library (expo-media-library → PhotoKit / MediaStore), file reads and
// SHA-256 (expo-file-system, native), network and power state (expo-network, expo-battery), and the
// app-sandbox files that hold settings and the ledger. All MIT, Expo SDK 58.
import * as Battery from 'expo-battery';
import { File, FileMode, Paths } from 'expo-file-system';
import * as MediaLibrary from 'expo-media-library/legacy';
import * as Network from 'expo-network';
import { Platform as RNPlatform } from 'react-native';
import type { Conditions } from './engine';
import { parseLedger, parseSettings, type BackupSettings, type BackupStore, type Ledger } from './ledger';
import type { AlbumSelection, MediaAsset, MediaPermission, MediaSource } from './media';
import type { Platform } from './protocol';

export const PLATFORM: Platform = RNPlatform.OS === 'ios' ? 'ios' : RNPlatform.OS === 'android' ? 'android' : 'other';

function toPermission(p: MediaLibrary.PermissionResponse): MediaPermission {
  if (p.granted) return p.accessPrivileges === 'limited' ? 'limited' : 'granted';
  return p.canAskAgain ? 'undetermined' : 'denied';
}

export class ExpoMedia implements MediaSource {
  private readonly uris = new Map<string, string>();

  async permission(request: boolean): Promise<MediaPermission> {
    const cur = toPermission(await MediaLibrary.getPermissionsAsync(false));
    if (cur !== 'undetermined' || !request) return cur;
    return toPermission(await MediaLibrary.requestPermissionsAsync(false));
  }

  async albums() {
    const list = await MediaLibrary.getAlbumsAsync({ includeSmartAlbums: true });
    return list.filter((a) => a.assetCount > 0).map((a) => ({ id: a.id, title: a.title, count: a.assetCount }));
  }

  async list(selection: AlbumSelection): Promise<MediaAsset[]> {
    const seen = new Map<string, MediaAsset>();
    const scopes: (string | undefined)[] = selection === 'all' ? [undefined] : selection;
    for (const album of scopes) {
      let after: string | undefined;
      for (;;) {
        const page = await MediaLibrary.getAssetsAsync({
          first: 500,
          after,
          album,
          mediaType: [MediaLibrary.MediaType.photo, MediaLibrary.MediaType.video],
          sortBy: [[MediaLibrary.SortBy.creationTime, true]],
        });
        for (const a of page.assets)
          seen.set(a.id, {
            id: a.id,
            fileName: a.filename,
            kind: a.mediaType === MediaLibrary.MediaType.video ? 'video' : 'photo',
            createdAt: a.creationTime,
            modifiedAt: a.modificationTime,
          });
        if (!page.hasNextPage) break;
        after = page.endCursor;
      }
    }
    return [...seen.values()].sort((a, b) => a.createdAt - b.createdAt);
  }

  /** A readable file for the asset; iCloud-only originals are downloaded by the OS first. */
  private async file(a: MediaAsset): Promise<File> {
    let uri = this.uris.get(a.id);
    if (!uri) {
      const info = await MediaLibrary.getAssetInfoAsync(a.id, { shouldDownloadFromNetwork: true });
      if (!info.localUri) throw new Error('The original is not on this phone (iCloud only?)');
      uri = info.localUri;
      this.uris.set(a.id, uri);
    }
    return new File(uri);
  }

  async size(a: MediaAsset) {
    const f = await this.file(a);
    if (!f.exists) throw new Error('The file is no longer on this phone');
    return f.size ?? 0;
  }

  async hash(a: MediaAsset) {
    return `sha256:${(await (await this.file(a)).digest('SHA-256')).toLowerCase()}`;
  }

  async read(a: MediaAsset, offset: number, length: number) {
    const h = (await this.file(a)).open(FileMode.ReadOnly);
    try {
      h.offset = offset;
      return await h.readBytes(length);
    } finally {
      h.close();
    }
  }
}

export async function readConditions(): Promise<Conditions> {
  const [net, power] = await Promise.all([
    Network.getNetworkStateAsync().catch(() => undefined),
    Battery.getBatteryStateAsync().catch(() => Battery.BatteryState.UNKNOWN),
  ]);
  const t = net?.type;
  const network =
    !net || net.isConnected === false
      ? 'none'
      : t === Network.NetworkStateType.WIFI || t === Network.NetworkStateType.ETHERNET
        ? 'wifi'
        : t === Network.NetworkStateType.CELLULAR
          ? 'cellular'
          : 'other';
  return {
    network,
    power:
      power === Battery.BatteryState.CHARGING || power === Battery.BatteryState.FULL
        ? 'charging'
        : power === Battery.BatteryState.UNPLUGGED || power === Battery.BatteryState.NOT_CHARGING
          ? 'battery'
          : 'unknown',
  };
}

/** Settings and ledger as JSON files in the app's private documents folder (excluded from nothing; holds no secret). */
export class FileStore implements BackupStore {
  private f(name: string) {
    return new File(Paths.document, name);
  }
  private async read(name: string): Promise<string | null> {
    try {
      const f = this.f(name);
      return f.exists ? await f.text() : null;
    } catch {
      return null;
    }
  }
  private async write(name: string, text: string) {
    const tmp = this.f(`${name}.tmp`);
    await tmp.write(text);
    const dst = this.f(name);
    if (dst.exists) dst.delete();
    tmp.move(dst);
  }
  async loadLedger() {
    return parseLedger(await this.read('photo-backup-ledger.json'));
  }
  async saveLedger(l: Ledger) {
    await this.write('photo-backup-ledger.json', JSON.stringify(l));
  }
  async loadSettings() {
    return parseSettings(await this.read('photo-backup-settings.json'));
  }
  async saveSettings(s: BackupSettings) {
    await this.write('photo-backup-settings.json', JSON.stringify(s));
  }
}
