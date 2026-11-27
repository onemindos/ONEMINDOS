// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from '@testing-library/react-native';
import '@shopify/flash-list/jestSetup';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { filterRows, LongListSpike, makeRows, ROW_COUNT, spikesEnabled } from './LongListSpike';

const metrics = { frame: { x: 0, y: 0, width: 360, height: 800 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } };
const ui = () => (
  <SafeAreaProvider initialMetrics={metrics}>
    <LongListSpike />
  </SafeAreaProvider>
);

describe('long list spike', () => {
  it('generates 10,000 distinct rows and filters them', () => {
    const rows = makeRows();
    expect(rows).toHaveLength(ROW_COUNT);
    expect(new Set(rows.map((r) => r.id)).size).toBe(ROW_COUNT);
    expect(filterRows(rows, '')).toHaveLength(ROW_COUNT);
    const hits = filterRows(rows, ' RECEIPT 10 ');
    expect(hits.length).toBeGreaterThan(0);
    expect(hits.length).toBeLessThan(ROW_COUNT);
    expect(hits.every((r) => r.title.toLowerCase().includes('receipt') || r.hay.includes('receipt 10'))).toBe(true);
    expect(filterRows(rows, 'no such text anywhere')).toHaveLength(0);
  });

  it('renders, filters live, toggles a checkbox and switches list engine', async () => {
    await render(ui());
    expect(screen.getByTestId('long-list-spike')).toBeTruthy();
    expect(screen.getByTestId('spike-count').props.children.join('')).toContain('10000 of 10000 rows');
    await fireEvent.changeText(screen.getByTestId('spike-search'), 'Reminder 1');
    expect(await screen.findByText(/of 10000 rows/)).toBeTruthy();
    const count = screen.getByTestId('spike-count').props.children.join('');
    expect(count).not.toContain('10000 of');
    await fireEvent.changeText(screen.getByTestId('spike-search'), 'zzzz');
    expect((await screen.findByTestId('spike-count')).props.children.join('')).toContain('0 of 10000');
    await fireEvent.changeText(screen.getByTestId('spike-search'), '');
    await fireEvent.press(screen.getByTestId('spike-engine-flatlist'));
    expect(await screen.findByTestId('spike-flatlist')).toBeTruthy();
    const first = await screen.findByTestId('spike-row-0');
    await fireEvent.press(first);
    expect(screen.getByTestId('spike-count').props.children.join('')).toContain('1 checked');
    await fireEvent.press(screen.getByTestId('spike-engine-flashlist'));
    expect(await screen.findByTestId('spike-flashlist')).toBeTruthy();
  });

  it('is on in a dev build and off in a release build without the flag', () => {
    const g = globalThis as { __DEV__?: boolean };
    const saved = g.__DEV__;
    try {
      g.__DEV__ = false;
      delete process.env.EXPO_PUBLIC_ONEMIND_SPIKES;
      expect(spikesEnabled()).toBe(false);
      process.env.EXPO_PUBLIC_ONEMIND_SPIKES = '1';
      expect(spikesEnabled()).toBe(true);
    } finally {
      g.__DEV__ = saved;
      delete process.env.EXPO_PUBLIC_ONEMIND_SPIKES;
    }
  });
});
