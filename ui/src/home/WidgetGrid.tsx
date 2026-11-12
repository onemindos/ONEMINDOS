// SPDX-License-Identifier: Apache-2.0
// The widget grid. In edit mode each widget can be dragged, moved with buttons or arrow
// keys, resized (S/M/L) and removed. Every change goes through layout.ts and is announced
// in a polite live region, so it works without a mouse and with a screen reader.
import { useState, type DragEvent, type KeyboardEvent } from 'react';
import { Icon } from '../components/Icon';
import { cx } from '../lib/cx';
import { SIZE_LABEL, WIDGET_SIZES, isLocked, moveWidget, removeWidget, resizeWidget, type HomeLayout, type WidgetInstance } from './layout';
import { renderWidget, widgetName, type WidgetContext } from './widgets';

export interface WidgetGridProps {
  layout: HomeLayout;
  onChange: (next: HomeLayout, announce: string) => void;
  editing: boolean;
  ctx: WidgetContext;
}

function EditBar({ w, index, count, name, layout, onChange }: { w: WidgetInstance; index: number; count: number; name: string; layout: HomeLayout; onChange: WidgetGridProps['onChange'] }) {
  const locked = isLocked(w);
  const firstMovable = layout.widgets[0] && isLocked(layout.widgets[0]) ? 1 : 0;
  const move = (to: number) => onChange(moveWidget(layout, w.id, to), `${name} moved to position ${Math.max(firstMovable, Math.min(count - 1, to)) + 1} of ${count}.`);
  const onKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (locked) return;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      move(index - 1);
    } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      move(index + 1);
    }
  };
  return (
    <div className="omh-editbar">
      {locked ? (
        <span className="omh-locked">
          <Icon name="lock" size={14} /> Always first
        </span>
      ) : (
        <>
          <button type="button" className="omh-handle" aria-label={`Move ${name}. Use arrow keys, or drag.`} onKeyDown={onKey}>
            <span aria-hidden="true" className="omh-grip" />
          </button>
          <button type="button" className="omh-ibtn" aria-label={`Move ${name} earlier`} disabled={index <= firstMovable} onClick={() => move(index - 1)}>
            <Icon name="chevron" size={16} className="omh-flip" />
          </button>
          <button type="button" className="omh-ibtn" aria-label={`Move ${name} later`} disabled={index >= count - 1} onClick={() => move(index + 1)}>
            <Icon name="chevron" size={16} />
          </button>
        </>
      )}
      <fieldset className="omh-sizes">
        <legend className="om-visually-hidden">Size of {name}</legend>
        {WIDGET_SIZES.map((s) => (
          <label key={s} className={cx(w.size === s && 'omh-size-on')} title={SIZE_LABEL[s]}>
            <input type="radio" name={`size-${w.id}`} value={s} checked={w.size === s} onChange={() => onChange(resizeWidget(layout, w.id, s), `${name} is now ${SIZE_LABEL[s].toLowerCase()}.`)} />
            <span aria-hidden="true">{s}</span>
            <span className="om-visually-hidden">{SIZE_LABEL[s]}</span>
          </label>
        ))}
      </fieldset>
      {!locked && (
        <button type="button" className="omh-ibtn omh-remove" aria-label={`Remove ${name} from Home`} onClick={() => onChange(removeWidget(layout, w.id), `${name} removed from Home.`)}>
          <Icon name="x" size={16} />
        </button>
      )}
    </div>
  );
}

export function WidgetGrid({ layout, onChange, editing, ctx }: WidgetGridProps) {
  const [dragId, setDragId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);
  const count = layout.widgets.length;

  const dropOn = (target: WidgetInstance, e: DragEvent) => {
    e.preventDefault();
    const id = dragId ?? e.dataTransfer.getData('text/plain');
    setDragId(null);
    setOverId(null);
    if (!id || id === target.id) return;
    const to = layout.widgets.findIndex((x) => x.id === target.id);
    const w = layout.widgets.find((x) => x.id === id);
    if (!w) return;
    const name = widgetName(w, ctx.data);
    const next = moveWidget(layout, id, to);
    if (next !== layout) onChange(next, `${name} moved to position ${next.widgets.findIndex((x) => x.id === id) + 1} of ${count}.`);
  };

  return (
    <ul className={cx('omh-grid', editing && 'omh-grid-editing')} aria-label="Widgets">
      {layout.widgets.map((w, i) => {
        const name = widgetName(w, ctx.data);
        const canDrag = editing && !isLocked(w);
        return (
          <li
            key={w.id}
            className={cx('omh-cell', `omh-cell-${w.size}`, dragId === w.id && 'omh-dragging', overId === w.id && dragId !== w.id && 'omh-drop')}
            draggable={canDrag}
            onDragStart={(e) => {
              if (!canDrag) return;
              setDragId(w.id);
              e.dataTransfer.effectAllowed = 'move';
              e.dataTransfer.setData('text/plain', w.id);
            }}
            onDragEnd={() => {
              setDragId(null);
              setOverId(null);
            }}
            onDragOver={(e) => {
              if (!editing || !dragId || isLocked(w)) return;
              e.preventDefault();
              if (overId !== w.id) setOverId(w.id);
            }}
            onDrop={(e) => editing && !isLocked(w) && dropOn(w, e)}
          >
            {editing && <EditBar w={w} index={i} count={count} name={name} layout={layout} onChange={onChange} />}
            {renderWidget(w, ctx)}
          </li>
        );
      })}
    </ul>
  );
}
