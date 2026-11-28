// SPDX-License-Identifier: Apache-2.0
// Settings > Appearance: the Dock and Home tiles lists. Dock order and labels are appearance
// preferences (the dock reads them); Home tiles use the person's Home layout, the same one the
// Home editor writes. Moving is by button, so it works by keyboard and screen reader.
import { useMemo, useState } from 'react';
import { Button, removeWidget as removeHomeWidget, moveWidget as moveHomeWidget, useCustomize, widgetName, type HomeData, type HomeLayout } from '@onemind/ui';
import { SCREENS, DOCK_ORDER } from '../screens/registry';
import { orderDock } from '../shell/dockOrder';
import { homeLayoutStore } from '../data/prefs';
import { dashboardHomeLayout } from './Home';
import { useSignedIn } from '../session';
import { showsNav } from '../shell/roles';
import { useShell } from '../shell/Shell';

const unknownData = { apps: { state: 'loading' }, nodes: { state: 'loading' } } as unknown as HomeData;

function Row({ label, note, index, last, locked, onMove, onRemove }: { label: string; note?: string; index: number; last: number; locked?: boolean; onMove: (to: number) => void; onRemove?: () => void }) {
  return (
    <li>
      <span>
        {label}
        {note && <small> · {note}</small>}
      </span>
      {locked ? (
        <small>always on</small>
      ) : (
        <>
          <Button size="sm" aria-label={`Move ${label} up`} disabled={index === 0} onClick={() => onMove(index - 1)}>Up</Button>
          <Button size="sm" aria-label={`Move ${label} down`} disabled={index === last} onClick={() => onMove(index + 1)}>Down</Button>
          {onRemove && <Button size="sm" aria-label={`Remove ${label} from Home`} onClick={onRemove}>Remove</Button>}
        </>
      )}
    </li>
  );
}

export function DockOrderSection() {
  const { prefs, update } = useCustomize();
  const order = useMemo(() => orderDock(DOCK_ORDER, prefs.dockOrder), [prefs.dockOrder]);
  const title = (id: string) => SCREENS.find((s) => s.id === id)?.title ?? id;
  const move = (from: number, to: number) => {
    const next = order.slice();
    const [id] = next.splice(from, 1);
    next.splice(to, 0, id!);
    update({ dockOrder: next });
  };
  return (
    <section className="om-cz-section" aria-labelledby="om-dock-h">
      <h2 id="om-dock-h" className="om-cz-section-title">Dock</h2>
      <ol className="om-cz-list" aria-label="Dock order">
        {order.map((id, i) => <Row key={id} label={title(id)} index={i} last={order.length - 1} onMove={(to) => move(i, to)} />)}
      </ol>
      <label className="om-cz-check">
        <input type="checkbox" role="switch" checked={prefs.dockLabels} onChange={(e) => update({ dockLabels: e.target.checked })} />
        <span>Labels under tiles</span>
      </label>
      {prefs.dockOrder.length > 0 && <Button size="sm" onClick={() => update({ dockOrder: [] })}>Reset dock order</Button>}
    </section>
  );
}

export function HomeTilesSection() {
  const { person } = useSignedIn();
  const shell = useShell();
  const store = useMemo(() => homeLayoutStore(), []);
  const pro = showsNav('nodes', shell.view);
  const [layout, setLayout] = useState<HomeLayout>(() => store.load(person) ?? dashboardHomeLayout(pro));
  const save = (next: HomeLayout) => {
    setLayout(next);
    store.save(person, next);
  };
  return (
    <section className="om-cz-section" aria-labelledby="om-tiles-h">
      <h2 id="om-tiles-h" className="om-cz-section-title">Home tiles</h2>
      <ol className="om-cz-list" aria-label="Home tiles">
        {layout.widgets.map((w, i) => (
          <Row
            key={w.id}
            label={widgetName(w, unknownData)}
            index={i}
            last={layout.widgets.length - 1}
            locked={i === 0 && w.kind === 'approvals'}
            onMove={(to) => save(moveHomeWidget(layout, w.id, to))}
            onRemove={() => save(removeHomeWidget(layout, w.id))}
          />
        ))}
      </ol>
      <p className="om-cz-desc">Add tiles, resize them and pin apps from Home, Edit.</p>
    </section>
  );
}
