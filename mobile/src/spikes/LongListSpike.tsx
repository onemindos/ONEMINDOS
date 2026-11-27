// SPDX-License-Identifier: Apache-2.0
// Spike 3 (D-032): do 10,000 rows scroll smoothly on a phone? Rows are generated on the device, because
// this screen measures list performance only; it reads and writes nothing on the box. Reachable only
// through spikesEnabled() (a dev build, or EXPO_PUBLIC_ONEMIND_SPIKES=1 at build time).
import { FlashList } from '@shopify/flash-list';
import { memo, useCallback, useDeferredValue, useMemo, useState } from 'react';
import { FlatList, Pressable, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { font, space, useTheme } from '../ui/theme';

export const ROW_COUNT = 10_000;
const ROW_HEIGHT = 64;

export function spikesEnabled(): boolean {
  return __DEV__ || process.env.EXPO_PUBLIC_ONEMIND_SPIKES === '1';
}

export interface SpikeRow {
  id: number;
  title: string;
  subtitle: string;
  date: string;
  /** Lower-case text the search box matches against. */
  hay: string;
}

const TOPICS = ['Reminder', 'Note', 'File', 'Photo', 'Receipt', 'Recipe', 'Invoice', 'Plan'];
const PLACES = ['kitchen', 'garage', 'garden', 'office', 'school', 'trip', 'boiler', 'backup'];

/** Deterministic rows (same list every run, so two runs compare). */
export function makeRows(n: number = ROW_COUNT): SpikeRow[] {
  const rows: SpikeRow[] = [];
  for (let i = 0; i < n; i++) {
    const title = `${TOPICS[i % TOPICS.length]} ${i + 1}`;
    const subtitle = `About the ${PLACES[(i * 7) % PLACES.length]}, item ${(i * 31) % 997}`;
    const day = new Date(Date.UTC(2024, 0, 1) + i * 3_600_000 * 7);
    const date = day.toISOString().slice(0, 10);
    rows.push({ id: i, title, subtitle, date, hay: `${title} ${subtitle} ${date}`.toLowerCase() });
  }
  return rows;
}

export function filterRows(rows: SpikeRow[], query: string): SpikeRow[] {
  const q = query.trim().toLowerCase();
  return q ? rows.filter((r) => r.hay.includes(q)) : rows;
}

const Row = memo(function Row({ row, checked, onToggle }: { row: SpikeRow; checked: boolean; onToggle: (id: number) => void }) {
  const t = useTheme();
  return (
    <Pressable
      testID={`spike-row-${row.id}`}
      accessibilityRole="checkbox"
      accessibilityState={{ checked }}
      accessibilityLabel={row.title}
      onPress={() => onToggle(row.id)}
      style={{ height: ROW_HEIGHT, flexDirection: 'row', alignItems: 'center', gap: space.md, paddingHorizontal: space.lg }}
    >
      <View style={{ width: 24, height: 24, borderRadius: 6, borderWidth: 2, borderColor: t.muted, alignItems: 'center', justifyContent: 'center' }}>
        {checked ? <Text style={{ color: t.text, fontSize: font.sm }}>✓</Text> : null}
      </View>
      <View style={{ flex: 1 }}>
        <Text numberOfLines={1} style={{ color: t.text, fontSize: font.md, fontWeight: font.semibold }}>{row.title}</Text>
        <Text numberOfLines={1} style={{ color: t.muted, fontSize: font.sm }}>{row.subtitle}</Text>
      </View>
      <Text style={{ color: t.muted, fontSize: font.sm }}>{row.date}</Text>
    </Pressable>
  );
});

type Engine = 'flatlist' | 'flashlist';

export function LongListSpike() {
  const t = useTheme();
  const [engine, setEngine] = useState<Engine>('flashlist');
  const [query, setQuery] = useState('');
  const [checked, setChecked] = useState<ReadonlySet<number>>(() => new Set());
  const rows = useMemo(() => makeRows(), []);
  const deferred = useDeferredValue(query);
  const shown = useMemo(() => filterRows(rows, deferred), [rows, deferred]);
  const toggle = useCallback(
    (id: number) =>
      setChecked((prev) => {
        const next = new Set(prev);
        if (!next.delete(id)) next.add(id);
        return next;
      }),
    [],
  );
  const renderItem = useCallback(({ item }: { item: SpikeRow }) => <Row row={item} checked={checked.has(item.id)} onToggle={toggle} />, [checked, toggle]);
  const keyExtractor = useCallback((r: SpikeRow) => String(r.id), []);

  return (
    <SafeAreaView edges={['bottom']} style={{ flex: 1 }} testID="long-list-spike">
      <View style={{ padding: space.lg, gap: space.sm }}>
        <View style={{ flexDirection: 'row', gap: space.sm }}>
          {(['flatlist', 'flashlist'] as const).map((e) => (
            <Pressable
              key={e}
              testID={`spike-engine-${e}`}
              accessibilityRole="button"
              accessibilityState={{ selected: engine === e }}
              onPress={() => setEngine(e)}
              style={{ flex: 1, padding: space.md, borderRadius: 8, borderWidth: 1, borderColor: t.muted, opacity: engine === e ? 1 : 0.5 }}
            >
              <Text style={{ color: t.text, textAlign: 'center', fontWeight: font.semibold }}>{e === 'flatlist' ? 'FlatList' : 'FlashList'}</Text>
            </Pressable>
          ))}
        </View>
        <TextInput
          testID="spike-search"
          value={query}
          onChangeText={setQuery}
          placeholder="Search 10,000 rows"
          placeholderTextColor={t.muted}
          autoCorrect={false}
          autoCapitalize="none"
          style={{ color: t.text, borderWidth: 1, borderColor: t.muted, borderRadius: 8, padding: space.md }}
        />
        <Text testID="spike-count" style={{ color: t.muted, fontSize: font.sm }}>
          {shown.length} of {rows.length} rows · {checked.size} checked · {engine === 'flatlist' ? 'FlatList' : 'FlashList'}
        </Text>
      </View>
      {engine === 'flatlist' ? (
        <FlatList
          testID="spike-flatlist"
          data={shown}
          extraData={checked}
          renderItem={renderItem}
          keyExtractor={keyExtractor}
          getItemLayout={(_, index) => ({ length: ROW_HEIGHT, offset: ROW_HEIGHT * index, index })}
          initialNumToRender={12}
          windowSize={7}
          keyboardShouldPersistTaps="handled"
        />
      ) : (
        <FlashList
          testID="spike-flashlist"
          data={shown}
          extraData={checked}
          renderItem={renderItem}
          keyExtractor={keyExtractor}
          keyboardShouldPersistTaps="handled"
        />
      )}
    </SafeAreaView>
  );
}
