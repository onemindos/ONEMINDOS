// SPDX-License-Identifier: Apache-2.0
import type { UpdateNeeded as State } from '../lib/protocol';

/** Shown instead of every screen when the hub no longer serves this dashboard's protocol generation. */
export function UpdateNeeded({ state }: { state: State }) {
  return (
    <main className="dash-signin">
      <section className="om-note om-tone-warn" role="alert" aria-labelledby="update-needed-title">
        <h1 id="update-needed-title">Update needed</h1>
        <p>
          This copy of the dashboard speaks OneMind protocol {state.sent}. The hub now serves {state.min} to {state.max}, so it
          stopped answering this page rather than risk showing wrong data.
        </p>
        <p>Reload to get the dashboard the hub serves now. If this page was saved as an app, close and reopen it.</p>
        <button type="button" className="om-btn om-btn-primary" onClick={() => window.location.reload()}>
          Reload
        </button>
      </section>
    </main>
  );
}
