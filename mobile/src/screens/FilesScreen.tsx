// SPDX-License-Identifier: Apache-2.0
// Files: browse the folders the box shares with you, save or share a file, and add a file from the phone to a
// folder you may write to. Each part shows only when the hub serves its route. Moving, trashing and sharing
// links are not here: those stay on the dashboard. Photos have their own backup screen.
import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { OP } from '../api/client';
import { uploadLocalFile, uploadProblem, type FilesDevice } from '../lib/filesTransfer';
import { formatBytes } from '../lib/manage';
import { useLoad } from '../lib/useLoad';
import { useSignedIn } from '../session';
import { Badge, Button, Card, H1, H2, Loading, Notice, P, Screen, s } from '../ui/bits';
import { font, useTheme } from '../ui/theme';

/** "/a/b" -> "/a"; "/a" -> "/". */
export function parentOf(path: string): string {
  const i = path.replace(/\/+$/, '').lastIndexOf('/');
  return i <= 0 ? '/' : path.slice(0, i);
}
export function join(path: string, name: string): string {
  return `${path === '/' ? '' : path.replace(/\/+$/, '')}/${name}`;
}

const BACKUP_BADGE: Record<string, { label: string; tone: 'ok' | 'warn' | 'bad' }> = {
  verified: { label: 'Safe in a backup, restore-checked', tone: 'ok' },
  unverified: { label: 'Backed up, not restore-checked yet', tone: 'warn' },
  stale: { label: 'Backup is out of date', tone: 'warn' },
  failing: { label: 'Backup is failing', tone: 'bad' },
};

function nativeDevice(): FilesDevice {
  // Loaded on first use so the screen (and its tests) never touch native modules until a button is pressed.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  return (require('../files/native') as typeof import('../files/native')).nativeFiles;
}

function VersionHistory({ root, path }: { root: string; path: string }) {
  const { api } = useSignedIn();
  const history = useLoad(() => api.filesVersions(root, path), [api, root, path]);

  if (history.loading) return <Loading what="previous versions" />;
  if (history.error) return <Notice tone="bad" text={`Could not read previous versions: ${history.error.message}`} />;
  if (!history.data?.enabled) return <P muted small>Local versions are off on this box.</P>;
  if (history.data.versions.length === 0) return <P muted small>No previous versions for this file.</P>;
  return (
    <View>
      {history.data.versions.map((version) => (
        <P key={version.version} small>{new Date(version.taken_at).toLocaleString()} · {formatBytes(version.size)}</P>
      ))}
      <P muted small>Restore a previous version from Files on the dashboard.</P>
    </View>
  );
}

export function FilesScreen({ device }: { device?: FilesDevice } = {}) {
  const t = useTheme();
  const { api, features } = useSignedIn();
  const [busy, setBusy] = useState<string>();
  const [msg, setMsg] = useState<{ text: string; tone: 'ok' | 'bad' }>();
  const canDownload = features.has(OP.filesDownload);
  const canUpload = features.has(OP.filesUploads);
  const canSeeVersions = features.has(OP.filesVersions);
  const [historyTarget, setHistoryTarget] = useState<{ root: string; path: string }>();
  // The box-wide badge from the backups route (it is not per file: the hub reports no per-file state).
  const backup = useLoad(() => (features.has(OP.backupStatus) ? api.backupStatus().catch(() => undefined) : Promise.resolve(undefined)), [api]);
  const badge = backup.data?.badges?.box ? BACKUP_BADGE[backup.data.badges.box.state] : undefined;
  const [at, setAt] = useState<{ root: string; path: string }>();
  const roots = useLoad(() => api.filesRoots(), [api]);
  const list = useLoad(() => (at ? api.filesList(at.root, at.path) : Promise.resolve([])), [api, at?.root, at?.path]);

  // A fresh hub answers 503 with reason `storage_unavailable` (seen on a real gateway, MOB-LIVE-01).
  const noStorage = roots.error?.reason === 'storage_unavailable';

  if (roots.loading) return <Loading what="files" />;
  if (!at)
    return (
      <Screen testID="files">
        <H1>Files</H1>
        {roots.error ? <Notice tone={roots.forbidden || noStorage ? 'warn' : 'bad'} text={roots.forbidden ? 'This sign-in has no files.' : noStorage ? 'This hub has no storage for shared files yet.' : `Could not read files: ${roots.error.message}`} /> : null}
        {(roots.data ?? []).length === 0 && !roots.error ? <P muted>No folders are shared with you.</P> : null}
        {(roots.data ?? []).map((r) => (
          <Pressable key={r.root} testID={`root-${r.root}`} accessibilityRole="button" onPress={() => setAt({ root: r.root, path: r.path || '/' })}>
            <Card>
              <View style={s.row}>
                <Text style={{ color: t.text, fontSize: font.md, fontWeight: font.semibold }}>{r.name}</Text>
                <Badge label={r.writable ? 'read and write' : 'read only'} />
              </View>
              <P muted small>
                {r.used_bytes != null ? `${formatBytes(r.used_bytes)} used` : 'size unknown'}
                {r.quota_bytes ? ` of ${formatBytes(r.quota_bytes)}` : ''}
              </P>
            </Card>
          </Pressable>
        ))}
        <P muted small>Moving and deleting files is done on the dashboard.</P>
      </Screen>
    );

  const dev = () => (device ??= nativeDevice());
  const writable = (roots.data ?? []).find((r) => r.root === at.root)?.writable === true;

  /** Fetch to the phone, then open the system sheet: it offers "Save to Files", other apps and AirDrop/Nearby Share. */
  async function fetchFile(name: string) {
    setBusy(`file-${name}`);
    setMsg(undefined);
    try {
      const local = await dev().download(api.filesDownloadRequest(at!.root, join(at!.path, name)), name);
      await dev().share(local, name);
      setMsg({ text: `${name} was fetched from the hub.`, tone: 'ok' });
    } catch (e) {
      setMsg({ text: `Could not get ${name}: ${uploadProblem(e)}`, tone: 'bad' });
    } finally {
      setBusy(undefined);
    }
  }

  async function addFile() {
    setBusy('upload');
    setMsg(undefined);
    try {
      const f = await dev().pick();
      if (!f) return;
      await uploadLocalFile(api, f, at!.root, at!.path, (sent, total) => setMsg({ text: `Sending ${f.name}: ${formatBytes(sent)} of ${formatBytes(total)}`, tone: 'ok' }));
      setMsg({ text: `${f.name} is on the hub.`, tone: 'ok' });
      await list.reload();
    } catch (e) {
      setMsg({ text: `Could not add the file: ${uploadProblem(e)}`, tone: 'bad' });
    } finally {
      setBusy(undefined);
    }
  }

  const rootName = (roots.data ?? []).find((r) => r.root === at.root)?.name ?? at.root;
  return (
    <Screen testID="files-folder">
      <H1>{rootName}</H1>
      <P muted small>{at.path}</P>
      {badge ? <Badge label={badge.label} tone={badge.tone} /> : null}
      {msg ? <Notice tone={msg.tone === 'ok' ? 'info' : 'bad'} text={msg.text} /> : null}
      {canUpload && writable ? <Button testID="files-add" label={busy === 'upload' ? 'Sending...' : 'Add a file from this phone'} disabled={busy !== undefined} onPress={() => void addFile()} /> : null}
      <View style={s.wrap}>
        <Pressable testID="files-up" accessibilityRole="button" onPress={() => setAt(at.path === '/' ? undefined : { root: at.root, path: parentOf(at.path) })}>
          <Badge label="← Back" tone="info" />
        </Pressable>
      </View>
      {list.loading ? <Loading what="folder" /> : null}
      {list.error ? <Notice tone="bad" text={`Could not open this folder: ${list.error.message}`} /> : null}
      {!list.loading && !list.error && (list.data ?? []).length === 0 ? <P muted>This folder is empty.</P> : null}
      {(list.data ?? []).map((e) => {
        const path = join(at.path, e.name);
        const showingHistory = historyTarget?.root === at.root && historyTarget.path === path;
        return e.type === 'dir' ? (
          <Pressable key={e.name} testID={`dir-${e.name}`} accessibilityRole="button" onPress={() => setAt({ root: at.root, path: join(at.path, e.name) })}>
            <Card>
              <Text style={{ color: t.text, fontSize: font.md }}>📁 {e.name}</Text>
            </Card>
          </Pressable>
        ) : (
          <Card key={e.name} testID={`file-${e.name}`}>
            <View style={s.row}>
              <Text style={{ color: t.text, fontSize: font.md, flexShrink: 1 }}>{e.name}</Text>
              <Text style={{ color: t.muted, fontSize: font.sm }}>{formatBytes(e.size)}</Text>
            </View>
            {canDownload ? (
              <View style={s.wrap}>
                <Button testID={`save-${e.name}`} variant="secondary" label={busy === `file-${e.name}` ? 'Fetching...' : 'Save or share'} disabled={busy !== undefined} onPress={() => void fetchFile(e.name)} />
              </View>
            ) : null}
            {canSeeVersions && e.type === 'file' ? (
              <View>
                <Button variant="secondary" label={showingHistory ? 'Hide previous versions' : 'Previous versions'} onPress={() => setHistoryTarget(showingHistory ? undefined : { root: at.root, path })} />
                {showingHistory ? <VersionHistory root={at.root} path={path} /> : null}
              </View>
            ) : null}
          </Card>
        );
      })}
      <H2>On the dashboard</H2>
      <P muted small>Moving, deleting and share links are done on the dashboard.</P>
    </Screen>
  );
}
