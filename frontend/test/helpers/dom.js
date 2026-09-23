/**
 * Minimal DOM/browser environment stubs for node:test. Not a browser — only
 * enough surface for the frontend modules to import and for the pure-logic
 * tests to run (element creation, events, localStorage, fetch, routing).
 */

class StubClassList {
  constructor() { this._set = new Set(); }
  add(...names) { for (const n of names) this._set.add(n); }
  remove(...names) { for (const n of names) this._set.delete(n); }
  toggle(name, force) {
    const want = force === undefined ? !this._set.has(name) : Boolean(force);
    if (want) this._set.add(name); else this._set.delete(name);
    return want;
  }
  contains(name) { return this._set.has(name); }
}

export class StubElement {
  constructor(tag) {
    this.nodeType = 1;
    this.tagName = tag.toUpperCase();
    this.childNodes = [];
    this.parentNode = null;
    this.attributes = new Map();
    this.style = {};
    this.dataset = {};
    this.classList = new StubClassList();
    this.listeners = {};
    this.value = "";
    this.textContent = "";
    this.href = "";
    this.disabled = false;
    this.selected = false;
    this.files = [];
    this.checked = false;
    this.id = "";
    this.title = "";
  }

  setAttribute(key, value) {
    this.attributes.set(key, String(value));
    if (key === "id") this.id = String(value);
    if (key === "value") this.value = String(value);
    if (key === "disabled") this.disabled = true;
    if (key === "class" || key === "className") this.className = String(value);
  }

  getAttribute(key) {
    return this.attributes.has(key) ? this.attributes.get(key) : null;
  }

  hasAttribute(key) { return this.attributes.has(key); }

  removeAttribute(key) { this.attributes.delete(key); }

  appendChild(child) {
    if (child === undefined || child === null) return child;
    if (typeof child === "string") child = new StubText(child);
    child.parentNode = this;
    this.childNodes.push(child);
    return child;
  }

  removeChild(child) {
    const idx = this.childNodes.indexOf(child);
    if (idx >= 0) this.childNodes.splice(idx, 1);
    if (child) child.parentNode = null;
    return child;
  }

  append(...children) {
    for (const child of children.flat(Infinity)) {
      if (child !== undefined && child !== null) this.appendChild(child);
    }
  }

  replaceChildren(...nodes) {
    this.childNodes = [];
    this.append(...nodes);
  }

  after(node) {
    if (node) {
      node.remove();
      const idx = this.parentNode ? this.parentNode.childNodes.indexOf(this) : -1;
      if (this.parentNode && idx >= 0) this.parentNode.childNodes.splice(idx + 1, 0, node);
    }
  }

  remove() {
    if (this.parentNode) {
      const idx = this.parentNode.childNodes.indexOf(this);
      if (idx >= 0) this.parentNode.childNodes.splice(idx, 1);
      this.parentNode = null;
    }
  }

  addEventListener(type, fn) {
    (this.listeners[type] ||= []).push(fn);
  }

  removeEventListener(type, fn) {
    const list = this.listeners[type] || [];
    const idx = list.indexOf(fn);
    if (idx >= 0) list.splice(idx, 1);
  }

  dispatchEvent(event) {
    const type = event.type || "click";
    (this.listeners[type] || []).forEach((fn) => fn.call(this, event));
  }

  contains(node) {
    for (let cur = node; cur; cur = cur.parentNode) {
      if (cur === this) return true;
    }
    return false;
  }
  closest() { return null; }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  querySelectorAll(selector) {
    const out = [];
    const visit = (node) => {
      for (const child of node.childNodes || []) {
        if (!child || child.nodeType === 3) continue;
        if (matchesSelector(child, selector)) out.push(child);
        visit(child);
      }
    };
    visit(this);
    return out;
  }
  get elements() { return this.querySelectorAll("*"); }
  focus() { globalThis.document.activeElement = this; }
  click() { this.dispatchEvent({ type: "click" }); }
  reset() { this.value = ""; }

  cloneNode(deep = false) {
    const clone = new StubElement(this.tagName);
    for (const [key, value] of this.attributes) clone.attributes.set(key, value);
    if (this.className) clone.className = this.className;
    for (const child of this.childNodes) {
      if (child.nodeType === 3) {
        clone.appendChild(new StubText(child.textContent));
      } else if (deep) {
        clone.appendChild(child.cloneNode(true));
      }
    }
    return clone;
  }

  get className() { return this.attributes.get("className") || this.attributes.get("class") || ""; }
  set className(v) {
    if (typeof v === "string") {
      this.attributes.set("class", v);
      this.attributes.set("className", v);
      this.classList._set = new Set(v.split(/\s+/).filter(Boolean));
    }
  }
}

/** Minimal selector matcher supporting "#id", ".class", "[attr=val]", tags and "*". */
function matchesSelector(node, selector) {
  const sel = String(selector).trim();
  if (sel === "*") return true;
  if (sel.startsWith("#")) return node.getAttribute("id") === sel.slice(1);
  if (sel.startsWith(".")) return node.classList && node.classList.contains(sel.slice(1));
  if (sel.startsWith("[")) {
    const m = /^\[([\w-]+)=?["']?([^"'\]]*)["']?\]$/.exec(sel);
    if (!m) return false;
    return String(node.getAttribute(m[1])) === m[2];
  }
  return (node.tagName || "").toLowerCase() === sel.toLowerCase();
}

export class StubText {
  constructor(text) { this.nodeType = 3; this.textContent = String(text); }
}

globalThis.Node = StubElement;

const documentStub = {
  createElement(tag) { return new StubElement(tag); },
  createTextNode(text) { return new StubText(text); },
  createDocumentFragment() { return new StubElement("#fragment"); },
  getElementById() { return null; },
  querySelector(selector) { return this.body.querySelector(selector); },
  querySelectorAll(selector) { return this.body.querySelectorAll(selector); },
  body: new StubElement("body"),
  documentElement: new StubElement("html"),
  activeElement: null,
  _docListeners: {},
  addEventListener(type, fn) { (this._docListeners[type] ||= []).push(fn); },
  removeEventListener(type, fn) {
    const list = this._docListeners[type] || [];
    const idx = list.indexOf(fn);
    if (idx >= 0) list.splice(idx, 1);
  },
  dispatchEvent(event) {
    const type = event.type || "keydown";
    (this._docListeners[type] || []).forEach((fn) => fn.call(this, event));
  },
};

globalThis.document = documentStub;

const storageMap = new Map();
globalThis.localStorage = {
  getItem(key) { return storageMap.has(key) ? storageMap.get(key) : null; },
  setItem(key, value) { storageMap.set(key, String(value)); },
  removeItem(key) { storageMap.delete(key); },
  clear() { storageMap.clear(); },
};

globalThis.window = globalThis;
globalThis.window.location = { search: "", href: "", hash: "" };
globalThis.__EIS_API_BASE__ = undefined;

globalThis.URL.createObjectURL = () => "blob:stub";
globalThis.URL.revokeObjectURL = () => {};

globalThis.FormData = class FormData {
  constructor() { this.entries = []; }
  append(k, v) { this.entries.push([k, v]); }
};