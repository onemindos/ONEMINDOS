// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from 'react';
import { Icon, type IconName } from './Icon';

export interface EmptyStateProps {
  icon?: IconName;
  title: string;
  /** Say why it is empty and what happens next; never a bare "No data". */
  children?: ReactNode;
  action?: ReactNode;
  /** The CLI line that does the same thing (headless-first, PRINCIPLES P4). */
  command?: string;
}

export function EmptyState({ icon = 'info', title, children, action, command }: EmptyStateProps) {
  return (
    <div className="om-empty" role="note">
      <span className="om-empty-icon">
        <Icon name={icon} size={28} />
      </span>
      <p className="om-empty-title">{title}</p>
      {children && <div className="om-empty-body">{children}</div>}
      {command && (
        <p className="om-empty-cmd">
          <span className="om-visually-hidden">Or from a terminal: </span>
          <code>{command}</code>
        </p>
      )}
      {action && <div className="om-empty-action">{action}</div>}
    </div>
  );
}
