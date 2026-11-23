// SPDX-License-Identifier: Apache-2.0
import { Dialog } from '@onemind/ui';
import { KEYMAP, type Group } from './keymap';

const GROUPS: Group[] = ['Open', 'Windows', 'Workspaces', 'Tiling', 'Help'];

/** Every entry of the keymap, grouped. Opens with "?" and from Launchpad. */
export function ShortcutSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Dialog open={open} onClose={onClose} title="Keyboard shortcuts" description="Shortcuts pause while you type in a field." size="md">
      {GROUPS.map(group => (
        <section key={group} aria-label={group}>
          <h3 className="wm-keys-head">{group}</h3>
          <dl className="wm-keys">
            {KEYMAP.filter(entry => entry.group === group).map(entry => (
              <div key={entry.id} className="wm-keys-row">
                <dt>{entry.description}</dt>
                <dd><kbd>{entry.keys}</kbd></dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </Dialog>
  );
}
