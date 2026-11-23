// SPDX-License-Identifier: Apache-2.0
// A person's own Simple or Pro choice (#841). It can only narrow what the role already allows:
// roles.ts still decides Pro (owner, adult), so a guest, child or teen can never pick Pro, and a
// Pro role may choose the Simple screens for itself. Stored in the person's browser slot only.
import { useCallback, useMemo, useState } from 'react';
import { personStorage } from '../../data/prefs';
import type { View } from '../roles';

export type ViewChoice = 'auto' | 'simple';
const KEY = 'shell.view';

export function parseViewChoice(raw: string | null | undefined): ViewChoice {
  return raw === 'simple' ? 'simple' : 'auto';
}

/** The view to show: the role's, narrowed to Simple when the person chose it. Never widens. */
export function effectiveView(roleView: View, choice: ViewChoice): View {
  return roleView === 'pro' && choice === 'simple' ? 'simple' : roleView;
}

export function viewChoiceStore(personId: string, base?: Storage | null) {
  const s = base === undefined ? personStorage(personId) : personStorage(personId, base);
  return {
    load(): ViewChoice {
      try {
        return parseViewChoice(s?.getItem(KEY));
      } catch {
        return 'auto';
      }
    },
    save(c: ViewChoice): void {
      try {
        s?.setItem(KEY, c);
      } catch {
        // not saved; the choice still applies until reload
      }
    },
  };
}

export function useViewChoice(personId: string): [ViewChoice, (c: ViewChoice) => void] {
  const store = useMemo(() => viewChoiceStore(personId), [personId]);
  const [choice, setChoice] = useState<ViewChoice>(() => store.load());
  const set = useCallback(
    (c: ViewChoice) => {
      setChoice(c);
      store.save(c);
    },
    [store],
  );
  return [choice, set];
}
