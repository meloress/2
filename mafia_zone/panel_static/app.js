/* Admiral Mafia admin panel.
   Xavfsizlik: hech qayerda innerHTML ishlatilmaydi — barcha ma'lumot textContent orqali chiqadi (XSS yo'q).
   O'zgartiruvchi so'rovlar X-CSRF sarlavhasi bilan ketadi. */
"use strict";
(() => {
  const $app = document.getElementById("app");
  const $toasts = document.getElementById("toasts");
  const S = { me: null, csrf: "", period: "today", view: 0, timers: [], bot: "" };

  // ================= DOM yordamchilari =================
  const SVGNS = "http://www.w3.org/2000/svg";
  function h(tag, props, ...kids) {
    const svg = tag.startsWith("svg:");
    const el = svg ? document.createElementNS(SVGNS, tag.slice(4)) : document.createElement(tag);
    if (props) {
      for (const [k, v] of Object.entries(props)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === "class") el.setAttribute("class", v);
        else if (k === "text") el.textContent = String(v);
        else if (k === "style") Object.assign(el.style, v);
        else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
        else if (k === "value" && !svg) el.value = v;
        else if (k === "checked" && !svg) el.checked = !!v;
        else el.setAttribute(k, v === true ? "" : String(v));
      }
    }
    for (const c of kids.flat(Infinity)) {
      if (c === null || c === undefined || c === false) continue;
      el.append(c instanceof Node ? c : String(c));
    }
    return el;
  }
  const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };

  const ICONS = {
    dash: "M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z",
    users: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75",
    send: "M3 11v2a1 1 0 0 0 1 1h3l5 4V6L7 10H4a1 1 0 0 0-1 1zM16 8a5 5 0 0 1 0 8M19 5a9 9 0 0 1 0 14",
    games: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM10 8l6 4-6 4z",
    money: "M12 1v22M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6",
    search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3",
    menu: "M3 6h18M3 12h18M3 18h18",
    out: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
    plus: "M12 5v14M5 12h14",
    minus: "M5 12h14",
    x: "M18 6L6 18M6 6l12 12",
    left: "M15 18l-6-6 6-6",
    right: "M9 18l6-6-6-6",
    copy: "M9 9h11v11H9zM5 15H4V4h11v1",
    refresh: "M21 12a9 9 0 1 1-2.64-6.36M21 3v6h-6",
    img: "M21 15l-5-5L5 21M3 5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM8.5 10a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z",
    link: "M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71",
    tg: "M22 2L11 13M22 2l-7 20-4-9-9-4z",
    shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  };
  function icon(name, size = 18) {
    return h("svg:svg", { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
      "stroke-width": "1.8", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" },
      h("svg:path", { d: ICONS[name] }));
  }

  // ================= formatlash =================
  const NF = new Intl.NumberFormat("ru-RU");
  const fmt = (n) => (n === null || n === undefined ? "—" : NF.format(n));
  const DTF = new Intl.DateTimeFormat("ru-RU", { timeZone: "Asia/Tashkent", day: "2-digit", month: "2-digit",
    year: "numeric", hour: "2-digit", minute: "2-digit" });
  const TF = new Intl.DateTimeFormat("ru-RU", { timeZone: "Asia/Tashkent", hour: "2-digit", minute: "2-digit" });
  const fmtDate = (iso) => (iso ? DTF.format(new Date(iso)) : "—");
  function ago(iso) {
    if (!iso) return "—";
    const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return "hozirgina";
    if (s < 3600) return `${Math.floor(s / 60)} daq oldin`;
    if (s < 86400) return `${Math.floor(s / 3600)} soat oldin`;
    if (s < 86400 * 2) return `kecha, ${TF.format(new Date(iso))}`;
    return fmtDate(iso);
  }
  function elapsed(iso) {
    if (!iso) return "—";
    const s = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
    const m = Math.floor(s / 60);
    return m >= 60 ? `${Math.floor(m / 60)} soat ${m % 60} daq` : `${m} daq`;
  }
  const initial = (name) => ((name || "?").trim().match(/\p{L}|\p{N}/u) || ["?"])[0].toUpperCase();
  const ROLE_LABEL = { owner: "Bosh admin", moderator: "Moderator", viewer: "Kuzatuvchi" };
  const ROLE_CHIP = { owner: "c-gold", moderator: "c-blue", viewer: "c-gray" };
  const RANK = { viewer: 0, moderator: 1, owner: 2 };
  const can = (role) => S.me && RANK[S.me.role] >= RANK[role];
  const PHASE = {
    night: ["Tun", "c-blue", "#6EA8FF"], day: ["Kun", "c-gold", "#F2C25B"], voting: ["Ovoz", "c-red", "#FF6B6B"],
    confirm: ["Tasdiq", "c-violet", "#B794FF"], lobby: ["Ro'yxat", "c-green", "#4ADE98"],
  };
  const STATUS = {
    banned: ["Ban", "c-red"], playing: ["O'yinda", "c-blue"], new: ["Yangi", "c-gold"],
    active: ["Faol", "c-green"], idle: ["Nofaol", "c-gray"],
  };
  const chip = (text, cls) => h("span", { class: `chip ${cls || ""}`, text });
  const roleName = (code) => (S.me && S.me.roles[code] ? S.me.roles[code].name : code || "—");

  // ================= API =================
  class ApiError extends Error {}
  async function api(path, opts = {}) {
    const init = { method: opts.method || "GET", credentials: "same-origin", headers: {} };
    if (init.method !== "GET") init.headers["X-CSRF"] = S.csrf;
    if (opts.json !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.json);
    }
    if (opts.form) init.body = opts.form;
    let res;
    try {
      res = await fetch(path, init);
    } catch (e) {
      throw new ApiError("Serverga ulanib bo'lmadi. Internetni tekshiring.");
    }
    let data = {};
    try { data = await res.json(); } catch (e) { data = {}; }
    if (res.status === 401 && !opts.quiet401) {
      S.me = null;
      go("/login");
      throw new ApiError("Sessiya tugadi. Qaytadan kiring.");
    }
    if (!res.ok) throw new ApiError(data.error || `Xatolik (${res.status})`);
    return data;
  }

  // ================= toast va modal =================
  function toast(msg, kind = "ok") {
    const t = h("div", { class: `toast ${kind}` },
      h("span", { class: `dot`, style: { background: kind === "bad" ? "#FF6B6B" : "#4ADE98", marginTop: "5px" } }),
      h("div", { text: msg }));
    $toasts.append(t);
    setTimeout(() => t.remove(), kind === "bad" ? 6000 : 3500);
  }
  const fail = (e) => toast(e && e.message ? e.message : "Xatolik yuz berdi", "bad");

  let openModal = null;
  function modal(content, { wide = false, onClose } = {}) {
    closeModal();
    const box = h("div", { class: `modal ${wide ? "wide" : ""}`, role: "dialog", "aria-modal": "true" }, content);
    const back = h("div", { class: "modal-back", onMousedown: (e) => { if (e.target === back) closeModal(); } }, box);
    const prev = document.activeElement;
    const onKey = (e) => {
      if (e.key === "Escape") closeModal();
      if (e.key === "Tab") { // fokus modal ichida qoladi
        const f = [...box.querySelectorAll("button, a[href], input, select, textarea")].filter((x) => !x.disabled);
        if (!f.length) return;
        if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
        else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    document.body.append(back);
    openModal = () => {
      document.removeEventListener("keydown", onKey);
      back.remove();
      openModal = null;
      if (onClose) onClose();
      if (prev && prev.focus) prev.focus();
    };
    const first = box.querySelector("input, select, textarea, button");
    if (first) setTimeout(() => first.focus(), 30);
    return box;
  }
  function closeModal() { if (openModal) openModal(); }

  /* Tasdiqlash oynasi. input: {label, placeholder, required, value, max} bo'lsa matn so'raydi. */
  function confirmBox({ title, text, ok = "Tasdiqlash", danger = false, input = null }) {
    return new Promise((resolve) => {
      let done = false;
      const finish = (v) => { if (!done) { done = true; resolve(v); closeModal(); } };
      const inp = input ? h("input", { class: "input", id: "cf-in", placeholder: input.placeholder || "",
        maxlength: input.max || 200, value: input.value || "" }) : null;
      const err = h("div", { class: "err" });
      const submit = () => {
        if (input && input.required && !inp.value.trim()) { err.textContent = "To'ldiring"; inp.focus(); return; }
        finish({ ok: true, value: inp ? inp.value.trim() : "" });
      };
      if (inp) inp.addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
      modal([
        h("h2", { text: title }),
        text ? h("p", { class: "muted", text }) : null,
        input ? h("div", { class: "field" }, h("label", { for: "cf-in", text: input.label }), inp, err) : null,
        h("div", { class: "modal-actions" },
          h("button", { type: "button", class: "btn", text: "Bekor qilish", onClick: () => finish({ ok: false }) }),
          h("button", { type: "button", class: `btn ${danger ? "danger" : "primary"}`, text: ok, onClick: submit })),
      ], { onClose: () => { if (!done) { done = true; resolve({ ok: false }); } } });
    });
  }

  /* Tugmani so'rov davomida bloklaydi (ikki marta bosilmasin). */
  async function busy(btn, fn) {
    if (btn.disabled) return;
    const old = [...btn.childNodes];
    btn.disabled = true;
    clear(btn).append(h("span", { class: "spin" }), "Kuting...");
    try { return await fn(); } finally { btn.disabled = false; clear(btn).append(...old); }
  }

  // ================= marshrutlash =================
  function parseHash() {
    const raw = (location.hash || "#/").slice(1) || "/";
    const i = raw.indexOf("?");
    let path = i < 0 ? raw : raw.slice(0, i);
    try { path = decodeURIComponent(path); } catch (e) { path = "/"; }
    return { path: path || "/", params: new URLSearchParams(i < 0 ? "" : raw.slice(i + 1)) };
  }
  function go(path, replace = false) {
    const url = `#${path}`;
    if (location.hash === url) { render(); return; }
    if (replace) { history.replaceState(null, "", url); render(); } else location.hash = url;
  }
  function setQuery(path, params) {
    const qs = params.toString();
    history.replaceState(null, "", `#${path}${qs ? `?${qs}` : ""}`);
  }
  function every(ms, fn) {
    const id = setInterval(() => { if (document.visibilityState === "visible") fn(); }, ms);
    S.timers.push(id);
  }
  window.addEventListener("hashchange", () => render());

  const NAV = [
    { key: "dash", path: "/", label: "Boshqaruv", icon: "dash" },
    { key: "users", path: "/users", label: "Foydalanuvchilar", icon: "users" },
    { key: "broadcast", path: "/broadcast", label: "Xabar yuborish", icon: "send" },
    { key: "games", path: "/games", label: "O'yinlar va guruhlar", icon: "games" },
    { key: "economy", path: "/economy", label: "Iqtisod va adminlar", icon: "money" },
  ];

  async function boot() {
    try {
      const me = await api("/api/me", { quiet401: true });
      S.me = me; S.csrf = me.csrf; S.bot = me.bot;
    } catch (e) {
      S.me = null;
    }
    render();
  }

  function render() {
    S.view += 1;
    S.timers.forEach(clearInterval);
    S.timers = [];
    closeModal();
    const { path, params } = parseHash();
    if (!S.me) { pageLogin(params); return; }
    if (path === "/login") { go("/", true); return; }
    const seg = path.split("/").filter(Boolean);
    const key = seg[0] || "dash";
    const content = h("div", { class: "stack" });
    shell(key, content);
    const view = S.view;
    const pages = { dash: pageDash, users: pageUsers, broadcast: pageBroadcast, games: pageGames, economy: pageEconomy };
    (pages[key] || pageNotFound)(content, { view, params, seg });
    window.scrollTo(0, 0);
  }
  const alive = (view) => view === S.view;

  function shell(active, content) {
    const side = h("aside", { class: "side", id: "side" });
    const scrim = h("div", { class: "scrim", onClick: () => toggleMenu(false) });
    const toggleMenu = (open) => { side.classList.toggle("open", open); scrim.classList.toggle("open", open); };
    side.append(
      h("div", { class: "brand" }, h("div", { class: "logo", text: "MZ" }),
        h("div", null, h("div", { class: "brand-name", text: "Admiral Mafia" }), h("div", { class: "small muted", text: "Admin panel" }))),
      h("nav", { class: "nav", "aria-label": "Asosiy menyu" }, NAV.map((n) =>
        h("a", { href: `#${n.path}`, "aria-current": n.key === active ? "page" : null, onClick: () => toggleMenu(false) },
          icon(n.icon), h("span", { text: n.label })))),
      h("div", { class: "side-foot" },
        h("div", { class: "status-box" },
          h("div", { class: "inline" }, h("span", { class: "live-dot" }), h("b", { text: "Bot ishlayapti" })),
          S.bot ? h("a", { class: "small mono", href: `https://t.me/${S.bot}`, target: "_blank", rel: "noopener noreferrer", text: `@${S.bot}` }) : null),
        h("button", { type: "button", class: "btn ghost block", onClick: logout }, icon("out", 16), "Chiqish")));

    const search = h("input", { type: "search", id: "gsearch", placeholder: "Foydalanuvchi qidirish: ism, @username yoki ID", autocomplete: "off" });
    search.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && search.value.trim()) go(`/users?q=${encodeURIComponent(search.value.trim())}`);
    });
    const top = h("header", { class: "top" },
      h("button", { type: "button", class: "btn icon menu-btn", "aria-label": "Menyuni ochish", onClick: () => toggleMenu(true) }, icon("menu")),
      h("label", { class: "search" }, h("span", { class: "sr", text: "Qidiruv" }), icon("search", 16), search, h("kbd", { text: "/" })),
      h("div", { class: "me" },
        h("div", { class: "who-text right" }, h("div", { class: "ellipsis", text: S.me.name }),
          h("div", { class: "small muted", text: ROLE_LABEL[S.me.role] })),
        h("div", { class: "avatar", text: initial(S.me.name), title: S.me.name })));
    clear($app).append(h("div", { class: "shell" }, side, scrim, h("main", { class: "main", id: "main" }, top, content)));
  }
  document.addEventListener("keydown", (e) => {
    const t = e.target;
    if (e.key === "/" && !openModal && !(t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement || t instanceof HTMLSelectElement)) {
      const s = document.getElementById("gsearch");
      if (s) { e.preventDefault(); s.focus(); }
    }
  });

  async function logout() {
    try { await api("/api/logout", { method: "POST" }); } catch (e) { /* baribir chiqamiz */ }
    S.me = null;
    go("/login");
  }

  function head(title, subtitle, ...right) {
    return h("div", { class: "page-head" },
      h("div", null, h("h1", { text: title }), subtitle ? h("p", { class: "muted", text: subtitle }) : null),
      right.length ? h("div", { class: "inline" }, right) : null);
  }
  const empty = (text) => h("div", { class: "empty" }, h("div", { text }));
  const skel = (n = 3, hgt = 18) => h("div", { class: "stack gap-8" }, Array.from({ length: n }, () => h("div", { class: "skel", style: { height: `${hgt}px` } })));
  function pager(page, size, total, onPage) {
    const from = total ? page * size + 1 : 0;
    const to = Math.min(total, (page + 1) * size);
    return h("div", { class: "pager" },
      h("span", { class: "num", text: `${fmt(from)}–${fmt(to)} / ${fmt(total)}` }),
      h("div", { class: "inline" },
        h("button", { type: "button", class: "btn icon", "aria-label": "Oldingi sahifa", disabled: page <= 0, onClick: () => onPage(page - 1) }, icon("left")),
        h("button", { type: "button", class: "btn icon", "aria-label": "Keyingi sahifa", disabled: to >= total, onClick: () => onPage(page + 1) }, icon("right"))));
  }
  function errorCard(e, retry) {
    return h("div", { class: "card" }, h("div", { class: "empty" },
      h("div", { text: e.message || "Ma'lumotni yuklab bo'lmadi" }),
      retry ? h("button", { type: "button", class: "btn", onClick: retry }, icon("refresh", 16), "Qayta urinish") : null));
  }
  function seg(options, value, onPick, label) {
    return h("div", { class: "seg", role: "group", "aria-label": label },
      options.map(([v, text]) => h("button", { type: "button", "aria-pressed": String(v === value), text,
        onClick: () => onPick(v) })));
  }

  // ================= kirish =================
  async function pageLogin(params) {
    let bot = S.bot;
    if (!bot) {
      try { bot = (await api("/api/public", { quiet401: true })).bot; S.bot = bot; } catch (e) { bot = ""; }
    }
    const err = params.get("err");
    clear($app).append(h("div", { class: "login" }, h("div", { class: "login-card" },
      h("div", { class: "logo", text: "MZ" }),
      h("div", { class: "stack gap-8" }, h("h1", { text: "Admiral Mafia admin" }),
        h("p", { class: "muted", text: "Telegram orqali kiring. Parol kerak emas — faqat admin ro'yxatidagilar kira oladi." })),
      err === "link" ? h("div", { class: "alert", text: "Kirish havolasi eskirgan yoki allaqachon ishlatilgan. Botdan yangisini oling." }) : null,
      bot ? h("a", { class: "btn tg-login block", href: `https://t.me/${bot}?start=panel`, target: "_blank", rel: "noopener noreferrer" }, icon("tg", 20), "Telegram orqali kirish")
        : h("div", { class: "alert info", text: "Bot hali ishga tushmagan. Bir ozdan keyin sahifani yangilang." }),
      h("ol", { class: "steps" },
        h("li", { text: "Tugmani bosing — bot ochiladi" }),
        h("li", { text: "Botda «Start» bosing (yoki /panel yozing)" }),
        h("li", { text: "Kelgan «Panelga kirish» tugmasini bosing" })),
      h("p", { class: "hint", text: "Havola 5 daqiqa amal qiladi va bir marta ishlaydi. Sessiya 12 soatdan keyin tugaydi." }))));
  }

  function pageNotFound(root) {
    root.append(head("Sahifa topilmadi", null), h("div", { class: "card" }, empty("Bunday bo'lim yo'q."), h("a", { class: "btn", href: "#/", text: "Bosh sahifaga" })));
  }

  // ================= boshqaruv paneli =================
  const PERIODS = [["today", "Bugun"], ["7", "7 kun"], ["30", "30 kun"], ["all", "Hammasi"]];
  const PERIOD_WORD = { today: "bugun", 7: "7 kunda", 30: "30 kunda", all: "jami" };
  const ACTIONS = {
    login: ["Panelga kirdi", "K", "c-gray"], pro: ["PRO o'zgardi", "P", "c-green"], nickname: ["Nickname o'chirildi", "N", "c-gray"], balance: ["Balans o'zgardi", "$", "c-green"], item: ["Buyum berildi", "B", "c-green"],
    ban: ["Ban qilindi", "B", "c-red"], unban: ["Bandan chiqarildi", "U", "c-green"], stop_game: ["O'yin to'xtatildi", "O", "c-red"],
    view_roles: ["Rollarni ko'rdi", "R", "c-violet"], group_settings: ["Guruh sozlamalari", "G", "c-gold"],
    leave_group: ["Guruhdan chiqdi", "G", "c-red"], economy: ["Iqtisod sozlamalari", "S", "c-gold"],
    admin_set: ["Admin roli berildi", "A", "c-blue"], admin_remove: ["Adminlikdan olindi", "A", "c-red"],
    broadcast: ["E'lon yuborildi", "E", "c-blue"], broadcast_cancel: ["E'lon to'xtatildi", "E", "c-red"],
  };
  function feedItem(l) {
    const [label, letter, cls] = ACTIONS[l.action] || [l.action, "•", "c-gray"];
    const detail = [l.target, l.details].filter(Boolean).join(" · ");
    return h("div", { class: "feed-item" },
      h("div", { class: `feed-icon chip ${cls}`, text: letter }),
      h("div", { class: "stack gap-8", style: { gap: "2px", minWidth: "0" } },
        h("div", null, h("b", { text: l.admin }), ` — ${label}`),
        detail ? h("div", { class: "small muted ellipsis", text: detail, title: detail }) : null,
        h("div", { class: "small muted", text: ago(l.at) })));
  }

  function spark(vals, color) {
    const w = 120, hh = 32, pad = 3;
    const max = Math.max(...vals, 1), min = Math.min(...vals, 0);
    const pts = vals.map((v, i) => [vals.length > 1 ? (i * w) / (vals.length - 1) : w / 2, pad + (hh - 2 * pad) * (1 - (v - min) / (max - min || 1))]);
    const line = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
    return h("svg:svg", { viewBox: `0 0 ${w} ${hh}`, preserveAspectRatio: "none", "aria-hidden": "true" },
      h("svg:path", { d: `${line} L${w} ${hh} L0 ${hh} Z`, fill: color, "fill-opacity": "0.12" }),
      h("svg:path", { d: line, fill: "none", stroke: color, "stroke-width": "1.8", "stroke-linejoin": "round", "vector-effect": "non-scaling-stroke" }));
  }
  function kpi(label, value, sub, series, color) {
    return h("div", { class: "kpi" },
      h("div", { class: "between" }, h("span", { class: "muted small", text: label })),
      h("div", { class: "val", text: value }),
      h("div", { class: "small muted", text: sub }),
      series ? spark(series, color) : null);
  }
  function chart(rows) {
    const W = 700, H = 220, pad = 16;
    const all = rows.flatMap((r) => [r.games, r.users]);
    const max = Math.max(...all, 1);
    const x = (i) => (rows.length > 1 ? (i * W) / (rows.length - 1) : W / 2);
    const y = (v) => pad + (H - 2 * pad) * (1 - v / max);
    const path = (k) => rows.map((r, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(r[k]).toFixed(1)}`).join(" ");
    const svg = h("svg:svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none", role: "img",
      "aria-label": `14 kunlik grafik: jami ${rows.reduce((a, r) => a + r.games, 0)} o'yin` },
      h("svg:path", { d: `M0 ${H * 0.25}H${W}M0 ${H * 0.5}H${W}M0 ${H * 0.75}H${W}`, stroke: "#1E2129", "stroke-width": "1", "vector-effect": "non-scaling-stroke" }),
      h("svg:path", { d: `${path("games")} L${W} ${H} L0 ${H} Z`, fill: "rgba(242,194,91,0.12)" }),
      h("svg:path", { d: path("games"), fill: "none", stroke: "#F2C25B", "stroke-width": "2.4", "stroke-linejoin": "round", "vector-effect": "non-scaling-stroke" }),
      h("svg:path", { d: path("users"), fill: "none", stroke: "#6EA8FF", "stroke-width": "2", "stroke-dasharray": "5 5", "stroke-linejoin": "round", "vector-effect": "non-scaling-stroke" }),
      rows.map((r, i) => h("svg:rect", { x: Math.max(0, x(i) - W / rows.length / 2), y: 0, width: W / rows.length, height: H, fill: "transparent" },
        h("svg:title", { text: `${r.date}: ${r.games} o'yin, ${r.users} yangi foydalanuvchi` }))));
    const labels = rows.filter((_, i) => i % 3 === 0 || i === rows.length - 1).map((r) => h("span", { text: r.date }));
    return h("div", { class: "chart stack gap-8" }, svg, h("div", { class: "chart-x" }, labels));
  }
  const TEAMS = [["town", "Tinch aholi", "#6EA8FF"], ["mafia", "Mafiya", "#FF6B6B"], ["neutral", "Neytrallar", "#B794FF"], ["draw", "Durang", "#4B5060"]];
  function donut(teams, games) {
    const total = TEAMS.reduce((a, [k]) => a + (teams[k] || 0), 0);
    const d = h("div", { class: "donut" }, h("div", null, h("span", { class: "num", style: { fontSize: "24px" }, text: fmt(games) }), h("span", { class: "small muted", text: "o'yin" })));
    if (total) {
      let acc = 0;
      const parts = TEAMS.map(([k, , c]) => { const from = acc; acc += (teams[k] || 0) / total * 100; return `${c} ${from}% ${acc}%`; });
      d.style.background = `conic-gradient(${parts.join(", ")})`;
    }
    const legend = h("div", { class: "stack gap-8" }, TEAMS.map(([k, name, c]) => {
      const pct = total ? Math.round((teams[k] || 0) / total * 100) : 0;
      return h("div", { class: "inline", style: { justifyContent: "space-between" } },
        h("span", { class: "inline" }, h("span", { class: "dot", style: { background: c } }), name),
        h("span", { class: "num muted", text: `${pct}% · ${fmt(teams[k] || 0)}` }));
    }));
    let note;
    if (!total) note = h("div", { class: "alert info", text: "Bu davrda tugagan o'yin yo'q." });
    else {
      const [k, name] = TEAMS.slice(0, 3).reduce((best, t) => ((teams[t[0]] || 0) > (teams[best[0]] || 0) ? t : best));
      const share = (teams[k] || 0) / total;
      note = share > 0.55 && total >= 20
        ? h("div", { class: "alert", text: `${name} juda ko'p yutmoqda (${Math.round(share * 100)}%). Rollar balansini ko'rib chiqing.` })
        : h("div", { class: "alert info", text: total < 20 ? "Xulosa uchun kamida 20 ta o'yin kerak." : "Balans yaxshi: hech bir jamoa 55% dan oshmagan." });
    }
    return [d, legend, note];
  }
  function gameCard(g) {
    const [label, cls, color] = PHASE[g.phase] || [g.phase, "c-gray", "#888"];
    const pct = g.total ? Math.round((g.alive / g.total) * 100) : 0;
    return h("a", { class: "game-card", href: "#/games" },
      h("div", { class: "between" }, h("b", { class: "ellipsis", text: g.title }), chip(label, cls)),
      h("div", { class: "stack gap-8", style: { gap: "6px" } },
        h("div", { class: "between small muted" }, h("span", { text: g.phase === "lobby" ? "Qo'shilganlar" : "Tirik" }),
          h("span", { class: "num", style: { color: "#EDEDEF" }, text: g.phase === "lobby" ? fmt(g.total) : `${g.alive} / ${g.total}` })),
        h("div", { class: "bar" }, h("div", { style: { width: `${g.phase === "lobby" ? Math.min(100, g.total / 60 * 100) : pct}%`, background: color } }))),
      h("div", { class: "between small muted num" },
        h("span", { text: g.phase === "lobby" ? `${g.lobby_left || 0} s qoldi` : `${g.day}-kun` }),
        h("span", { text: g.phase === "lobby" ? "" : elapsed(g.started) })));
  }

  function pageDash(root, { view }) {
    const greet = (() => { const hr = Number(new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Tashkent", hour: "2-digit", hourCycle: "h23" }).format(new Date())); return hr < 5 ? "Xayrli tun" : hr < 12 ? "Xayrli tong" : hr < 18 ? "Xayrli kun" : "Xayrli kech"; })();
    const sub = h("p", { class: "muted", text: "Yuklanmoqda..." });
    const periodBox = h("div");
    const body = h("div", { class: "stack" }, h("div", { class: "kpis" }, Array.from({ length: 6 }, () => h("div", { class: "kpi" }, skel(3)))));
    root.append(h("div", { class: "page-head" },
      h("div", null, h("h1", { text: `${greet}, ${S.me.name.split(" ")[0] || "admin"}` }), sub),
      h("div", { class: "inline" }, periodBox,
        can("owner") ? h("a", { class: "btn primary", href: "#/broadcast" }, icon("plus", 16), "Yangi e'lon") : null)), body);

    const drawPeriod = () => clear(periodBox).append(seg(PERIODS, S.period, (p) => { S.period = p; drawPeriod(); load(); }, "Davr"));
    drawPeriod();

    async function load() {
      let d;
      try { d = await api(`/api/dashboard?period=${S.period}`); } catch (e) { if (alive(view)) clear(body).append(errorCard(e, load)); return; }
      if (!alive(view)) return;
      const w = PERIOD_WORD[d.period];
      sub.textContent = `Hozir ${d.live_count} ta o'yin yoki ro'yxat ochiq, ${d.playing} kishi ishtirok etmoqda`;
      const gamesSeries = d.chart.map((r) => r.games), usersSeries = d.chart.map((r) => r.users);
      clear(body).append(
        h("div", { class: "kpis" },
          kpi("Foydalanuvchilar", fmt(d.users), d.period === "all" ? `${fmt(d.banned)} ban qilingan` : `+${fmt(d.users_new)} ${w}`, usersSeries, "#F2C25B"),
          kpi(d.period === "all" ? "Faol (30 kun)" : `Faol (${w})`, fmt(d.active), "botdan foydalanganlar", null),
          kpi(`O'yinlar (${w})`, fmt(d.games), d.avg_minutes ? `o'rtacha ${d.avg_minutes} daqiqa` : "tugagan o'yinlar", gamesSeries, "#6EA8FF"),
          kpi("Guruhlar", fmt(d.groups), d.period === "all" ? "bot qo'shilgan guruhlar" : `+${fmt(d.groups_new)} ${w}`, null),
          kpi("Muomaladagi pul", `${fmt(d.money)} $`, `${fmt(d.diamonds)} olmos`, null),
          kpi("Hozir o'ynamoqda", fmt(d.playing), `${d.live_count} ta o'yin / ro'yxat`, null)),
        h("div", { class: "row" },
          h("section", { class: "card f3" },
            h("div", { class: "between" },
              h("div", { class: "stack gap-8", style: { gap: "4px" } }, h("h2", { text: "Oxirgi 14 kun" }),
                h("span", { class: "num", style: { fontSize: "24px" }, text: `${fmt(gamesSeries.reduce((a, b) => a + b, 0))} o'yin` })),
              h("div", { class: "legend" }, h("span", null, h("i", { style: { background: "#F2C25B" } }), "O'yinlar"),
                h("span", null, h("i", { style: { background: "#6EA8FF" } }), "Yangi foydalanuvchilar"))),
            chart(d.chart)),
          h("section", { class: "card f1" }, h("h2", { text: `G'alabalar balansi (${w})` }), donut(d.teams, d.games))),
        h("div", { class: "row" },
          h("section", { class: "card f3" },
            h("div", { class: "between" }, h("h2", { class: "inline" }, h("span", { class: "live-dot" }), "Jonli o'yinlar"),
              h("a", { href: "#/games", text: "Hammasi →" })),
            d.live.length ? h("div", { class: "live-grid" }, d.live.map(gameCard)) : empty("Hozir hech qayerda o'yin ketmayapti.")),
          h("section", { class: "card f2" },
            h("div", { class: "between" }, h("h2", { text: "Faollik" }), h("a", { href: "#/economy", text: "Jurnal →" })),
            d.log.length ? h("div", null, d.log.map(feedItem)) : empty("Hali admin amallari yo'q."))));
    }
    load();
    every(20000, load);
  }

  // ================= foydalanuvchilar =================
  const FILTERS = [["all", "Hammasi"], ["active", "Faol (7 kun)"], ["banned", "Ban"], ["rich", "Eng boylar"], ["games", "Ko'p o'ynagan"]];
  function pageUsers(root, { view, params, seg: parts }) {
    const st = { q: params.get("q") || "", filter: params.get("filter") || "all", page: Math.max(0, Number(params.get("page")) || 0) };
    if (!FILTERS.some(([k]) => k === st.filter)) st.filter = "all";
    const selected = parts[1] && /^\d{1,19}$/.test(parts[1]) ? parts[1] : null;
    const q = h("input", { class: "input", type: "search", id: "uq", placeholder: "Ism, @username yoki Telegram ID", value: st.q, autocomplete: "off", maxlength: 64 });
    const filterBox = h("div");
    const listCard = h("section", { class: "card tight" }, skel(8, 36));
    const detailBox = selected ? h("aside", { class: "card detail warn" }, skel(6, 28)) : null;
    root.append(head("Foydalanuvchilar", "Qidirish, balans va buyumlarni o'zgartirish, ban"),
      h("div", { class: "inline" }, h("div", { class: "field", style: { flex: "1 1 280px" } }, h("label", { for: "uq", class: "sr", text: "Qidiruv" }), q), filterBox),
      selected ? h("div", { class: "split" }, listCard, detailBox) : listCard);

    const sync = () => {
      const p = new URLSearchParams();
      if (st.q) p.set("q", st.q);
      if (st.filter !== "all") p.set("filter", st.filter);
      if (st.page) p.set("page", String(st.page));
      setQuery(selected ? `/users/${selected}` : "/users", p);
    };
    const drawFilter = () => clear(filterBox).append(seg(FILTERS, st.filter, (f) => { st.filter = f; st.page = 0; drawFilter(); sync(); loadList(); }, "Filtr"));
    drawFilter();
    let tmr;
    q.addEventListener("input", () => { clearTimeout(tmr); tmr = setTimeout(() => { st.q = q.value.trim(); st.page = 0; sync(); loadList(); }, 300); });
    const listHref = () => { const p = new URLSearchParams(); if (st.q) p.set("q", st.q); if (st.filter !== "all") p.set("filter", st.filter); if (st.page) p.set("page", String(st.page)); const s = p.toString(); return s ? `?${s}` : ""; };

    let reqId = 0;
    async function loadList() {
      const my = ++reqId;
      let d;
      try { d = await api(`/api/users?q=${encodeURIComponent(st.q)}&filter=${st.filter}&page=${st.page}`); }
      catch (e) { if (alive(view)) clear(listCard).append(errorCard(e, loadList)); return; }
      if (!alive(view) || my !== reqId) return;
      if (!d.items.length) { clear(listCard).append(empty(st.q ? `«${st.q}» bo'yicha hech kim topilmadi.` : "Foydalanuvchilar yo'q.")); return; }
      const rows = d.items.map((u) => {
        const [sl, sc] = STATUS[u.status] || [u.status, "c-gray"];
        const href = `#/users/${u.id}${listHref()}`;
        return h("tr", { class: `click ${String(u.id) === selected ? "sel" : ""}`, onClick: (e) => { if (!(e.target.closest && e.target.closest("a"))) location.hash = href; } },
          h("td", { class: "wide" }, h("div", { class: "who" }, h("div", { class: "avatar round", text: initial(u.name) }),
            h("div", null, h("a", { href, class: "ellipsis", style: { color: "#EDEDEF", fontWeight: "500" }, text: u.name || "(ismsiz)" }),
              h("span", { class: "small muted mono ellipsis", text: u.username ? `@${u.username}` : String(u.id) })))),
          h("td", { class: "right num", "data-label": "Dollar", text: fmt(u.dollars) }),
          h("td", { class: "right num", "data-label": "Olmos", text: fmt(u.diamonds) }),
          h("td", { class: "right num", "data-label": "O'yin", text: fmt(u.games) }),
          h("td", { class: "right num", "data-label": "G'alaba", text: fmt(u.wins) }),
          h("td", { "data-label": "Holat" }, chip(sl, sc)));
      });
      clear(listCard).append(h("div", { class: "table-wrap" }, h("table", { class: "t cards" },
        h("thead", null, h("tr", null, h("th", { text: "Foydalanuvchi" }), h("th", { class: "right", text: "Dollar" }), h("th", { class: "right", text: "Olmos" }),
          h("th", { class: "right", text: "O'yin" }), h("th", { class: "right", text: "G'alaba" }), h("th", { text: "Holat" }))),
        h("tbody", null, rows))),
        pager(d.page, d.size, d.total, (p) => { st.page = p; sync(); loadList(); }));
    }
    loadList();
    if (selected) loadDetail(detailBox, selected, view, () => loadList(), listHref);
  }

  async function loadDetail(box, uid, view, refreshList, listHref) {
    let u;
    try { u = await api(`/api/users/${uid}`); } catch (e) { if (alive(view)) clear(box).append(errorCard(e, () => loadDetail(box, uid, view, refreshList, listHref))); return; }
    if (!alive(view)) return;
    const [sl, sc] = STATUS[u.status] || [u.status, "c-gray"];
    const vals = { dollars: h("span", { class: "v", text: fmt(u.dollars) }), diamonds: h("span", { class: "v", text: fmt(u.diamonds) }) };
    const winPct = u.games ? Math.round((u.wins / u.games) * 100) : 0;
    const copyBtn = h("button", { type: "button", class: "btn sm icon ghost", "aria-label": "ID ni nusxalash", title: "Nusxalash",
      onClick: async () => { try { await navigator.clipboard.writeText(String(u.id)); toast("ID nusxalandi"); } catch (e) { toast("Nusxalab bo'lmadi", "bad"); } } }, icon("copy", 16));

    const parts = [
      h("div", { class: "between" }, h("a", { href: `#/users${listHref()}`, class: "inline small" }, icon("left", 16), "Ro'yxatga"),
        h("button", { type: "button", class: "btn sm icon ghost", "aria-label": "Yangilash", onClick: () => loadDetail(box, uid, view, refreshList, listHref) }, icon("refresh", 16))),
      h("div", { class: "who" }, h("div", { class: "avatar lg", text: initial(u.name) }),
        h("div", null, h("h2", { class: "ellipsis", style: { fontSize: "18px" }, text: u.name || "(ismsiz)" }),
          h("div", { class: "inline small muted mono" }, h("span", { text: `ID ${u.id}` }), copyBtn),
          h("div", { class: "inline" }, chip(sl, sc), u.admin_role ? chip(ROLE_LABEL[u.admin_role], ROLE_CHIP[u.admin_role]) : null,
            u.username ? h("a", { class: "small", href: `https://t.me/${encodeURIComponent(u.username)}`, target: "_blank", rel: "noopener noreferrer", text: `@${u.username}` }) : null))),
      h("div", { class: "small muted stack gap-8", style: { gap: "4px" } },
        h("div", null, "Unvon: ", h("span", { style: { color: "#EDEDEF" }, text: u.rank })),
        h("div", null, "Para: ", u.partner ? h("a", { href: `#/users/${u.partner.id}`, text: u.partner.name }) : "yo'q"),
        h("div", { text: `Ro'yxatdan o'tgan: ${fmtDate(u.created_at)}` }),
        h("div", { text: `Oxirgi faollik: ${ago(u.last_seen)}` })),
      h("div", { class: "stat-grid" },
        h("div", { class: "stat" }, h("span", { class: "small muted", text: "Dollar" }), vals.dollars),
        h("div", { class: "stat" }, h("span", { class: "small muted", text: "Olmos" }), vals.diamonds),
        h("div", { class: "stat" }, h("span", { class: "small muted", text: "O'yinlar" }), h("span", { class: "v", text: fmt(u.games) })),
        h("div", { class: "stat" }, h("span", { class: "small muted", text: "G'alaba" }), h("span", { class: "v", text: `${fmt(u.wins)} · ${winPct}%` }))),
    ];

    if (can("owner")) {
      const amt = h("input", { class: "input num", id: "b-amt", type: "number", inputmode: "numeric", min: "1", max: "1000000000", step: "1", placeholder: "500" });
      const cur = h("select", { class: "input", id: "b-cur" }, h("option", { value: "dollars", text: "Dollar" }), h("option", { value: "diamonds", text: "Olmos" }));
      const why = h("input", { class: "input", id: "b-why", maxlength: 200, placeholder: "Masalan: konkurs g'olibi" });
      const notify = h("input", { type: "checkbox", class: "switch", id: "b-ntf", checked: true });
      const err = h("div", { class: "err", role: "alert" });
      const submit = async (sign, btn) => {
        err.textContent = "";
        const n = Number(amt.value);
        if (!Number.isInteger(n) || n < 1 || n > 1e9) { err.textContent = "Miqdor 1 dan 1 000 000 000 gacha butun son bo'lsin"; amt.setAttribute("aria-invalid", "true"); amt.focus(); return; }
        amt.removeAttribute("aria-invalid");
        const curName = cur.value === "dollars" ? "$" : "olmos";
        if (n >= 10000) {
          const c = await confirmBox({ title: "Katta miqdor", text: `${u.name} hisobiga ${sign > 0 ? "+" : "−"}${fmt(n)} ${curName}. Davom etilsinmi?`, ok: "Ha, davom et" });
          if (!c.ok) return;
        }
        await busy(btn, async () => {
          try {
            const r = await api(`/api/users/${u.id}/balance`, { method: "POST", json: { currency: cur.value, delta: sign * n, reason: why.value.trim(), notify: notify.checked } });
            vals[cur.value].textContent = fmt(r.value);
            toast(`${sign > 0 ? "Qo'shildi" : "Ayirildi"}: ${fmt(n)} ${curName}. Yangi balans: ${fmt(r.value)}`);
            amt.value = ""; why.value = "";
            refreshList();
          } catch (e) { err.textContent = e.message; }
        });
      };
      const addBtn = h("button", { type: "button", class: "btn success", style: { flex: "1 1 0" } }, icon("plus", 16), "Qo'shish");
      const subBtn = h("button", { type: "button", class: "btn", style: { flex: "1 1 0" } }, icon("minus", 16), "Ayirish");
      addBtn.addEventListener("click", () => submit(1, addBtn));
      subBtn.addEventListener("click", () => submit(-1, subBtn));
      parts.push(h("div", { class: "divider" }), h("h3", { text: "Balansni o'zgartirish" }),
        h("div", { class: "inline", style: { alignItems: "flex-end" } },
          h("div", { class: "field", style: { flex: "1 1 140px" } }, h("label", { for: "b-amt", text: "Miqdor" }), amt),
          h("div", { class: "field", style: { flex: "1 1 110px" } }, h("label", { for: "b-cur", text: "Valyuta" }), cur)),
        h("div", { class: "field" }, h("label", { for: "b-why", text: "Sabab (jurnalga yoziladi)" }), why),
        h("label", { class: "check-row", for: "b-ntf" }, notify, h("span", { text: "Foydalanuvchiga botda xabar yuborilsin" })),
        err, h("div", { class: "inline" }, addBtn, subBtn));
    }

    const itemRows = u.items.map((it) => {
      const qty = h("span", { class: "qty", text: String(it.qty) });
      const change = async (delta, btn) => {
        await busy(btn, async () => {
          try {
            const r = await api(`/api/users/${u.id}/item`, { method: "POST", json: { item: it.code, delta } });
            it.qty = r.qty; qty.textContent = String(r.qty); minus.disabled = r.qty <= 0;
          } catch (e) { fail(e); }
        });
        minus.disabled = it.qty <= 0;
      };
      const minus = h("button", { type: "button", class: "btn sm icon", "aria-label": `${it.name}: kamaytirish`, disabled: !can("owner") || it.qty <= 0 }, icon("minus", 16));
      const plus = h("button", { type: "button", class: "btn sm icon", "aria-label": `${it.name}: ko'paytirish`, disabled: !can("owner") }, icon("plus", 16));
      minus.addEventListener("click", () => change(-1, minus));
      plus.addEventListener("click", () => change(1, plus));
      return h("div", { class: "item-row" }, h("span", { class: "ellipsis", text: it.name }),
        h("div", { class: "inline" }, minus, qty, plus));
    });
    parts.push(h("div", { class: "divider" }), h("h3", { text: "Buyumlar" }), h("div", null, itemRows));

    // ---- PRO ----
    const reload = () => { if (alive(view)) loadDetail(box, uid, view, refreshList, listHref); };
    const proParts = [h("div", { class: "divider" }), h("h3", { text: "PRO" }),
      h("p", { class: "small", text: u.pro_until ? `PRO: ${fmtDate(u.pro_until)} gacha` : "PRO yo'q" })];
    if (u.nickname) proParts.push(h("p", { class: "small muted", text: `Nickname: ${u.nickname}` }));
    if (can("owner")) {
      const days = h("input", { class: "input num", id: "p-days", type: "number", inputmode: "numeric", min: "1", max: "3650", step: "1", value: "30" });
      const proErr = h("div", { class: "err", role: "alert" });
      const give = h("button", { type: "button", class: "btn success", style: { flex: "1 1 0" }, text: u.pro_until ? "PRO uzaytirish" : "PRO berish" });
      const take = h("button", { type: "button", class: "btn danger", style: { flex: "1 1 0" }, text: "PRO olib tashlash", disabled: !u.pro_until });
      const setPro = async (n, btn) => {
        proErr.textContent = "";
        await busy(btn, async () => {
          try {
            const r = await api(`/api/users/${u.id}/pro`, { method: "POST", json: { days: n, notify: n > 0 } });
            toast(r.pro_until ? `PRO: ${fmtDate(r.pro_until)} gacha` : "PRO olib tashlandi");
            refreshList();
          } catch (e) { proErr.textContent = e.message; }
        });
        reload();
      };
      give.addEventListener("click", () => {
        const n = Number(days.value);
        if (!Number.isInteger(n) || n < 1 || n > 3650) { proErr.textContent = "Kun 1 dan 3650 gacha butun son bo'lsin"; days.setAttribute("aria-invalid", "true"); days.focus(); return; }
        days.removeAttribute("aria-invalid");
        setPro(n, give);
      });
      take.addEventListener("click", async () => {
        const c = await confirmBox({ title: "PRO olib tashlash", text: `${u.name} PRO imkoniyatlaridan darhol mahrum bo'ladi.`, ok: "Olib tashlash", danger: true });
        if (c.ok) setPro(0, take);
      });
      proParts.push(h("div", { class: "field" }, h("label", { for: "p-days", text: "Necha kun (foydalanuvchiga botda xabar boradi)" }), days),
        proErr, h("div", { class: "inline" }, give, take));
    }
    if (u.nickname && can("moderator")) {
      const clr = h("button", { type: "button", class: "btn block", text: "Nickname'ni o'chirish" });
      clr.addEventListener("click", async () => {
        const c = await confirmBox({ title: "Nickname'ni o'chirish", text: `«${u.nickname}» o'chiriladi, o'yinlarda Telegram ismi ko'rinadi.`, ok: "O'chirish", danger: true });
        if (!c.ok) return;
        await busy(clr, async () => {
          try { await api(`/api/users/${u.id}/nickname`, { method: "POST", json: {} }); toast("Nickname o'chirildi"); } catch (e) { fail(e); }
        });
        reload();
      });
      proParts.push(clr);
    }
    parts.push(...proParts);

    if (can("moderator")) {
      const banBtn = h("button", { type: "button", class: `btn block ${u.banned ? "success" : "danger"}`, disabled: !!u.admin_role,
        text: u.banned ? "Bandan chiqarish" : "Ban qilish" });
      banBtn.addEventListener("click", async () => {
        const c = u.banned
          ? await confirmBox({ title: "Bandan chiqarish", text: `${u.name} yana botdan foydalana oladi.`, ok: "Bandan chiqarish" })
          : await confirmBox({ title: "Ban qilish", text: `${u.name} botdan foydalana olmaydi: o'yinga qo'shila olmaydi, buyruqlar ishlamaydi.`, ok: "Ban qilish", danger: true,
            input: { label: "Sabab (jurnalga yoziladi)", placeholder: "Masalan: spam, haqorat" } });
        if (!c.ok) return;
        await busy(banBtn, async () => {
          try {
            await api(`/api/users/${u.id}/ban`, { method: "POST", json: { banned: !u.banned, reason: c.value || "" } });
            toast(u.banned ? "Bandan chiqarildi" : "Ban qilindi");
            refreshList();
          } catch (e) { fail(e); }
        });
        if (alive(view)) loadDetail(box, uid, view, refreshList, listHref);
      });
      parts.push(h("div", { class: "divider" }), banBtn, u.admin_role ? h("p", { class: "hint", text: "Adminni ban qilib bo'lmaydi. Avval «Iqtisod va adminlar» bo'limida adminlikdan oling." }) : null);
    }

    parts.push(h("div", { class: "divider" }), h("h3", { text: "Oxirgi o'yinlar" }),
      u.history.length ? h("div", { class: "stack gap-8" }, u.history.map((g) => h("div", { class: "between" },
        h("div", { class: "stack", style: { gap: "2px", minWidth: "0" } }, h("span", { class: "ellipsis", text: roleName(g.role) }),
          h("span", { class: "small muted ellipsis", text: `${g.group} · ${fmtDate(g.at)}` })),
        chip(g.won ? "Yutdi" : "Yutqazdi", g.won ? "c-green" : "c-gray")))) : h("p", { class: "muted small", text: "Hali o'ynamagan." }));
    clear(box).append(...parts);
  }

  // ================= e'lon =================
  const AUD = [["users", "Hamma foydalanuvchilar"], ["active", "Faollar (7 kun)"], ["groups", "Hamma guruhlar"]];
  const BSTATUS = { running: ["Yuborilmoqda", "c-blue"], done: ["Tugadi", "c-green"], cancelled: ["To'xtatildi", "c-gray"], interrupted: ["Uzildi", "c-red"] };

  function tgRender(html) {
    // Telegram HTML'ini xavfsiz ko'rsatish: DOMParser skript ishlatmaydi, faqat ruxsat etilgan teglar ko'chiriladi.
    const doc = new DOMParser().parseFromString(`<!doctype html><body>${html}</body>`, "text/html");
    const map = { B: "b", STRONG: "b", I: "i", EM: "i", U: "u", INS: "u", S: "s", STRIKE: "s", DEL: "s", CODE: "code", PRE: "pre", BLOCKQUOTE: "blockquote" };
    const out = document.createDocumentFragment();
    let length = 0;
    (function walk(src, dst) {
      for (const n of src.childNodes) {
        if (n.nodeType === 3) { dst.append(n.textContent); length += n.textContent.length; }
        else if (n.nodeType === 1) {
          let el;
          if (n.tagName === "A") {
            const href = n.getAttribute("href") || "";
            el = /^(https?:\/\/|tg:\/\/)/i.test(href) ? h("a", { href, target: "_blank", rel: "noopener noreferrer" }) : h("span");
          } else if (n.tagName === "TG-SPOILER") el = h("span", { class: "spoiler" });
          else if (map[n.tagName]) el = h(map[n.tagName]);
          else el = document.createDocumentFragment();
          walk(n, el);
          dst.append(el);
        }
      }
    })(doc.body, out);
    return { node: out, length };
  }
  const plainText = (html) => new DOMParser().parseFromString(`<body>${html}</body>`, "text/html").body.textContent || "";

  function pageBroadcast(root, { view }) {
    const owner = can("owner");
    const form = h("section", { class: "card f3" }, skel(6, 30));
    const side = h("div", { class: "stack f2" });
    const preview = h("section", { class: "card" });
    const histCard = h("section", { class: "card" }, h("h2", { text: "Tarix" }), skel(3, 40));
    side.append(owner ? preview : null, histCard);
    root.append(head("Xabar yuborish", "Foydalanuvchilarga yoki guruhlarga e'lon. Tezlik ~20 xabar/soniya — o'yinlar sekinlashmasligi uchun."),
      h("div", { class: "row", style: { alignItems: "flex-start" } }, owner ? form : null, side));
    const st = { audience: "users", photo: null, photoUrl: null, buttons: [], counts: { users: 0, active: 0, groups: 0 }, running: null };

    const text = h("textarea", { class: "input", id: "bc-text", rows: "7", maxlength: "8000", placeholder: "E'lon matni. Qalin, kursiv va havola uchun yuqoridagi tugmalardan foydalaning." });
    const counter = h("div", { class: "small muted num right" });
    const err = h("div", { class: "err", role: "alert" });
    const audBox = h("div", { class: "radio-cards" });
    const photoBox = h("div", { class: "inline" });
    const btnBox = h("div", { class: "stack gap-8" });
    const fileIn = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp", class: "sr", id: "bc-file", tabindex: "-1" });
    const sendBtn = h("button", { type: "button", class: "btn primary", style: { flex: "2 1 220px" } });
    const testBtn = h("button", { type: "button", class: "btn", style: { flex: "1 1 160px" }, text: "O'zimga sinov" });

    const limit = () => (st.photo ? 1024 : 4096);
    function update() {
      const { node, length } = tgRender(text.value);
      counter.textContent = `${fmt(length)} / ${fmt(limit())}`;
      counter.style.color = length > limit() ? "#FF8A8A" : "";
      const total = st.counts[st.audience] || 0;
      clear(sendBtn).append(icon("send", 16), `${fmt(total)} ${st.audience === "groups" ? "guruhga" : "kishiga"} yuborish`);
      sendBtn.disabled = !!st.running || !total;
      clear(preview).append(h("h2", { text: "Telegramda shunday ko'rinadi" }),
        h("div", { class: "tg" },
          h("div", { class: "tg-bubble" }, st.photoUrl ? h("img", { src: st.photoUrl, alt: "" }) : null,
            text.value.trim() ? h("div", { class: "tg-text" }, node) : (st.photoUrl ? null : h("div", { class: "tg-text muted", text: "Matn shu yerda ko'rinadi" })),
            h("div", { class: "tg-time", text: TF.format(new Date()) })),
          st.buttons.filter((b) => b.text.trim()).map((b) => h("div", { class: "tg-btn", text: b.text }))));
    }
    function wrap(open, close) {
      const a = text.selectionStart, b = text.selectionEnd, v = text.value;
      text.value = v.slice(0, a) + open + v.slice(a, b) + close + v.slice(b);
      text.focus();
      text.setSelectionRange(a + open.length, b + open.length);
      update();
    }
    async function addLink() {
      const c = await confirmBox({ title: "Havola qo'shish", ok: "Qo'shish", input: { label: "Manzil (https://...)", placeholder: "https://t.me/kanal", required: true, max: 500 } });
      if (!c.ok) return;
      if (!/^(https?:\/\/|tg:\/\/)\S+$/i.test(c.value)) { toast("Havola https:// yoki tg:// bilan boshlansin", "bad"); return; }
      wrap(`<a href="${c.value.replace(/"/g, "%22")}">`, "</a>");
    }
    function drawAud() {
      clear(audBox).append(AUD.map(([k, label]) => h("label", { class: "radio-card" },
        h("input", { type: "radio", name: "aud", value: k, checked: st.audience === k, onChange: () => { st.audience = k; update(); } }),
        h("span", { class: "stack", style: { gap: "4px" } }, h("b", { text: label }),
          h("span", { class: "small muted num", text: `${fmt(st.counts[k])} ${k === "groups" ? "guruh" : "kishi"}` })))));
    }
    function drawPhoto() {
      clear(photoBox).append(st.photoUrl
        ? h("div", { class: "inline" }, h("div", { class: "thumb" }, h("img", { src: st.photoUrl, alt: "Tanlangan rasm" })),
          h("button", { type: "button", class: "btn sm danger-soft", onClick: () => { if (st.photoUrl) URL.revokeObjectURL(st.photoUrl); st.photo = null; st.photoUrl = null; fileIn.value = ""; drawPhoto(); update(); } }, icon("x", 14), "Olib tashlash"))
        : h("label", { class: "btn sm", for: "bc-file" }, icon("img", 16), "Rasm qo'shish"));
    }
    fileIn.addEventListener("change", () => {
      const f = fileIn.files && fileIn.files[0];
      if (!f) return;
      if (!["image/jpeg", "image/png", "image/webp"].includes(f.type)) { toast("Rasm JPG, PNG yoki WEBP bo'lsin", "bad"); fileIn.value = ""; return; }
      if (f.size > 10 * 1024 * 1024) { toast("Rasm 10 MB dan katta", "bad"); fileIn.value = ""; return; }
      if (st.photoUrl) URL.revokeObjectURL(st.photoUrl);
      st.photo = f; st.photoUrl = URL.createObjectURL(f);
      drawPhoto(); update();
    });
    function drawButtons() {
      clear(btnBox).append(st.buttons.map((b, i) => {
        const t = h("input", { class: "input", id: `bt-${i}`, maxlength: 64, value: b.text, placeholder: "O'yinni guruhga qo'shish" });
        const u = h("input", { class: "input mono", id: `bu-${i}`, maxlength: 512, value: b.url, placeholder: "https://t.me/..." });
        t.addEventListener("input", () => { b.text = t.value; update(); });
        u.addEventListener("input", () => { b.url = u.value.trim(); });
        return h("div", { class: "btn-row" },
          h("div", { class: "field" }, h("label", { for: `bt-${i}`, text: "Tugma matni" }), t),
          h("div", { class: "field" }, h("label", { for: `bu-${i}`, text: "Havola" }), u),
          h("button", { type: "button", class: "btn icon danger-soft", "aria-label": "Tugmani o'chirish", onClick: () => { st.buttons.splice(i, 1); drawButtons(); update(); } }, icon("x", 16)));
      }), st.buttons.length < 6 ? h("button", { type: "button", class: "btn sm dashed", onClick: () => {
        st.buttons.push({ text: "", url: S.bot ? `https://t.me/${S.bot}?startgroup=true` : "" }); drawButtons(); update();
        const last = document.getElementById(`bt-${st.buttons.length - 1}`); if (last) last.focus();
      } }, icon("plus", 14), "Tugma qo'shish") : h("p", { class: "hint", text: "Ko'pi bilan 6 ta tugma." }));
    }
    function validate() {
      err.textContent = "";
      const { length } = tgRender(text.value);
      if (!text.value.trim() && !st.photo) return "Matn yozing yoki rasm qo'shing";
      if (length > limit()) return `Matn ${fmt(limit())} belgidan oshmasin${st.photo ? " (rasm izohi uchun Telegram limiti)" : ""}`;
      for (const b of st.buttons) {
        if (!b.text.trim()) return "Har bir tugmaga matn yozing (yoki keraksizini o'chiring)";
        if (!/^(https?:\/\/|tg:\/\/)\S+$/i.test(b.url)) return `«${b.text}» havolasi https:// yoki tg:// bilan boshlansin`;
      }
      return "";
    }
    function formData(test) {
      const fd = new FormData();
      fd.append("audience", st.audience);
      fd.append("text", text.value);
      fd.append("buttons", JSON.stringify(st.buttons.map((b) => ({ text: b.text.trim(), url: b.url.trim() }))));
      fd.append("test", test ? "1" : "0");
      if (st.photo) fd.append("photo", st.photo, st.photo.name || "photo.jpg");
      return fd;
    }
    testBtn.addEventListener("click", () => {
      const v = validate(); if (v) { err.textContent = v; return; }
      busy(testBtn, async () => {
        try { await api("/api/broadcast", { method: "POST", form: formData(true) }); toast("Sinov xabari botda sizga yuborildi. Telegramda tekshiring."); }
        catch (e) { err.textContent = e.message; }
      });
    });
    sendBtn.addEventListener("click", async () => {
      const v = validate(); if (v) { err.textContent = v; return; }
      const total = st.counts[st.audience];
      const c = await confirmBox({ title: "E'lonni yuborish", ok: "Ha, yuborish", danger: true,
        text: `${fmt(total)} ${st.audience === "groups" ? "guruhga" : "kishiga"} yuboriladi. Yuborilgan xabarni qaytarib bo'lmaydi. Avval «O'zimga sinov» bilan tekshirganingizga ishonch hosil qiling.` });
      if (!c.ok) return;
      busy(sendBtn, async () => {
        try {
          const r = await api("/api/broadcast", { method: "POST", form: formData(false) });
          toast(`E'lon yuborilmoqda: ${fmt(r.total)} ta qabul qiluvchi`);
          text.value = ""; st.buttons = []; if (st.photoUrl) URL.revokeObjectURL(st.photoUrl); st.photo = null; st.photoUrl = null; fileIn.value = "";
          drawButtons(); drawPhoto();
          loadInfo();
        } catch (e) { err.textContent = e.message; }
      }).then(update);
    });
    text.addEventListener("input", update);

    const tb = (label, aria, fn, extra) => h("button", { type: "button", class: "btn sm", "aria-label": aria, title: aria, onClick: fn, ...(extra || {}) }, label);
    if (owner) {
      clear(form).append(
        h("fieldset", { class: "stack gap-12", style: { border: "0", margin: "0", padding: "0" } }, h("legend", { class: "sr", text: "Kimga" }), h("h2", { text: "Kimga" }), audBox),
        h("div", { class: "stack gap-8" }, h("label", { for: "bc-text" }, h("h2", { text: "Matn" })),
          h("div", { class: "toolbar", role: "toolbar", "aria-label": "Formatlash" },
            tb(h("b", { text: "B" }), "Qalin", () => wrap("<b>", "</b>")),
            tb(h("i", { text: "I" }), "Kursiv", () => wrap("<i>", "</i>")),
            tb(h("u", { text: "U" }), "Tagiga chizilgan", () => wrap("<u>", "</u>")),
            tb(h("s", { text: "S" }), "Ustidan chizilgan", () => wrap("<s>", "</s>")),
            tb("Spoiler", "Yashirin matn", () => wrap("<tg-spoiler>", "</tg-spoiler>")),
            tb(h("span", { class: "mono", text: "</>" }), "Kod", () => wrap("<code>", "</code>")),
            tb(icon("link", 16), "Havola", addLink)),
          text, counter),
        h("div", { class: "stack gap-8" }, h("h2", { text: "Rasm" }), fileIn, photoBox, h("p", { class: "hint", text: "Ixtiyoriy. Rasm bilan matn 1024 belgigacha bo'ladi." })),
        h("div", { class: "stack gap-8" }, h("h2", { text: "Tugmalar" }), btnBox),
        err,
        h("div", { class: "inline divider", style: { paddingTop: "16px" } }, testBtn, sendBtn));
      drawPhoto(); drawButtons();
    }

    let polling = false;
    async function loadInfo() {
      let d;
      try { d = await api("/api/broadcast"); } catch (e) { if (alive(view)) clear(histCard).append(h("h2", { text: "Tarix" }), errorCard(e, loadInfo)); return; }
      if (!alive(view)) return;
      st.counts = d.counts; st.running = d.running;
      if (owner) { drawAud(); update(); }
      clear(histCard).append(h("h2", { text: "Tarix" }), d.history.length ? h("div", { class: "stack" }, d.history.map((b) => {
        const [sl, sc] = BSTATUS[b.status] || [b.status, "c-gray"];
        const done = b.sent + b.blocked + b.failed;
        const pct = (x) => `${b.total ? (x / b.total) * 100 : 0}%`;
        const cancel = b.status === "running" && owner ? h("button", { type: "button", class: "btn sm danger-soft", text: "To'xtatish" }) : null;
        if (cancel) cancel.addEventListener("click", async () => {
          const c = await confirmBox({ title: "E'lonni to'xtatish", text: "Qolganlarga yuborilmaydi. Yuborilganlari qaytarilmaydi.", ok: "To'xtatish", danger: true });
          if (!c.ok) return;
          busy(cancel, async () => { try { await api(`/api/broadcast/${b.id}/cancel`, { method: "POST" }); toast("To'xtatilmoqda..."); loadInfo(); } catch (e) { fail(e); } });
        });
        const excerpt = plainText(b.text).trim() || (b.photo ? "(rasm)" : "(bo'sh)");
        return h("div", { class: "sub" },
          h("div", { class: "between" }, h("span", { class: "ellipsis", style: { flex: "1 1 160px" }, text: excerpt, title: excerpt }), chip(sl, sc)),
          h("div", { class: "bar multi" }, h("div", { style: { width: pct(b.sent), background: "#4ADE98" } }), h("div", { style: { width: pct(b.blocked), background: "#F2C25B" } }), h("div", { style: { width: pct(b.failed), background: "#FF6B6B" } })),
          h("div", { class: "small muted num", text: `${fmt(done)} / ${fmt(b.total)} · yetdi ${fmt(b.sent)} · bloklagan ${fmt(b.blocked)} · xato ${fmt(b.failed)}` }),
          h("div", { class: "between small muted" }, h("span", { text: `${AUD.find(([k]) => k === b.audience)?.[1] || b.audience} · ${ago(b.created_at)}` }), cancel));
      })) : empty("Hali e'lon yuborilmagan."));
      if (d.running && !polling) {
        polling = true;
        const id = setInterval(async () => { if (!alive(view)) { clearInterval(id); return; } await loadInfo(); if (!st.running) { clearInterval(id); polling = false; } }, 2500);
        S.timers.push(id);
      }
    }
    loadInfo();
  }

  // ================= o'yinlar va guruhlar =================
  const RIGHTS = { full: ["To'liq admin", "c-green"], partial: ["Huquqlar yetarli emas", "c-gold"], member: ["Admin emas", "c-red"], none: ["Bot chiqarilgan", "c-gray"], unknown: ["Noma'lum", "c-gray"] };
  const SORTS = [["week", "Hafta o'yinlari"], ["total", "Jami o'yinlar"], ["new", "Yangi qo'shilgan"]];

  function pageGames(root, { view }) {
    const liveCard = h("section", { class: "card" }, h("h2", { text: "Jonli o'yinlar" }), skel(4, 36));
    const groupCard = h("section", { class: "card" });
    root.append(head("O'yinlar va guruhlar", "Jonli o'yinlarni kuzatish va to'xtatish, guruh sozlamalari"), liveCard, groupCard);

    async function loadLive() {
      let d;
      try { d = await api("/api/games"); } catch (e) { if (alive(view)) clear(liveCard).append(h("h2", { text: "Jonli o'yinlar" }), errorCard(e, loadLive)); return; }
      if (!alive(view)) return;
      const title = h("div", { class: "between" }, h("h2", { class: "inline" }, h("span", { class: "live-dot" }), `Jonli o'yinlar · ${d.items.length}`),
        h("span", { class: "small muted", text: "Har 10 soniyada yangilanadi" }));
      if (!d.items.length) { clear(liveCard).append(title, empty("Hozir hech qayerda o'yin yoki ro'yxat ochiq emas.")); return; }
      clear(liveCard).append(title, h("div", { class: "table-wrap" }, h("table", { class: "t cards" },
        h("thead", null, h("tr", null, ["Guruh", "Holat", "Kun", "Tirik / Jami", "Mafiya", "Davomiyligi", ""].map((t) => h("th", { text: t })))),
        h("tbody", null, d.items.map((g) => {
          const [pl, pc] = PHASE[g.phase] || [g.phase, "c-gray"];
          const acts = h("td", { class: "acts wide" });
          if (can("moderator")) {
            const rolesBtn = h("button", { type: "button", class: "btn sm", text: g.phase === "lobby" ? "Ro'yxat" : "Rollar" });
            rolesBtn.addEventListener("click", () => busy(rolesBtn, () => showPlayers(g)));
            const stopBtn = h("button", { type: "button", class: "btn sm danger-soft", text: "To'xtatish" });
            stopBtn.addEventListener("click", async () => {
              const c = await confirmBox({ title: "O'yinni to'xtatish", text: `«${g.title}» guruhidagi ${g.phase === "lobby" ? "ro'yxat yopiladi" : "o'yin to'xtatiladi, hech kimga mukofot berilmaydi"}. Guruhga xabar boradi.`, ok: "To'xtatish", danger: true, input: { label: "Sabab (guruhga ham ko'rsatiladi)", placeholder: "Masalan: o'yin osilib qoldi" } });
              if (!c.ok) return;
              busy(stopBtn, async () => { try { await api(`/api/games/${g.chat_id}/stop`, { method: "POST", json: { reason: c.value } }); toast("To'xtatildi"); loadLive(); } catch (e) { fail(e); } });
            });
            acts.append(rolesBtn, stopBtn);
          }
          return h("tr", null,
            h("td", { class: "wide" }, h("b", { text: g.title }), h("div", { class: "small muted mono", text: String(g.chat_id) })),
            h("td", { "data-label": "Holat" }, chip(pl, pc)),
            h("td", { class: "num", "data-label": "Kun", text: g.phase === "lobby" ? "—" : String(g.day) }),
            h("td", { class: "num", "data-label": "Tirik / Jami", text: g.phase === "lobby" ? `${g.total} qo'shildi` : `${g.alive} / ${g.total}` }),
            h("td", { class: "num", "data-label": "Mafiya", text: g.mafia === null ? "—" : String(g.mafia) }),
            h("td", { class: "num muted", "data-label": "Davomiyligi", text: g.phase === "lobby" ? `${g.lobby_left || 0} s qoldi` : elapsed(g.started) }),
            acts);
        })))));
    }
    async function showPlayers(g) {
      let d;
      try { d = await api(`/api/games/${g.chat_id}/players`); } catch (e) { fail(e); return; }
      const teamChip = (t) => ({ town: chip("Tinch", "c-blue"), mafia: chip("Mafiya", "c-red"), neutral: chip("Neytral", "c-violet") }[t] || null);
      modal([
        h("div", { class: "between" }, h("h2", { text: `${d.title || g.title} · ${d.lobby ? "ro'yxat" : "rollar"}` }),
          h("button", { type: "button", class: "btn icon ghost", "aria-label": "Yopish", onClick: closeModal }, icon("x"))),
        d.lobby ? null : h("div", { class: "alert info", text: "Rollar sir. Ularni o'yinchilarga aytmang — ko'rganingiz jurnalga yozildi." }),
        h("div", { class: "table-wrap" }, h("table", { class: "t" }, h("tbody", null, d.players.map((p) => h("tr", null,
          h("td", null, h("a", { href: `#/users/${p.id}`, onClick: closeModal, text: p.name })),
          h("td", { text: p.role ? roleName(p.role) : "" }),
          h("td", null, teamChip(p.team)),
          h("td", { class: "right" }, d.lobby ? null : chip(p.alive ? "Tirik" : "O'lgan", p.alive ? "c-green" : "c-gray"))))))),
      ], { wide: true });
    }

    const gs = { q: "", sort: "week", page: 0 };
    const gq = h("input", { class: "input", type: "search", id: "gq", placeholder: "Guruh nomi yoki ID", maxlength: 64, autocomplete: "off" });
    const sortSel = h("select", { class: "input", id: "gsort" }, SORTS.map(([v, t]) => h("option", { value: v, text: t })));
    const gBody = h("div", null, skel(5, 36));
    clear(groupCard).append(h("div", { class: "between", style: { alignItems: "flex-end" } }, h("h2", { text: "Guruhlar" }),
      h("div", { class: "inline", style: { alignItems: "flex-end" } },
        h("div", { class: "field", style: { flex: "1 1 220px" } }, h("label", { for: "gq", text: "Qidirish" }), gq),
        h("div", { class: "field" }, h("label", { for: "gsort", text: "Saralash" }), sortSel))), gBody);
    let gt;
    gq.addEventListener("input", () => { clearTimeout(gt); gt = setTimeout(() => { gs.q = gq.value.trim(); gs.page = 0; loadGroups(); }, 300); });
    sortSel.addEventListener("change", () => { gs.sort = sortSel.value; gs.page = 0; loadGroups(); });
    let greq = 0;
    async function loadGroups() {
      const my = ++greq;
      let d;
      try { d = await api(`/api/groups?q=${encodeURIComponent(gs.q)}&sort=${gs.sort}&page=${gs.page}`); } catch (e) { if (alive(view)) clear(gBody).append(errorCard(e, loadGroups)); return; }
      if (!alive(view) || my !== greq) return;
      if (!d.items.length) { clear(gBody).append(empty(gs.q ? "Hech narsa topilmadi." : "Bot hali hech qaysi guruhga qo'shilmagan.")); return; }
      clear(gBody).append(h("div", { class: "table-wrap" }, h("table", { class: "t cards" },
        h("thead", null, h("tr", null, h("th", { text: "#" }), h("th", { text: "Guruh" }), h("th", { class: "right", text: "A'zolar" }), h("th", { class: "right", text: "Hafta" }),
          h("th", { class: "right", text: "Jami" }), h("th", { text: "Bot huquqi" }), h("th", { text: "" }))),
        h("tbody", null, d.items.map((g, i) => {
          const [rl, rc] = RIGHTS[g.rights] || RIGHTS.unknown;
          const acts = h("td", { class: "acts wide" });
          const setBtn = h("button", { type: "button", class: "btn sm", text: can("owner") ? "Sozlamalar" : "Ko'rish", onClick: () => groupSettings(g, loadGroups) });
          acts.append(setBtn);
          if (can("owner") && g.rights !== "none") {
            const leave = h("button", { type: "button", class: "btn sm danger-soft", text: "Botni chiqarish" });
            leave.addEventListener("click", async () => {
              const c = await confirmBox({ title: "Botni guruhdan chiqarish", text: `Bot «${g.title}» guruhidan chiqadi${g.live ? ", ketayotgan o'yin to'xtatiladi" : ""}. Qaytarish uchun guruh adminlari botni qayta qo'shishi kerak.`, ok: "Chiqarish", danger: true });
              if (!c.ok) return;
              busy(leave, async () => { try { await api(`/api/groups/${g.chat_id}/leave`, { method: "POST", json: {} }); toast("Bot guruhdan chiqdi"); loadGroups(); } catch (e) { fail(e); } });
            });
            acts.append(leave);
          }
          return h("tr", null,
            h("td", { class: "num muted", "data-label": "#", text: String(d.page * d.size + i + 1) }),
            h("td", { class: "wide" }, h("div", { class: "inline" }, h("b", { text: g.title || "(nomsiz)" }), g.live ? chip("O'yin ketyapti", "c-blue") : null),
              h("div", { class: "small muted mono", text: String(g.chat_id) })),
            h("td", { class: "right num", "data-label": "A'zolar", text: fmt(g.members) }),
            h("td", { class: "right num", "data-label": "Hafta", text: fmt(g.week) }),
            h("td", { class: "right num", "data-label": "Jami", text: fmt(g.total) }),
            h("td", { "data-label": "Bot huquqi" }, chip(rl, rc)),
            acts);
        })))), pager(d.page, d.size, d.total, (p) => { gs.page = p; loadGroups(); }));
    }
    loadLive(); loadGroups();
    every(10000, loadLive);
  }

  const GSET = [["lobby", "Ro'yxat vaqti", 30, 600], ["night", "Tun", 15, 300], ["day", "Kun (muhokama)", 15, 600], ["vote", "Ovoz berish", 15, 300]];
  const GFLAGS = [["items", "Buyumlar ishlaydi"], ["afk", "AFK o'yinchilarni chiqarish"], ["confirm", "Osishdan oldin 👍/👎 tasdiq"]];
  function groupSettings(g, reload) {
    const owner = can("owner");
    const inputs = {}, flags = {};
    const err = h("div", { class: "err", role: "alert" });
    const saveBtn = h("button", { type: "button", class: "btn primary", text: "Saqlash", disabled: !owner });
    modal([
      h("div", { class: "between" }, h("h2", { text: `${g.title} · sozlamalar` }), h("button", { type: "button", class: "btn icon ghost", "aria-label": "Yopish", onClick: closeModal }, icon("x"))),
      h("div", { class: "stat-grid" }, GSET.map(([k, label, lo, hi]) => {
        inputs[k] = h("input", { class: "input num", id: `gs-${k}`, type: "number", min: lo, max: hi, step: "1", value: g.settings[k], disabled: !owner });
        return h("div", { class: "field" }, h("label", { for: `gs-${k}`, text: `${label}, soniya (${lo}–${hi})` }), inputs[k]);
      })),
      h("div", null, GFLAGS.map(([k, label]) => {
        flags[k] = h("input", { type: "checkbox", class: "switch", id: `gf-${k}`, checked: !!g.settings[k], disabled: !owner });
        return h("label", { class: "check-row", for: `gf-${k}` }, flags[k], h("span", { text: label }));
      })),
      h("p", { class: "hint", text: "O'zgarishlar keyingi o'yindan kuchga kiradi. Rollarni yoqish/o'chirish guruhda /settings orqali." }),
      err,
      h("div", { class: "modal-actions" }, h("button", { type: "button", class: "btn", text: "Yopish", onClick: closeModal }), owner ? saveBtn : null),
    ]);
    saveBtn.addEventListener("click", () => {
      err.textContent = "";
      const payload = {};
      for (const [k, label, lo, hi] of GSET) {
        const n = Number(inputs[k].value);
        if (!Number.isInteger(n) || n < lo || n > hi) { err.textContent = `${label}: ${lo} dan ${hi} gacha butun son`; inputs[k].focus(); return; }
        payload[k] = n;
      }
      for (const [k] of GFLAGS) payload[k] = flags[k].checked;
      busy(saveBtn, async () => {
        try { await api(`/api/groups/${g.chat_id}/settings`, { method: "POST", json: payload }); toast("Saqlandi"); closeModal(); reload(); }
        catch (e) { err.textContent = e.message; }
      });
    });
  }

  // ================= iqtisod, adminlar, jurnal =================
  const ECON = [["reward_win", "G'alaba mukofoti", "O'yinda yutgan har bir o'yinchiga", 0, 100000, "$"],
    ["reward_play", "Ishtirok mukofoti", "Yutqazganga ham beriladi (0 — faqat yutganlar oladi)", 0, 100000, "$"],
    ["ref_bonus", "Taklif bonusi", "Taklif qilingan do'st 3 ta o'yin o'ynagach", 0, 100000, "$"],
    ["diamond_rate", "Olmos kursi", "1 olmos necha dollarga almashadi", 1, 1000000, "$"]];

  function pageEconomy(root, { view }) {
    const owner = can("owner");
    const econCard = h("section", { class: "card f1" }, h("h2", { text: "Mukofotlar" }), skel(5, 40));
    const shopCard = h("section", { class: "card f1" }, h("h2", { text: "Do'kon" }), skel(4, 40));
    const saveBtn = h("button", { type: "button", class: "btn primary", text: "O'zgarishlarni saqlash", disabled: true });
    const resetBtn = h("button", { type: "button", class: "btn", text: "Bekor qilish", disabled: true });
    const err = h("div", { class: "err", role: "alert" });
    const adminCard = owner ? h("section", { class: "card f1" }, h("h2", { text: "Adminlar" }), skel(3, 44)) : null;
    const logCard = h("section", { class: owner ? "card f1" : "card" }, h("h2", { text: "Amallar jurnali" }), skel(6, 30));
    root.append(head("Iqtisod va adminlar", owner ? "O'zgarishlar darhol kuchga kiradi — botni qayta ishga tushirish shart emas" : "Ko'rish rejimi: o'zgartirish faqat bosh admin uchun",
      owner ? resetBtn : null, owner ? saveBtn : null), err,
      h("div", { class: "row", style: { alignItems: "flex-start" } }, econCard, shopCard),
      h("div", { class: "row", style: { alignItems: "flex-start" } }, adminCard, logCard));

    let base = null;
    const inputs = {}, prices = {}, onSale = {};
    function current() {
      const v = {};
      for (const [k] of ECON) v[k] = inputs[k].value.trim();
      v.shop = {}; for (const k of Object.keys(prices)) v.shop[k] = prices[k].value.trim();
      v.shop_off = Object.keys(onSale).filter((k) => !onSale[k].checked).sort();
      return v;
    }
    function dirty() { return base && JSON.stringify(current()) !== JSON.stringify(base); }
    function refresh() { const d = dirty(); saveBtn.disabled = !d; resetBtn.disabled = !d; }
    function fill(values) {
      base = { ...Object.fromEntries(ECON.map(([k]) => [k, String(values[k])])), shop: Object.fromEntries(Object.entries(values.shop).map(([k, p]) => [k, String(p)])), shop_off: [...values.shop_off].sort() };
      clear(econCard).append(h("h2", { text: "Mukofotlar" }), ECON.map(([k, label, hint, lo, hi, unit]) => {
        inputs[k] = h("input", { class: "input num", id: `ec-${k}`, type: "number", inputmode: "numeric", min: lo, max: hi, step: "1", value: values[k], disabled: !owner, style: { width: "120px" } });
        inputs[k].addEventListener("input", refresh);
        return h("div", { class: "between" }, h("div", { class: "stack", style: { gap: "2px", flex: "1 1 200px" } }, h("label", { for: `ec-${k}`, text: label }), h("span", { class: "hint", text: hint })),
          h("div", { class: "inline" }, inputs[k], h("span", { class: "muted", text: unit })));
      }));
      clear(shopCard).append(h("h2", { text: "Do'kon" }), Object.entries(values.shop).map(([k, p]) => {
        const item = S.me.items[k] || { name: k, about: "" };
        prices[k] = h("input", { class: "input num", id: `sp-${k}`, type: "number", inputmode: "numeric", min: "1", max: "1000000", step: "1", value: p, disabled: !owner, style: { width: "110px" } });
        onSale[k] = h("input", { type: "checkbox", class: "switch", id: `so-${k}`, checked: !values.shop_off.includes(k), disabled: !owner, "aria-label": `${item.name}: sotuvda` });
        prices[k].addEventListener("input", refresh); onSale[k].addEventListener("change", refresh);
        return h("div", { class: "between" }, h("div", { class: "stack", style: { gap: "2px", flex: "1 1 200px" } }, h("label", { for: `sp-${k}`, text: item.name }), h("span", { class: "hint", text: item.about })),
          h("div", { class: "inline" }, prices[k], h("span", { class: "muted", text: "$" }), h("label", { class: "check-row", for: `so-${k}` }, onSale[k], h("span", { class: "small", text: "Sotuvda" }))));
      }));
      refresh();
    }
    async function loadEcon() {
      try { const d = await api("/api/economy"); if (alive(view)) fill(d.values); } catch (e) { if (alive(view)) clear(econCard).append(errorCard(e, loadEcon)); }
    }
    resetBtn.addEventListener("click", () => loadEcon());
    saveBtn.addEventListener("click", () => {
      err.textContent = "";
      const v = current();
      const payload = { shop: {}, shop_off: v.shop_off };
      for (const [k, label, , lo, hi] of ECON) {
        const n = Number(v[k]);
        if (v[k] === "" || !Number.isInteger(n) || n < lo || n > hi) { err.textContent = `${label}: ${lo} dan ${fmt(hi)} gacha butun son kiriting`; inputs[k].setAttribute("aria-invalid", "true"); inputs[k].focus(); return; }
        inputs[k].removeAttribute("aria-invalid");
        payload[k] = n;
      }
      for (const [k, raw] of Object.entries(v.shop)) {
        const n = Number(raw);
        if (raw === "" || !Number.isInteger(n) || n < 1 || n > 1e6) { err.textContent = `${(S.me.items[k] || {}).name || k}: narx 1 dan 1 000 000 gacha`; prices[k].focus(); return; }
        payload.shop[k] = n;
      }
      busy(saveBtn, async () => {
        try { const d = await api("/api/economy", { method: "POST", json: payload }); fill(d.values); toast("Saqlandi. Bot yangi qiymatlarni darhol ishlatadi."); loadLog(0); }
        catch (e) { err.textContent = e.message; }
      }).then(refresh);
    });
    window.addEventListener("beforeunload", (e) => { if (alive(view) && dirty()) { e.preventDefault(); e.returnValue = ""; } }, { once: true });

    async function loadAdmins() {
      if (!adminCard) return;
      let d;
      try { d = await api("/api/admins"); } catch (e) { if (alive(view)) clear(adminCard).append(h("h2", { text: "Adminlar" }), errorCard(e, loadAdmins)); return; }
      if (!alive(view)) return;
      const who = h("input", { class: "input", id: "ad-who", placeholder: "Telegram ID yoki @username", maxlength: 64, autocomplete: "off" });
      const role = h("select", { class: "input", id: "ad-role" }, h("option", { value: "moderator", text: "Moderator" }), h("option", { value: "viewer", text: "Kuzatuvchi" }));
      const addBtn = h("button", { type: "button", class: "btn primary" }, icon("plus", 16), "Qo'shish");
      const aerr = h("div", { class: "err", role: "alert" });
      addBtn.addEventListener("click", () => {
        aerr.textContent = "";
        const v = who.value.trim();
        if (!/^(@[A-Za-z0-9_]{3,32}|\d{3,18})$/.test(v)) { aerr.textContent = "Raqamli Telegram ID yoki @username kiriting"; who.focus(); return; }
        busy(addBtn, async () => { try { await api("/api/admins", { method: "POST", json: { who: v, role: role.value } }); toast("Admin qo'shildi. U botga /panel yozib kira oladi."); loadAdmins(); loadLog(0); } catch (e) { aerr.textContent = e.message; } });
      });
      clear(adminCard).append(h("h2", { text: "Adminlar" }),
        h("div", { class: "stack gap-8" }, d.items.map((a) => {
          const right = h("div", { class: "inline" });
          if (a.role === "owner") right.append(chip("Bosh admin", "c-gold"));
          else {
            const sel = h("select", { class: "input", "aria-label": `${a.name || a.id}: rol`, style: { width: "auto", minHeight: "36px" } },
              h("option", { value: "moderator", text: "Moderator" }), h("option", { value: "viewer", text: "Kuzatuvchi" }));
            sel.value = a.role;
            sel.addEventListener("change", async () => {
              try { await api("/api/admins", { method: "POST", json: { who: String(a.id), role: sel.value } }); toast("Rol o'zgardi"); loadLog(0); } catch (e) { fail(e); sel.value = a.role; }
            });
            const rm = h("button", { type: "button", class: "btn sm icon danger-soft", "aria-label": `${a.name || a.id}: adminlikdan olish` }, icon("x", 16));
            rm.addEventListener("click", async () => {
              const c = await confirmBox({ title: "Adminlikdan olish", text: `${a.name || a.id} panelga kira olmaydi (15 soniya ichida chiqariladi).`, ok: "Olib tashlash", danger: true });
              if (!c.ok) return;
              busy(rm, async () => { try { await api(`/api/admins/${a.id}`, { method: "DELETE" }); toast("Adminlikdan olindi"); loadAdmins(); loadLog(0); } catch (e) { fail(e); } });
            });
            right.append(sel, rm);
          }
          return h("div", { class: "sub", style: { flexDirection: "row", alignItems: "center", gap: "12px", padding: "12px" } },
            h("div", { class: "avatar round", text: initial(a.name) }),
            h("div", { class: "stack", style: { gap: "2px", flex: "1 1 auto", minWidth: "0" } },
              h("a", { class: "ellipsis", href: `#/users/${a.id}`, style: { color: "#EDEDEF" }, text: a.name || String(a.id) }),
              h("span", { class: "small muted mono", text: a.username ? `@${a.username}` : String(a.id) })),
            right);
        })),
        h("div", { class: "divider" }), h("h3", { text: "Yangi admin" }),
        h("div", { class: "inline", style: { alignItems: "flex-end" } },
          h("div", { class: "field", style: { flex: "2 1 200px" } }, h("label", { for: "ad-who", text: "Kim" }), who),
          h("div", { class: "field", style: { flex: "1 1 130px" } }, h("label", { for: "ad-role", text: "Rol" }), role), addBtn), aerr,
        h("p", { class: "hint", text: "Moderator: foydalanuvchilarni ban qilish, o'yinlarni to'xtatish, rollarni ko'rish. Kuzatuvchi: faqat ko'rish. Pul, buyum, e'lon, iqtisod va adminlar — faqat bosh admin (ADMIN_IDS)." }));
    }

    async function loadLog(page) {
      let d;
      try { d = await api(`/api/log?page=${page}`); } catch (e) { if (alive(view)) clear(logCard).append(h("h2", { text: "Amallar jurnali" }), errorCard(e, () => loadLog(page))); return; }
      if (!alive(view)) return;
      clear(logCard).append(h("h2", { text: "Amallar jurnali" }), d.items.length ? h("div", null, d.items.map(feedItem)) : empty("Hali amallar yo'q."),
        d.total > d.size ? pager(d.page, d.size, d.total, loadLog) : null);
    }
    loadEcon(); loadAdmins(); loadLog(0);
  }

  boot();
})();
