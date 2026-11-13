// SPDX-License-Identifier: Apache-2.0
// Files: browse the folders the box shares with you. Read only on the phone: moving, trashing and sharing are
// owner actions on the dashboard, and downloads are not offered here. Photos have their own backup screen.
import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { formatBytes } from '../lib/manage';
import { useLoad } from '../lib/useLoad';
import { useSignedIn } from '../session';
import { Badge, Card, H1, H2, Loading, Notice, P, Screen, s } from '../ui/bits';
import { font, useTheme } from '../ui/theme';

/** "/a/b" -> "/a"; "/a" -> "/". */
export function parentOf(path: string): string {
  const i = path.replace(/\/+$/, '').lastIndexOf('/');
  return i <= 0 ? '/' : path.slice(0, i);
}
export function join(path: string, name: string): string {
  return `${path === '/' ? '' : path.replace(/\/+$/, '')}/${name}`;
}

export function FilesScreen() {
  const t = useTheme();
  const { api } = useSignedIn();
  const [at, setAt] = useState<{ root: string; path: string }>();
  const roots = useLoad(() => api.filesRoots(), [api]);
  const list = useLoad(() => (at ? api.filesList(at.root, at.path) : Promise.resolve([])), [api, at?.root, at?.path]);

  if (roots.loading) return <Loading what="files" />;
  if (!at)
    return (
      <Screen testID="files">
        <H1>Files</H1>
        {roots.error ? <Notice tone={roots.forbidden ? 'warn' : 'bad'} text={roots.forbidden ? 'This sign-in has no files.' : `Could not read files: ${roots.error.message}`} /> : null}
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
        <P muted small>Opening and changing files is done on the dashboard.</P>
      </Screen>
    );

  const rootName = (roots.data ?? []).find((r) => r.root === at.root)?.name ?? at.root;
  return (
    <Screen testID="files-folder">
      <H1>{rootName}</H1>
      <P muted small>{at.path}</P>
      <View style={s.wrap}>
        <Pressable testID="files-up" accessibilityRole="button" onPress={() => setAt(at.path === '/' ? undefined : { root: at.root, path: parentOf(at.path) })}>
          <Badge label="← Back" tone="info" />
        </Pressable>
      </View>
      {list.loading ? <Loading what="folder" /> : null}
      {list.error ? <Notice tone="bad" text={`Could not open this folder: ${list.error.message}`} /> : null}
      {!list.loading && !list.error && (list.data ?? []).length === 0 ? <P muted>This folder is empty.</P> : null}
      {(list.data ?? []).map((e) =>
        e.type === 'dir' ? (
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
          </Card>
        ),
      )}
      <H2>Read only here</H2>
      <P muted small>To open, move or delete a file, use the dashboard.</P>
    </Screen>
  );
}
