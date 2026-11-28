// SPDX-License-Identifier: Apache-2.0
// Atlas Market (04): "Bring your own". Custom apps are first-class (founder 2026-11-25, D-026): the
// ways onto the box that exist today, each on Discover next to the catalog. Every one only files a
// request; the owner approves it in Approvals like a Market app (D-027). Commands are the real
// `onemind` ones; a way with no command says so instead of showing one that does not exist.
import { Icon, type IconName } from '@onemind/ui';
import { href } from '../../shell/routes';
import './market.css';

interface Way { title: string; body: string; to: string; icon: IconName; command?: string; open: string }

export const WAYS: Way[] = [
  {
    title: 'A container image',
    body: 'Put the image in a Compose file with one service. OneMind converts it and checks it against the install rules before anything runs.',
    to: href.compose,
    icon: 'apps',
    open: 'Import a Compose file',
  },
  {
    title: 'A Compose file',
    body: 'Paste a compose.yaml. OneMind turns it into an app folder and lists what it refuses; nothing is installed. Deploy the folder from Git.',
    to: href.compose,
    icon: 'storage',
    open: 'Import a Compose file',
  },
  {
    title: 'A Git repository',
    body: 'Point at a repository and a ref with an onemind.app.yaml. Every revision is kept, so you can roll back.',
    to: href.custom,
    icon: 'link',
    command: 'onemind app deploy --git URL --ref REF',
    open: 'Deploy from Git',
  },
  {
    title: 'A plugin',
    body: 'Adds a map layer, a Home tile, a Settings panel or commands, in its own slot. Plugins come from a source you trust.',
    to: `${href.market}?plugins=1`,
    icon: 'plus',
    command: 'onemind plugins list',
    open: 'Show plugins',
  },
];

export function BringYourOwn() {
  return (
    <section className="dash-mkt-byo" aria-labelledby="dash-mkt-byo-title">
      <h2 id="dash-mkt-byo-title" className="dash-mkt-byo-title">
        Bring your own <span className="om-hint">anything that runs in a container; it still asks before it touches your things</span>
      </h2>
      <ul className="dash-mkt-byo-grid">
        {WAYS.map((w) => (
          <li key={w.title} className="dash-mkt-byo-card">
            <span className="dash-mkt-byo-icon"><Icon name={w.icon} size={22} /></span>
            <div>
              <h3><a href={w.to}>{w.title}<span className="om-visually-hidden">: {w.open}</span></a></h3>
              <p>{w.body}</p>
              {w.command ? <code>$ {w.command}</code> : <p className="om-hint">From this screen only, for now.</p>}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
