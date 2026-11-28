// SPDX-License-Identifier: Apache-2.0
// The person's dock order (Settings > Appearance > Dock). The shipped order is each screen's `dock`
// position; `preferred` is the saved list of screen ids. Unknown ids are ignored and screens the list
// does not name keep their shipped place after it, so a new screen never disappears from the dock.
export function orderDock(shipped: readonly string[], preferred: readonly string[] | undefined): string[] {
  if (!preferred?.length) return [...shipped];
  const known = preferred.filter((id, i) => shipped.includes(id) && preferred.indexOf(id) === i);
  return [...known, ...shipped.filter((id) => !known.includes(id))];
}
