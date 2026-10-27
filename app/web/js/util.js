/** 通用工具：DOM 构建、格式化、toast、modal、防抖。 */

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c.nodeType ? c : document.createTextNode(c));
  }
  return el;
}

export const fmtSize = (n) => {
  if (!n || n <= 0) return "-";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n >= 100 || i === 0 ? 0 : 1)} ${u[i]}`;
};

export const fmtDur = (sec) => {
  sec = Math.round(sec || 0);
  if (sec <= 0) return "-";
  const hh = Math.floor(sec / 3600), mm = Math.floor((sec % 3600) / 60), ss = sec % 60;
  return hh > 0
    ? `${hh}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`
    : `${mm}:${String(ss).padStart(2, "0")}`;
};

export const fmtTime = (ts) => {
  if (!ts) return "-";
  const d = new Date(ts * 1000);
  const p = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
};

export const fmtAgo = (ts) => {
  if (!ts) return "-";
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  if (diff < 7 * 86400) return `${Math.floor(diff / 86400)} 天前`;
  return fmtTime(ts).slice(0, 10);
};

/** 是否在服务器本机浏览（mpv 唤起等本机操作仅此场景显示；远端触发会在服务器上弹窗） */
export const isLocal = () => ["localhost", "127.0.0.1", "[::1]", "::1"].includes(location.hostname);

export function toast(msg, type = "ok", ms = 2600) {
  const box = document.getElementById("toasts");
  const t = h("div", { class: `toast ${type}` }, msg);
  box.append(t);
  setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 300); }, ms);
}

export function modal(build) {
  const root = document.getElementById("modal-root");
  const scrim = h("div", { class: "scrim2" });
  const close = () => {
    if (typeof box._onclose === "function") { try { box._onclose(); } catch { /* ignore */ } }
    scrim.remove();
    document.removeEventListener("keydown", onKey);
  };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  const box = h("div", { class: "modal" });
  scrim.append(box);
  scrim.addEventListener("mousedown", (e) => { if (e.target === scrim) close(); });
  document.addEventListener("keydown", onKey);
  build(box, close);
  root.append(scrim);
  return close;
}

export function confirmModal(title, text, onOk, danger = false) {
  modal((box, close) => {
    box.append(
      h("h3", {}, title),
      h("p", { style: "color:var(--muted);margin:0 0 4px" }, text),
      h("div", { class: "acts" },
        h("button", { class: "btn", onclick: close }, "取消"),
        h("button", { class: `btn ${danger ? "danger" : "primary"}`, onclick: async () => { close(); await onOk(); } }, "确定"),
      ),
    );
  });
}

export function promptModal(title, fields, onOk) {
  /** fields: [{key, label, type, value, placeholder}] */
  modal((box, close) => {
    const inputs = {};
    box.append(h("h3", {}, title));
    for (const f of fields) {
      const input = h("input", { class: "input", type: f.type || "text", value: f.value ?? "", placeholder: f.placeholder || "" });
      inputs[f.key] = input;
      box.append(h("div", { class: "row" }, h("label", {}, f.label), input));
    }
    box.append(h("div", { class: "acts" },
      h("button", { class: "btn", onclick: close }, "取消"),
      h("button", {
        class: "btn primary",
        onclick: async () => {
          const vals = {};
          for (const [k, i] of Object.entries(inputs)) vals[k] = i.value;
          close();
          await onOk(vals);
        },
      }, "确定"),
    ));
    inputs[fields[0].key]?.focus();
  });
}

export function debounce(fn, ms = 300) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

/** 主题应用：dark / light / oled / mocha / forest / sepia / ocean / neon / gold / sakura / auto。写入 localStorage 供下次无闪烁加载。 */
export function applyTheme(t = "dark") {
  document.documentElement.setAttribute("data-theme", t === "auto" ? "auto" : t);
  localStorage.setItem("mb_theme", t);
}

/* ===== v1.2 新增：基础 i18n（界面框架层） ===== */
const I18N = {
  zh: {
    "nav.dashboard": "仪表盘", "nav.videos": "视频库", "nav.jav": "JAV 库",
    "nav.actresses": "女优", "nav.studios": "厂商", "nav.series": "系列",
    "nav.genres": "类别", "nav.collections": "片单", "nav.insights": "观影统计",
    "nav.tools": "工具箱", "nav.history": "观看历史",
    "nav.settings": "设置", "group.library": "媒体库", "group.other": "其他",
    "search.placeholder": "搜索番号 / 标题 / 文件名…",
    "act.logout": "退出", "act.update": "更新", "task.idle": "空闲",
  },
  en: {
    "nav.dashboard": "Dashboard", "nav.videos": "Videos", "nav.jav": "JAV Library",
    "nav.actresses": "Actresses", "nav.studios": "Studios", "nav.series": "Series",
    "nav.genres": "Genres", "nav.collections": "Collections", "nav.insights": "Insights",
    "nav.tools": "Toolbox", "nav.history": "History",
    "nav.settings": "Settings", "group.library": "Library", "group.other": "More",
    "search.placeholder": "Search code / title / filename…",
    "act.logout": "Exit", "act.update": "Update", "task.idle": "Idle",
  },
};

export function t(key) {
  let lang = "zh";
  try { lang = localStorage.getItem("mb_lang") || "zh"; } catch { /* ignore */ }
  return (I18N[lang] && I18N[lang][key]) || I18N.zh[key] || key;
}

/** 切换语言并即时刷新带 data-i18n 标记的元素。 */
export function applyLang(lang) {
  try { localStorage.setItem("mb_lang", lang === "en" ? "en" : "zh"); } catch { /* ignore */ }
  document.documentElement.lang = lang === "en" ? "en" : "zh-CN";
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  const gs = document.getElementById("global-search");
  if (gs) gs.placeholder = t("search.placeholder");
}

/* ===== v1.2 新增：强调色 / 壁纸 ===== */
function _hexRgb(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || "").trim());
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** 应用自定义强调色（hex）。light 主题下派生色变暗以保证对比度。传空恢复默认。 */
export function applyAccent(hex) {
  const root = document.documentElement;
  const rgb = _hexRgb(hex);
  if (!rgb) {
    root.style.removeProperty("--accent");
    root.style.removeProperty("--accent-h");
    root.style.removeProperty("--accent-dim");
    try { localStorage.removeItem("mb_accent"); } catch { /* ignore */ }
    return;
  }
  const [r, g, b] = rgb;
  const theme = root.getAttribute("data-theme");
  const light = theme === "light" || theme === "sepia" || theme === "sakura"
    || (theme === "auto" && window.matchMedia?.("(prefers-color-scheme: light)").matches);
  const d = light ? -28 : 26;
  const hexOf = (x) => x.toString(16).padStart(2, "0");
  root.style.setProperty("--accent", `#${rgb.map(hexOf).join("")}`);
  root.style.setProperty("--accent-h",
    `rgb(${Math.min(255, Math.max(0, r + d))}, ${Math.min(255, Math.max(0, g + Math.round(d * .75)))}, ${Math.min(255, Math.max(0, b + Math.round(d * .75)))})`);
  root.style.setProperty("--accent-dim", `rgba(${r}, ${g}, ${b}, .16)`);
  try { localStorage.setItem("mb_accent", `#${rgb.map(hexOf).join("")}`); } catch { /* ignore */ }
}

/** 应用壁纸（URL）。半透明化面板变量让背景透出；传空恢复默认。 */
export function applyWallpaper(url) {
  const body = document.body;
  url = String(url || "").trim();
  if (!url) {
    body.classList.remove("has-wallpaper");
    body.style.backgroundImage = "";
    try { localStorage.removeItem("mb_wallpaper"); } catch { /* ignore */ }
    return;
  }
  body.classList.add("has-wallpaper");
  body.style.backgroundImage = `url("${url.replace(/"/g, "%22")}")`;
  try { localStorage.setItem("mb_wallpaper", url); } catch { /* ignore */ }
}

/** 列表页码记忆（会话内）：进入详情再返回时恢复翻到之前的页。 */
export const pageMem = {
  get(key) {
    try { return Math.max(1, +sessionStorage.getItem("mb_page:" + key) || 1); }
    catch { return 1; }
  },
  set(key, p) {
    try {
      if (p > 1) sessionStorage.setItem("mb_page:" + key, String(p));
      else sessionStorage.removeItem("mb_page:" + key);
    } catch { /* 存储不可用时静默 */ }
  },
};

/** 时长格式化（秒 → mm:ss / h:mm:ss），用于任务耗时。 */
export function fmtElapsed(sec) {
  sec = Math.max(0, Math.round(sec || 0));
  const hh = Math.floor(sec / 3600), mm = Math.floor((sec % 3600) / 60), ss = sec % 60;
  return hh > 0 ? `${hh}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`
    : `${mm}:${String(ss).padStart(2, "0")}`;
}

export function stars(rating) {
  return "★".repeat(rating || 0) + "☆".repeat(5 - (rating || 0));
}

export function scoreStars(score) {
  // JAV 站点评分一般 0-10
  const s = Math.round((score || 0) / 2);
  return s > 0 ? "★".repeat(Math.min(5, s)) : "";
}

/** 图片懒加载：进入视口才设置 src。 */
const io = new IntersectionObserver((entries) => {
  for (const e of entries) {
    if (e.isIntersecting) {
      const img = e.target;
      io.unobserve(img);
      img.src = img.dataset.src;
      img.addEventListener("load", () => img.classList.add("loaded"), { once: true });
      img.addEventListener("error", () => img.classList.add("loaded"), { once: true });
    }
  }
}, { rootMargin: "400px" });

export function lazyimg(src, alt = "") {
  const img = h("img", { alt, loading: "lazy" });
  img.dataset.src = src;
  io.observe(img);
  return img;
}
