// SPDX-License-Identifier: Apache-2.0
import { useSyncExternalStore } from 'react';

const query = '(prefers-reduced-motion: reduce)';

function prefersReducedMotion() {
  const pref = document.documentElement.dataset.omMotion;
  return pref === 'reduce' || (pref !== 'allow' && (window.matchMedia?.(query).matches ?? false));
}

function subscribe(onChange: () => void) {
  const media = window.matchMedia?.(query);
  media?.addEventListener('change', onChange);
  const profile = new MutationObserver(onChange);
  profile.observe(document.documentElement, { attributes: true, attributeFilter: ['data-om-motion'] });
  return () => {
    media?.removeEventListener('change', onChange);
    profile.disconnect();
  };
}

export function useReducedMotion(override?: boolean) {
  const system = useSyncExternalStore(subscribe, prefersReducedMotion, () => false);
  return override ?? system;
}

const registries = new WeakMap<Document, Set<Animation>>();

function track(document: Document, animation: Animation) {
  let active = registries.get(document);
  if (!active) {
    const animations = new Set<Animation>();
    const finishOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') animations.forEach((pending) => pending.finish());
    };
    document.addEventListener('keydown', finishOnEscape);
    registries.set(document, animations);
    active = animations;
  }
  active.add(animation);
  const finish = () => active.delete(animation);
  void animation.finished.then(finish, finish);
}

/** Finish finite presentation animations on Escape. A hold is always handled by its own control. */
export function animate(element: Element, frames: Keyframe[], options: KeyframeAnimationOptions & { hold?: boolean }, reduced = prefersReducedMotion()) {
  if (typeof element.animate !== 'function') return;
  const { hold, ...timing } = options;
  const animation = reduced
    ? element.animate([{ opacity: frames[0]?.opacity ?? 0 }, { opacity: frames.at(-1)?.opacity ?? 1 }], { duration: 160, delay: 0 })
    : element.animate(frames, timing);
  if (!hold && timing.iterations !== Infinity && timing.duration !== Infinity) track(element.ownerDocument, animation);
  return animation;
}
