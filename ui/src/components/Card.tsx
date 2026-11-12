// SPDX-License-Identifier: Apache-2.0
import { useId, type ReactNode } from 'react';
import { cx } from '../lib/cx';

export interface CardProps {
  title?: ReactNode;
  /** Heading level of the title; default 2. */
  level?: 2 | 3 | 4;
  subtitle?: ReactNode;
  /** Right side of the header: a pill, a button or a menu. */
  aside?: ReactNode;
  footer?: ReactNode;
  /** `stale` draws the dashed "last report, not live" border (PRINCIPLES P2). */
  variant?: 'default' | 'stale' | 'attention' | 'sunken';
  className?: string;
  children?: ReactNode;
}

export function Card({ title, level = 2, subtitle, aside, footer, variant = 'default', className, children }: CardProps) {
  const id = useId();
  const H = `h${level}` as 'h2';
  return (
    <section className={cx('om-card', variant !== 'default' && `om-card-${variant}`, className)} aria-labelledby={title ? id : undefined}>
      {(title || aside) && (
        <header className="om-card-head">
          <div className="om-card-titles">
            {title && (
              <H id={id} className="om-card-title">
                {title}
              </H>
            )}
            {subtitle && <p className="om-card-subtitle">{subtitle}</p>}
          </div>
          {aside && <div className="om-card-aside">{aside}</div>}
        </header>
      )}
      {children !== undefined && <div className="om-card-body">{children}</div>}
      {footer && <footer className="om-card-foot">{footer}</footer>}
    </section>
  );
}
