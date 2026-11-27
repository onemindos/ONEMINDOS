// SPDX-License-Identifier: Apache-2.0
// The page the WebView shows: our own bundled script, no network. The CSP forbids every outside request.
export type EditorColors = { bg: string; fg: string; accent: string; border: string };

const BUTTONS: [string, string][] = [['bold', 'B'], ['italic', 'I'], ['h1', 'H1'], ['h2', 'H2'], ['bullet', '•'], ['task', '☑'], ['done', 'Tick'], ['undo', '↶'], ['redo', '↷']];

export function editorHtml(js: string, c: EditorColors): string {
  const buttons = BUTTONS.map(([n, l]) => `<button data-cmd="${n}" aria-label="${n}">${l}</button>`).join('');
  return `<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<style>
body{margin:0;background:${c.bg};color:${c.fg};font:17px/1.45 sans-serif}
#bar{position:sticky;top:0;display:flex;gap:6px;padding:6px;background:${c.bg};border-bottom:1px solid ${c.border};overflow-x:auto}
button{min-width:44px;min-height:44px;border:1px solid ${c.border};border-radius:8px;background:transparent;color:${c.fg};font-size:16px}
#editor{padding:12px}.ProseMirror{outline:none;min-height:60vh}
li[data-task]{list-style:none;position:relative}li[data-task]::before{content:'\\2610';position:absolute;left:-1.6em;font-size:1.2em;color:${c.accent}}
li[data-checked="1"]::before{content:'\\2611'}li[data-checked="1"]>p{text-decoration:line-through;opacity:.6}
ul[data-tasks]{padding-left:1.8em}
</style></head><body><div id="bar">${buttons}</div><div id="editor"></div>
<script>${js.replace(/<\/script/gi, '<\\/script')}</script></body></html>`;
}
