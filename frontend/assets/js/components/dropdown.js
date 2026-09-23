/**
 * Accessible menu-button dropdown (S3-5).
 *
 * The same ARIA menu contract as the export control: the trigger carries
 * aria-haspopup="menu" and manages aria-expanded; ArrowDown/Enter/Space open
 * the menu and move focus to the first item; Home/End/ArrowUp/ArrowDown move
 * focus; Escape closes and returns focus to the trigger; Tab/Escape and an
 * outside click dismiss the menu. Menu items are always present in the DOM so
 * their labels stay reachable by tests and assistive technology, while the
 * CSS (.dropdown__menu) hides the panel until opened.
 */

import { el } from "../utils/dom.js";

/**
 * @param {HTMLElement} container — receives `.dropdown` wrapper
 * @param {object} opts
 * @param {string} opts.label     — visible trigger label (and accessible name)
 * @param {Array<{label:string, onClick?:Function, danger?:boolean, disabled?:boolean}>} opts.items
 */
export function renderMenuButton(container, { label, items = [] }) {
  const menu = el("div", { className: "dropdown__menu", role: "menu" });
  for (const item of items) {
    menu.appendChild(
      el("button", {
        className: "dropdown-item" + (item.danger ? " dropdown-item--danger" : ""),
        role: "menuitem",
        type: "button",
        disabled: item.disabled ? "disabled" : null,
        onClick: () => { setOpen(false); if (item.onClick) item.onClick(); },
      }, item.label),
    );
  }

  const button = el("button", {
    className: "btn btn-secondary btn-sm",
    type: "button",
    "aria-haspopup": "menu",
    "aria-expanded": "false",
    "aria-label": label,
    title: label,
    onClick: (e) => {
      e.stopPropagation();
      setOpen(!menu.classList.contains("is-open"));
    },
  }, label);

  container.appendChild(el("div", { className: "dropdown" }, button, menu));

  const menuItems = () => Array.from(menu.querySelectorAll('[role="menuitem"]'));
  const setOpen = (open, { focusFirst = false, restoreFocus = false } = {}) => {
    menu.classList.toggle("is-open", open);
    button.setAttribute("aria-expanded", String(open));
    if (open && focusFirst && menuItems()[0]) menuItems()[0].focus();
    if (!open && restoreFocus) button.focus();
  };
  const moveFocus = (dir) => {
    const list = menuItems();
    if (!list.length) return;
    const cur = list.findIndex((node) => node === document.activeElement);
    const next = cur === -1 ? (dir > 0 ? 0 : list.length - 1) : (cur + dir + list.length) % list.length;
    list[next].focus();
  };

  button.addEventListener("keydown", (e) => {
    const open = menu.classList.contains("is-open");
    if (e.key === "Escape") {
      if (open) {
        e.preventDefault();
        e.stopPropagation();
        setOpen(false, { restoreFocus: true });
      }
      return;
    }
    if (open) return;
    if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setOpen(true, { focusFirst: true });
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      const list = menuItems();
      if (list.length) list[list.length - 1].focus();
    }
  });

  menu.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      setOpen(false, { restoreFocus: true });
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      moveFocus(e.key === "ArrowDown" ? 1 : -1);
    } else if (e.key === "Home" || e.key === "End") {
      e.preventDefault();
      const list = menuItems();
      if (!list.length) return;
      (e.key === "Home" ? list[0] : list[list.length - 1]).focus();
    } else if (e.key === "Tab") {
      setOpen(false);
    }
  });

  document.addEventListener("click", (e) => {
    if (menu.classList.contains("is-open") && !menu.contains(e.target) && e.target !== button && !button.contains(e.target)) {
      setOpen(false);
    }
  });
}