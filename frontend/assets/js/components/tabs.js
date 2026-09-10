/**
 * Tab bar component. Takes a container and an array of { id, label } and
 * calls onSelect(id) on change.
 */

import { el, clear } from "../utils/dom.js";

/**
 * Render a tabs bar into `container` and invoke `onSelect(id)` when the
 * user clicks a tab. Returns a `setActive(id)` updater function.
 */
export function renderTabs(container, tabs, onSelect, activeId) {
  clear(container);
  const bar = el("div", { className: "tabs" });
  const idMap = {};

  for (const tab of tabs) {
    const btn = el("button", {
      className: "tab" + (tab.id === activeId ? " is-active" : ""),
      dataset: { tab: tab.id },
    }, tab.label);
    btn.addEventListener("click", () => setActive(tab.id));
    idMap[tab.id] = btn;
    bar.appendChild(btn);
  }

  container.appendChild(bar);

  function setActive(id) {
    for (const [tid, btn] of Object.entries(idMap)) {
      btn.classList.toggle("is-active", tid === id);
    }
    onSelect(id);
  }

  return { setActive };
}