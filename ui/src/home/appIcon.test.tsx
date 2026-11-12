// SPDX-License-Identifier: Apache-2.0
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

describe('AppIcon (CRITIQUE #20)', () => {
  it('is one tile for Home and the Store: same hue and monogram for the same app', async () => {
    const { AppIcon } = await import('../components/AppIcon');
    const { AppTile } = await import('../store/bits');
    const { AppGlyph } = await import('./parts');
    const app = { id: 'home-assistant', name: 'Home Assistant' };
    const { container } = render(
      <>
        <AppIcon app={app} size={40} />
        <AppTile app={app} size={40} />
        <AppGlyph app={app} size={40} />
      </>,
    );
    const tiles = container.querySelectorAll('.om-app-icon');
    expect(tiles).toHaveLength(3);
    const hues = new Set(Array.from(tiles, (t) => t.getAttribute('data-hue')));
    expect(hues.size).toBe(1);
    tiles.forEach((t) => expect(t).toHaveTextContent('HA'));
  });

  it('never loads a javascript: or protocol-relative icon', async () => {
    const { AppIcon } = await import('../components/AppIcon');
    const { container } = render(
      <>
        <AppIcon app={{ id: 'a', name: 'A', icon: 'javascript:alert(1)' }} />
        <AppIcon app={{ id: 'b', name: 'B', icon: '//evil.example/x.png' }} />
        <AppIcon app={{ id: 'c', name: 'C', icon: '/icons/c.png' }} />
      </>,
    );
    const imgs = container.querySelectorAll('img');
    expect(imgs).toHaveLength(1);
    expect(imgs[0]).toHaveAttribute('src', '/icons/c.png');
  });
});
