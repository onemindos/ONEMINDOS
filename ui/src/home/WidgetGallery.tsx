// SPDX-License-Identifier: Apache-2.0
// "Add a widget": OneMind's own widgets, one System widget per node, and the typed widgets
// each installed app declares in its manifest (PLUGIN-UI.md §5 `spec.ui.widgets`).
import type { ReactNode } from 'react';
import { Button } from '../components/Button';
import { Dialog } from '../components/Dialog';
import { Icon } from '../components/Icon';
import { addWidget, hasWidget, MAX_WIDGETS, type HomeLayout, type NewWidget } from './layout';
import { AppGlyph } from './parts';
import { categoryOf } from './taxonomy';
import type { HomeData } from './types';
import { WIDGET_META } from './widgets';

interface Option {
  key: string;
  title: string;
  blurb: string;
  glyph: ReactNode;
  widget: NewWidget;
}

export function galleryOptions(data: HomeData): { builtin: Option[]; apps: Option[] } {
  const builtin: Option[] = (['system', 'activity', 'backups', 'updates', 'mesh'] as const).map((k) => ({
    key: k,
    title: k === 'system' ? 'System, every node' : WIDGET_META[k].title,
    blurb: WIDGET_META[k].blurb,
    glyph: <Icon name={WIDGET_META[k].icon} size={20} />,
    widget: { kind: k, size: k === 'system' || k === 'activity' ? 'M' : 'S' },
  }));
  if (data.nodes.state === 'ready') {
    for (const n of data.nodes.data)
      builtin.push({
        key: `system:${n.node_id}`,
        title: `System, ${n.hostname}`,
        blurb: 'One node in detail: CPU, memory, storage, temperature, uptime.',
        glyph: <Icon name="nodes" size={20} />,
        widget: { kind: 'system', nodeId: n.node_id, size: 'M' },
      });
  }
  const apps: Option[] = [];
  if (data.apps.state === 'ready') {
    for (const a of data.apps.data.filter((x) => x.installed)) {
      for (const d of a.widgets ?? []) {
        apps.push({
          key: `app:${a.id}/${d.id}`,
          title: `${a.name} · ${d.title}`,
          blurb: `${categoryOf(a.category)?.name ?? 'App'} · ${d.template} widget, refreshes every ${d.source.refreshSeconds} s`,
          glyph: <AppGlyph app={a} size={28} />,
          widget: { kind: 'app', appId: a.id, widgetId: d.id, size: 'S' },
        });
      }
    }
  }
  return { builtin, apps };
}

export interface WidgetGalleryProps {
  open: boolean;
  onClose: () => void;
  data: HomeData;
  layout: HomeLayout;
  onAdd: (next: HomeLayout, announce: string) => void;
}

export function WidgetGallery({ open, onClose, data, layout, onAdd }: WidgetGalleryProps) {
  const { builtin, apps } = galleryOptions(data);
  const full = layout.widgets.length >= MAX_WIDGETS;
  const list = (opts: Option[]) => (
    <ul className="omh-gallery">
      {opts.map((o) => {
        const present = hasWidget(layout, o.widget);
        return (
          <li key={o.key}>
            <span className="omh-gallery-glyph">{o.glyph}</span>
            <span className="omh-gallery-text">
              <span className="omh-gallery-title">{o.title}</span>
              <span className="om-hint">{o.blurb}</span>
            </span>
            {present ? (
              <span className="omh-onhome">
                <Icon name="check" size={16} /> On Home
              </span>
            ) : (
              <Button size="sm" icon="plus" disabled={full} aria-label={`Add ${o.title}`} onClick={() => onAdd(addWidget(layout, o.widget), `${o.title} added at the end of Home.`)}>
                Add
              </Button>
            )}
          </li>
        );
      })}
    </ul>
  );
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add a widget"
      size="lg"
      description={full ? `Home holds up to ${MAX_WIDGETS} widgets. Remove one to add another.` : `${layout.widgets.length} of ${MAX_WIDGETS} widgets on Home. Your layout is saved for you only.`}
      actions={
        <Button variant="primary" onClick={onClose}>
          Done
        </Button>
      }
    >
      <h3 className="omh-gallery-head">From OneMind</h3>
      {list(builtin)}
      <h3 className="omh-gallery-head">From your apps</h3>
      {apps.length ? list(apps) : <p className="om-hint">None of your installed apps offers a widget yet. Apps declare widgets in their manifest.</p>}
    </Dialog>
  );
}
