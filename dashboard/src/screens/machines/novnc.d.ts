// SPDX-License-Identifier: Apache-2.0
// Public API used from the unmodified MPL-2.0 package. Version 1.7 ships JavaScript only.
declare module '@novnc/novnc' {
  export default class RFB extends EventTarget {
    constructor(target: HTMLElement, channel: WebSocket);
    scaleViewport: boolean;
    viewOnly: boolean;
    disconnect(): void;
  }
}
