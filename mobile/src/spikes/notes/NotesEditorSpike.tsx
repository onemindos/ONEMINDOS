// SPDX-License-Identifier: Apache-2.0
// SPIKE (docs/SPIKE-EDITOR.md): a Notes editor inside the app, offline. One WebView shows our own bundled
// ProseMirror page; the note is a Yjs doc saved on this phone. "Device B" is a second in-memory doc, used to
// prove two offline editors merge with nothing lost. Reachable only through spikesEnabled().
import { File, Paths } from 'expo-file-system';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';
import * as Y from 'yjs';
import { useTheme } from '../../ui/theme';
import { EDITOR_JS } from './editorBundle.generated';
import { editorHtml } from './editorHtml';
import { addBlock, fork, fromBase64, loadNote, saveNote, sync, toBase64, toMarkdown, type NoteStore } from './noteDoc';

const file = () => new File(Paths.document, 'spike-note.ydoc.b64');
const deviceStore: NoteStore = {
  read: async () => (file().exists ? await file().text() : null),
  write: async (b64) => {
    const f = file();
    if (!f.exists) f.create();
    f.write(b64);
  },
};

export function NotesEditorSpike() {
  const t = useTheme();
  const web = useRef<WebView<object>>(null);
  const doc = useRef<Y.Doc | null>(null);
  const other = useRef<Y.Doc | null>(null);
  const loaded = useRef(false);
  const [md, setMd] = useState('');
  const [status, setStatus] = useState('Loading…');
  const [hasB, setHasB] = useState(false);
  const [n, setN] = useState(0);
  const [ready, setReady] = useState(false);

  const send = useCallback((m: object) => web.current?.injectJavaScript(`window.__om(${JSON.stringify(m)});true;`), []);

  useEffect(() => {
    void loadNote(deviceStore).then((d) => {
      d.on('update', (u: Uint8Array, origin: unknown) => {
        setMd(toMarkdown(d));
        void saveNote(deviceStore, d).then((bytes) => setStatus(`Saved on this phone (${bytes} bytes)`));
        if (origin !== 'webview') send({ type: 'remote', u: toBase64(u) });
      });
      doc.current = d;
      setMd(toMarkdown(d));
      setStatus('Loaded from this phone');
      loaded.current = true;
      setN((x) => x + 1);
    });
  }, [send]);

  useEffect(() => {
    if (ready && doc.current) send({ type: 'init', state: toBase64(Y.encodeStateAsUpdate(doc.current)) });
  }, [ready, n, send]);

  const onMessage = (e: WebViewMessageEvent) => {
    const m = JSON.parse(e.nativeEvent.data) as { type: string; u?: string };
    if (m.type === 'ready') setReady(true);
    else if (m.type === 'update' && m.u && doc.current) Y.applyUpdate(doc.current, fromBase64(m.u), 'webview');
  };

  const html = useMemo(() => editorHtml(EDITOR_JS, { bg: t.bg, fg: t.text, accent: t.accent, border: t.border }), [t]);
  const A = doc.current;
  const btn = (label: string, onPress: () => void, disabled = false) => (
    <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress} style={{ minHeight: 48, justifyContent: 'center', paddingHorizontal: 12, borderWidth: 1, borderColor: t.border, borderRadius: 8, opacity: disabled ? 0.4 : 1 }}>
      <Text style={{ color: t.text }}>{label}</Text>
    </Pressable>
  );

  return (
    <View style={{ flex: 1, backgroundColor: t.bg }} testID="notes-editor-spike">
      <View style={{ flex: 1 }}>
        {loaded.current && (
          <WebView<object>
            ref={web}
            source={{ html, baseUrl: 'about:blank' }}
            originWhitelist={['about:*']}
            javaScriptEnabled
            allowFileAccess={false}
            domStorageEnabled={false}
            setSupportMultipleWindows={false}
            onShouldStartLoadWithRequest={(r: { url: string }) => r.url.startsWith('about:')}
            onMessage={onMessage}
          />
        )}
      </View>
      <ScrollView style={{ maxHeight: 260 }} contentContainerStyle={{ padding: 12, gap: 8 }}>
        <Text style={{ color: t.muted }}>{status}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {btn('Start device B (copy)', () => { if (A) { other.current = fork(A); setHasB(true); } })}
          {btn('B edits offline', () => { if (other.current) { addBlock(other.current, { kind: 'task', runs: [{ text: 'Added on B ' }, { text: String(Math.floor(Math.random() * 1000)), marks: ['strong'] }] }); setN((x) => x + 0); } }, !hasB)}
          {btn('Merge B and A', () => { if (A && other.current) { sync(A, other.current, 'merge'); setStatus('Merged: both devices now hold the same note'); } }, !hasB)}
          {btn('Add sample', () => { if (A) { addBlock(A, { kind: 'heading', level: 1, runs: [{ text: 'Sample' }] }); addBlock(A, { kind: 'task', runs: [{ text: 'A checklist item' }] }); } })}
        </View>
        <Text style={{ color: t.muted }}>Markdown of the note (open format):</Text>
        <Text selectable style={{ color: t.text, fontFamily: 'monospace' }}>{md || '(empty)'}</Text>
        {other.current && <Text style={{ color: t.muted }}>Device B holds:{'\n'}{toMarkdown(other.current)}</Text>}
      </ScrollView>
    </View>
  );
}
