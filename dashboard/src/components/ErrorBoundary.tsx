import { Component, type ReactNode } from 'react';

/**
 * Last line of defence: if a hub response the client accepted still breaks a
 * screen, show a note instead of a blank page.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="page">
        <p className="note note-error" role="alert">
          Could not read the hub's response. Check that this page is served by the OneMind hub, then{' '}
          <button type="button" className="btn btn-ghost" onClick={() => window.location.reload()}>
            reload
          </button>
          .
        </p>
      </main>
    );
  }
}
