// SPDX-License-Identifier: Apache-2.0
// Data table with a real <caption>, sortable headers (aria-sort) and an empty state.
// Below the compact breakpoint each row becomes a stacked card, labelled from data-label.
import { useMemo, useState, type ReactNode } from 'react';
import { cx } from '../lib/cx';

export interface Column<T> {
  key: string;
  header: string;
  /** Cell content; default String(row[key]). */
  render?: (row: T) => ReactNode;
  /** Value used for sorting; enables sorting on this column. */
  sortValue?: (row: T) => string | number;
  align?: 'start' | 'end';
  /** Hide on compact screens (secondary detail). */
  secondary?: boolean;
}

export interface TableProps<T> {
  caption: string;
  /** Visually hide the caption when a heading already says it. */
  hideCaption?: boolean;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  empty?: ReactNode;
  initialSort?: { key: string; dir: 'asc' | 'desc' };
}

export function Table<T>({ caption, hideCaption, columns, rows, rowKey, empty, initialSort }: TableProps<T>) {
  const [sort, setSort] = useState(initialSort);
  const sorted = useMemo(() => {
    const col = sort && columns.find((c) => c.key === sort.key);
    if (!col?.sortValue) return rows;
    const get = col.sortValue;
    const out = [...rows].sort((a, b) => {
      const x = get(a);
      const y = get(b);
      return x < y ? -1 : x > y ? 1 : 0;
    });
    return sort!.dir === 'desc' ? out.reverse() : out;
  }, [rows, columns, sort]);

  if (rows.length === 0 && empty) {
    return (
      <div className="om-table-wrap">
        <p className={hideCaption ? 'om-visually-hidden' : 'om-table-caption'}>{caption}</p>
        {empty}
      </div>
    );
  }

  return (
    <div className="om-table-wrap">
      <table className="om-table">
        <caption className={hideCaption ? 'om-visually-hidden' : 'om-table-caption'}>{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => {
              const active = sort?.key === c.key;
              const ariaSort = active ? (sort!.dir === 'asc' ? 'ascending' : 'descending') : c.sortValue ? 'none' : undefined;
              return (
                <th key={c.key} scope="col" aria-sort={ariaSort} className={cx(c.align === 'end' && 'om-end', c.secondary && 'om-secondary')}>
                  {c.sortValue ? (
                    <button
                      type="button"
                      className="om-sort"
                      onClick={() => setSort({ key: c.key, dir: active && sort!.dir === 'asc' ? 'desc' : 'asc' })}
                    >
                      {c.header}
                      <span aria-hidden="true" className="om-sort-mark">
                        {active ? (sort!.dir === 'asc' ? '▲' : '▼') : '↕'}
                      </span>
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((c) => (
                <td key={c.key} data-label={c.header} className={cx(c.align === 'end' && 'om-end', c.secondary && 'om-secondary')}>
                  {c.render ? c.render(row) : String((row as Record<string, unknown>)[c.key] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
