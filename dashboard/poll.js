// The desk's live refresh (#411; option 2 of #396). live.py fills in the settings and inlines
// this at build time; the page's CSP allows only this script, by hash. It reads same-origin
// state.json and nothing else, and builds DOM nodes from its node trees with createElement,
// setAttribute and text nodes; it never parses HTML or runs strings as code. With JavaScript
// off the static page is unchanged.
(function () {
  "use strict";
  var ALLOW = /*ALLOW*/null, SAFE_URL = /*SAFE_URL*/null;
  var EVERY = /*EVERY*/0, STALE = /*STALE*/0;
  var SVG = "http://www.w3.org/2000/svg";
  var body = document.body, builtAt = body.getAttribute("data-built-at");

  function has(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }

  // A node is a string (text) or [tag, {attr: value}, child, ...].
  function node(n, inSvg) {
    if (typeof n === "string") { return document.createTextNode(n); }
    if (!Array.isArray(n) || typeof n[0] !== "string") { throw new Error("bad node"); }
    var tag = n[0], attrs = n[1] || {}, svg = inSvg || tag === "svg", el, k, i;
    if (!has(svg ? ALLOW.svg : ALLOW.tags, tag)) { throw new Error("tag " + tag); }
    el = svg ? document.createElementNS(SVG, tag) : document.createElement(tag);
    for (k in attrs) {
      if (!has(attrs, k)) { continue; }
      if (!has(ALLOW.attrs, k) || typeof attrs[k] !== "string" ||
          (k === "href" && !SAFE_URL.test(attrs[k]))) { throw new Error("attr " + k); }
      el.setAttribute(k, attrs[k]);
    }
    for (i = 2; i < n.length; i++) { el.appendChild(node(n[i], svg)); }
    return el;
  }

  // Build the whole panel first, so a bad node leaves it as it was.
  function fill(el, nodes) {
    var frag = document.createDocumentFragment(), i;
    for (i = 0; i < nodes.length; i++) { frag.appendChild(node(nodes[i], false)); }
    while (el.firstChild) { el.removeChild(el.firstChild); }
    el.appendChild(frag);
  }

  // Grey the LIVE mark (#402) once the data on screen is older than STALE.
  function fresh() {
    var old = !(Date.now() - Date.parse(builtAt) <= STALE);
    var marks = document.querySelectorAll("header.mast .live"), i;
    for (i = 0; i < marks.length; i++) { marks[i].classList.toggle("stale", old); }
  }

  function apply(s) {
    if (!s || s.schema !== 1 || typeof s.built_at !== "string" || !s.desk) { return; }
    // Pages' cache can serve a state.json older than the page; only ever move forward.
    if (!(Date.parse(s.built_at) > Date.parse(builtAt))) { return; }
    var panels = document.querySelectorAll("[data-panel]"), i, t;
    for (i = 0; i < panels.length; i++) {
      t = s.desk[panels[i].getAttribute("data-panel")];
      if (Array.isArray(t)) {
        try { fill(panels[i], t); } catch (e) { /* keep the panel as it was */ }
      }
    }
    builtAt = s.built_at;
    body.setAttribute("data-built-at", builtAt);
  }

  function poll() {
    if (document.hidden) { fresh(); return; }
    fetch("state.json?t=" + Date.now(), {cache: "no-store", credentials: "same-origin"})
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(apply)
      .catch(function () {})
      .then(fresh);
  }

  fresh();
  setInterval(poll, EVERY);
}());
