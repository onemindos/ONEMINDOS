// SPDX-License-Identifier: Apache-2.0
// Demo of the Home launcher on fixtures. `#/home/<variant>` shows a state:
// edit, loading, offline, errors, fresh. Approve/Deny only change local demo state and say
// which API call the dashboard would make; nothing talks to a gateway.
import { useMemo, useState } from 'react';
import { useToast } from '../../../src/components/Toast';
import { equivalentCall, type ActionSummary } from '../../../src/components/ApprovalCard';
import { useOptionalCustomize } from '../../../src/customize/CustomizeProvider';
import { HomeScreen } from '../../../src/home/HomeScreen';
import { DEFAULT_LAYOUT, browserLayoutStore, type HomeLayout } from '../../../src/home/layout';
import type { HomeData } from '../../../src/home/types';
import { CommandPalette } from '../../../src/shell/CommandPalette';
import { buildCommands } from '../../../src/shell/palette';
import { NOW, PERSON, TIME_ZONE, demoLayout, errorData, freshData, homeData, loadingData, nodes, offlineData } from './fixtures';

const VARIANTS: Record<string, HomeData> = { loading: loadingData, offline: offlineData, errors: errorData, fresh: freshData };

export function HomeLauncher({ variant }: { variant?: string }) {
  const toast = useToast();
  const customize = useOptionalCustomize();
  const store = useMemo(() => browserLayoutStore(), []);
  const base = VARIANTS[variant ?? ''] ?? homeData;
  const [decided, setDecided] = useState<Set<string>>(() => new Set());
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [layout, setLayout] = useState<HomeLayout>(() => {
    if (variant === 'fresh') return DEFAULT_LAYOUT;
    return (variant ? null : store.load(PERSON.id)) ?? demoLayout;
  });

  const data: HomeData = base.approvals.state === 'ready' ? { ...base, approvals: { state: 'ready', data: base.approvals.data.filter((a) => !decided.has(a.id)) } } : base;
  const decide = (a: ActionSummary, d: 'approve' | 'deny') => {
    setDecided((s) => new Set(s).add(a.id));
    toast.show({ tone: d === 'approve' ? 'ok' : 'neutral', title: d === 'approve' ? 'Approved (demo)' : 'Denied (demo)', body: `The dashboard sends ${equivalentCall(a, d)}.` });
  };

  const commands = useMemo(
    () =>
      buildCommands({
        now: NOW,
        apps: (data.apps.state === 'ready' ? data.apps.data : []).map((a) => ({ id: a.id, name: a.name, category: a.category, tagline: a.description, installed: a.installed, status: a.status === 'updating' || a.status === 'unknown' ? undefined : a.status, deployClass: a.deploy_class, plugin: a.plugin, updateAvailable: a.update_available })),
        nodes,
        pending: data.approvals.state === 'ready' ? data.approvals.data : [],
        canApprove: true,
      }),
    [data.apps, data.approvals],
  );

  return (
    <>
      <HomeScreen
        data={data}
        now={NOW}
        timeZone={TIME_ZONE}
        personName={PERSON.name}
        layout={layout}
        onLayoutChange={(next) => {
          setLayout(next);
          store.save(PERSON.id, next);
        }}
        wallpaper={customize && customize.prefs.wallpaper !== 'none' ? 'host' : 'tide'}
        canDecide={{ allowed: true }}
        onApprove={(a) => decide(a, 'approve')}
        onDeny={(a) => decide(a, 'deny')}
        onOpenSearch={() => setPaletteOpen(true)}
        initialEditing={variant === 'edit'}
      />
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        commands={commands}
        onRun={(cmd) => {
          setPaletteOpen(false);
          if (cmd.href) window.location.hash = cmd.href.replace(/^#/, '');
          else if (cmd.request) toast.show({ tone: 'info', title: 'Request created (demo)', body: `${cmd.title}. It waits in Approvals.` });
        }}
      />
    </>
  );
}
