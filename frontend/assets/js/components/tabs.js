/**
 * Tab bar component. Takes a container and an array of { id, label } and
 * calls onSelect(id) on change.
 *
 * Implements the WAI-ARIA tabs pattern (role=tablist/tab/tabpanel,
 * aria-selected, roving tabindex, Left/Right/Home/End keyboard navigation)
 * so assistive technology exposes the switches as tabs, not plain buttons.
 */

import { el, clear } from "../utils/dom.js";

const triggerId = (id) => `eis-tab--${id}`;
const panelId = (id) => `eis-tab-panel--${id}`;

/** id of the tab trigger for `id`; expose for aria-labelledby wiring. */
export function tabTriggerId(id) {
  return triggerId(id);
}

/** id of the matching tab panel; expose for aria-controls/aria-labelledby. */
export function tabPanelId(id) {
  return panelId(id);
}

/**
 * Render a tabs bar into `container` and invoke `onSelect(id)` when the
 * user selects a tab (pointer or keyboard). Returns a `setActive(id)`
 * updater function.
 *
 * @param {object} [opts] — { label: name for the tablist (aria-label) }
 */
export function renderTabs(container, tabs, onSelect, activeId, opts = {}) {
  clear(container);
  const bar = el("div", { className: "tabs", role: "tablist" });
  if (opts.label) bar.setAttribute("aria-label", opts.label);
  const idMap = {};

  for (const tab of tabs) {
    const isActive = tab.id === activeId;
    const btn = el("button", {
      className: "tab" + (isActive ? " is-active" : ""),
      role: "tab",
      type: "button",
      id: triggerId(tab.id),
      "aria-selected": String(isActive),
      "aria-controls": panelId(tab.id),
      tabindex: isActive ? "0" : "-1",
      dataset: { tab: tab.id },
    }, tab.label);
    btn.addEventListener("click", () => setActive(tab.id));
    btn.addEventListener("keydown", (e) => onTabKeydown(e, tab.id));
    idMap[tab.id] = btn;
    bar.appendChild(btn);
  }

  container.appendChild(bar);

  /** Move within the roving tabindex: previous/next/first/last + activate. */
  function onTabKeydown(e, id) {
    const order = tabs.map((t) => t.id);
    const idx = order.indexOf(id);
    if (idx === -1) return;

    let next = null;
    switch (e.key) {
      case "ArrowLeft": next = order[(idx - 1 + order.length) % order.length]; break;
      case "ArrowRight": next = order[(idx + 1) % order.length]; break;
      case "Home": next = order[0]; break;
      case "End": next = order[order.length - 1]; break;
      default: return;
    }
    e.preventDefault();
    setActive(next);
    idMap[next].focus();
  }

  function setActive(id) {
    for (const [tid, btn] of Object.entries(idMap)) {
      const on = tid === id;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-selected", String(on));
      btn.setAttribute("tabindex", on ? "0" : "-1");
    }
    onSelect(id);
  }

  return { setActive };
}