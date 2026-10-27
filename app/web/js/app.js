/** 应用入口：hash 路由 + 布局 + 启动引导。 */
import { api } from "./api.js?v=22";
import { h, toast, modal, applyTheme, applyAccent, applyWallpaper, applyLang, t, debounce } from "./util.js?v=22";
import { openUpdateDialog } from "./update.js?v=22";
import * as Login from "./pages/login.js?v=22";
import * as Dashboard from "./pages/dashboard.js?v=22";
import * as Videos from "./pages/videos.js?v=22";
import * as Jav from "./pages/jav.js?v=22";
import * as Entities from "./pages/entities.js?v=22";
import * as Player from "./pages/player.js?v=22";
import * as History from "./pages/history.js?v=22";
import * as Collections from "./pages/collections.js?v=22";
import * as Insights from "./pages/insights.js?v=22";
import * as Tools from "./pages/tools.js?v=22";
import * as Settings from "./pages/settings.js?v=22";

window.__BOOT_OK = "static-ok"; // 诊断标记：模块图加载成功即设置

const app = document.getElementById("app");

const ROUTES = [
  { re: /^\/login$/, mod: Login, bare: true },
  { re: /^\/$/, mod: Dashboard, title: "仪表盘" },
  { re: /^\/videos$/, mod: Videos, title: "视频库" },
  { re: /^\/jav$/, mod: Jav, title: "JAV 库" },
  { re: /^\/jav\/(\d+)$/, mod: Jav, fn: "renderDetail", title: "详情" },
  { re: /^\/(actresses|studios|series|genres)$/, mod: Entities, title: "演员与厂商" },
  { re: /^\/player\/(\d+)$/, mod: Player, bare: true, title: "播放" },
  { re: /^\/collections$/, mod: Collections, title: "片单" },
  { re: /^\/collections\/(\d+)$/, mod: Collections, fn: "renderDetail", title: "片单详情" },
  { re: /^\/insights$/, mod: Insights, title: "观影统计" },
  { re: /^\/tools$/, mod: Tools, title: "工具箱" },
  { re: /^\/history$/, mod: History, title: "观看历史" },
  { re: /^\/settings$/, mod: Settings, title: "设置" },
];

let current = { teardown: null, poll: null };
let layoutEl = null;
let taskTimer = null;
/* 路由滚动记忆：进入详情再返回列表时恢复滚动位置（会话内有效） */
const scrollMemory = new Map();
let lastRouteKey = "";
const routeKey = (path, query) => path + JSON.stringify(query || {});

function parseHash() {
  const raw = location.hash.replace(/^#/, "") || "/";
  const [path, qs] = raw.split("?");
  return { path, query: Object.fromEntries(new URLSearchParams(qs || "")) };
}

export function nav(to) { location.hash = to; }

const navItem = (href, key, icon) => h("a", { href, "data-nav": href.replace("#", "").split("?")[0] },
  h("span", { class: "ico" }, icon), h("span", { "data-i18n": key }, t(key)));

function buildLayout() {
  const sidebar = h("aside", { class: "sidebar", id: "sidebar" },
    h("div", { class: "logo" }, h("span", { class: "mark" }, "▶"), "MediaBoss"),
    h("nav", { class: "nav" },
      navItem("#/", "nav.dashboard", "📊"),
      h("div", { class: "group", "data-i18n": "group.library" }, t("group.library")),
      navItem("#/videos", "nav.videos", "🎬"),
      navItem("#/jav", "nav.jav", "💋"),
      navItem("#/actresses", "nav.actresses", "👩"),
      navItem("#/studios", "nav.studios", "🏢"),
      navItem("#/series", "nav.series", "📚"),
      navItem("#/genres", "nav.genres", "🏷"),
      navItem("#/collections", "nav.collections", "📋"),
      h("div", { class: "group", "data-i18n": "group.other" }, t("group.other")),
      navItem("#/insights", "nav.insights", "📈"),
      navItem("#/tools", "nav.tools", "🧰"),
      navItem("#/history", "nav.history", "🕘"),
      navItem("#/settings", "nav.settings", "⚙️"),
    ),
    h("div", { class: "foot" }, "MediaBoss · 本地媒体管家"),
  );

  const searchInput = h("input", {
    type: "text", placeholder: t("search.placeholder"), id: "global-search",
  });
  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && searchInput.value.trim()) {
      nav(`/videos?q=${encodeURIComponent(searchInput.value.trim())}`);
      searchInput.blur();
    }
  });

  const pill = h("span", { class: "task-pill", id: "task-pill", title: "后台任务" },
    h("span", { class: "dot" }), h("span", { class: "txt" }, t("task.idle")));
  pill.addEventListener("click", openUpdateDialog);

  const updBtn = h("button", { class: "btn sm", id: "upd-btn", title: "扫描目录并更新媒体库元数据" },
    h("span", { "data-i18n": "act.update" }, t("act.update")), " 🔄");
  updBtn.addEventListener("click", openUpdateDialog);

  /* 幸运骰子：随机播一部（优先未看） */
  const diceBtn = h("button", { class: "btn sm", id: "dice-btn", title: "🎲 幸运骰子：随机播放一部（优先未看）" }, "🎲");
  diceBtn.addEventListener("click", async () => {
    diceBtn.disabled = true;
    try {
      const r = await api.get("/videos/random-one?watched=0");
      nav(`/player/${r.id}`);
    } catch {
      try {
        const r = await api.get("/videos/random-one");
        nav(`/player/${r.id}`);
      } catch (e2) { toast(e2.message, "err"); }
    }
    diceBtn.disabled = false;
  });

  // 侧边栏开合：移动端走抽屉(open + 遮罩，点侧栏外任意处收起)，桌面走折叠(side-collapsed)
  const setSide = (open) => {
    sidebar.classList.toggle("open", open);
    scrim.style.display = open ? "" : "none";
  };
  const burger = h("button", { class: "burger", title: "折叠 / 展开导航栏" }, "☰");
  burger.addEventListener("click", () => {
    const lay = burger.closest(".layout");
    if (window.matchMedia("(max-width: 860px)").matches) setSide(!sidebar.classList.contains("open"));
    else lay?.classList.toggle("side-collapsed");
  });
  const scrim = h("div", { class: "scrim", style: "display:none" });
  scrim.addEventListener("click", () => setSide(false));
  sidebar.addEventListener("click", (e) => {
    if (e.target.closest("a")) setSide(false);
  });

  const logout = h("button", { class: "btn ghost sm", title: "退出登录" }, h("span", { "data-i18n": "act.logout" }, t("act.logout")));
  logout.addEventListener("click", async () => {
    try { await api.post("/auth/logout"); } catch { /* ignore */ }
    location.hash = "#/login";
  });

  const topbar = h("div", { class: "topbar" },
    burger,
    h("div", { class: "searchbox" },
      h("span", { class: "s-ico" }, "🔍"), searchInput, h("kbd", {}, "/")),
    h("div", { class: "spacer" }),
    diceBtn,
    updBtn,
    pill,
    logout,
  );

  const view = h("div", { class: "view", id: "view" });
  const layout = h("div", { class: "layout" }, sidebar, scrim, h("div", { class: "main" }, topbar, view));

  // 快捷键：/ 聚焦搜索；Ctrl/⌘+K 命令面板
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      openPalette();
    } else if (e.key === "/" && document.activeElement?.tagName !== "INPUT"
        && document.activeElement?.tagName !== "TEXTAREA" && !e.target.isContentEditable) {
      e.preventDefault();
      searchInput.focus();
    }
  });
  return { layout, view, pill };
}

/* ============ Ctrl+K 命令面板 ============ */
function openPalette() {
  const pages = [
    ["📊", "#/", "nav.dashboard"], ["🎬", "#/videos", "nav.videos"], ["💋", "#/jav", "nav.jav"],
    ["👩", "#/actresses", "nav.actresses"], ["🏢", "#/studios", "nav.studios"],
    ["📚", "#/series", "nav.series"], ["🏷", "#/genres", "nav.genres"],
    ["📋", "#/collections", "nav.collections"], ["📈", "#/insights", "nav.insights"],
    ["🧰", "#/tools", "nav.tools"], ["🕘", "#/history", "nav.history"],
    ["⚙️", "#/settings", "nav.settings"],
  ];
  const staticItems = pages.map(([icon, to, key]) => ({ icon, to, label: t(key) }));
  modal((box, close) => {
    const input = h("input", { class: "input", placeholder: "搜索影片 / 跳转页面…（↑↓ 选择，Enter 打开）" });
    const list = h("div", { class: "cmd-list" });
    box.append(h("h3", { style: "margin-top:0" }, "⌘ 快速跳转"), input, list);
    let items = staticItems;
    let sel = 0;
    const render = () => {
      list.replaceChildren(...items.map((it, i) =>
        h("div", { class: "cmd-item" + (i === sel ? " on" : ""), onclick: () => go(i) },
          h("span", { class: "ico" }, it.icon),
          h("span", { class: "lb" }, it.label),
          it.sub ? h("span", { class: "sub" }, it.sub) : null)));
    };
    const go = (i) => { const it = items[i]; if (!it) return; close(); nav(it.to); };
    const doSearch = debounce(async () => {
      const q = input.value.trim();
      if (!q) { items = staticItems; sel = 0; render(); return; }
      const enc = encodeURIComponent(q);
      const [jr, vr] = await Promise.all([
        api.get(`/jav?q=${enc}&page_size=6`).catch(() => null),
        api.get(`/videos?q=${enc}&page_size=4`).catch(() => null),
      ]);
      items = [
        ...(jr?.items || []).map((j) => ({
          icon: "💋", to: `#/jav/${j.id}`, sub: j.code,
          label: j.cn_title || j.title || j.code,
        })),
        ...(vr?.items || []).map((v) => ({
          icon: "🎬", to: `#/player/${v.id}`, sub: v.code || "",
          label: v.title || v.filename,
        })),
      ];
      sel = 0; render();
    }, 250);
    input.addEventListener("input", doSearch);
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); sel = Math.min(items.length - 1, sel + 1); render(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); sel = Math.max(0, sel - 1); render(); }
      else if (e.key === "Enter") { e.preventDefault(); go(sel); }
    });
    render();
    setTimeout(() => input.focus(), 30);
  });
}

async function refreshTaskPill(pill) {
  if (!pill) return; // bare 路由（播放页等）无 task pill
  try {
    const s = await api.get("/tasks/status");
    const busy = s.scan?.running || s.scrape?.running || (s.scrape?.queue || 0) > 0 || (s.thumb_queue || 0) > 0;
    pill.classList.toggle("busy", !!busy);
    const parts = [];
    if (s.scan?.running) parts.push("扫描中");
    if (s.scrape?.running || s.scrape?.queue > 0) parts.push(`刮削 ${s.scrape.queue || 0}`);
    if (s.thumb_queue > 0) parts.push(`缩略图 ${s.thumb_queue}`);
    pill.querySelector(".txt").textContent = busy ? parts.join(" · ") : t("task.idle");
  } catch { /* 静默 */ }
}

function teardownCurrent() {
  if (current.teardown) { try { current.teardown(); } catch { /* ignore */ } }
  if (current.poll) clearInterval(current.poll);
  current = { teardown: null, poll: null };
}

async function route() {
  teardownCurrent();
  const { path, query } = parseHash();
  // 离开带布局页面时记住滚动位置（播放页等 bare 路由无 .view）
  if (lastRouteKey && layoutEl?.view) {
    scrollMemory.set(lastRouteKey, layoutEl.view.scrollTop);
  }
  for (const r of ROUTES) {
    const m = path.match(r.re);
    if (!m) continue;
    const params = { 0: m[0], ...m.slice(1).reduce((o, v, i) => ({ ...o, [i + 1]: v }), {}) };
    const fn = r.fn || "render";
    if (r.bare) {
      layoutEl = null;
      app.innerHTML = "";
      app.append(h("div", { id: "page-root" }));
      const t = await r.mod[fn](app.firstChild, params, query);
      if (typeof t === "function") current.teardown = t;
      lastRouteKey = routeKey(path, query);
      return;
    }
    // 带布局页面
    if (!layoutEl) {
      app.innerHTML = "";
      layoutEl = buildLayout();
      app.append(layoutEl.layout);
      if (taskTimer) clearInterval(taskTimer); // 防重复定时器
      taskTimer = setInterval(() => { if (layoutEl) refreshTaskPill(layoutEl.pill); }, 6000); // 裸路由（播放页）时 layoutEl 为 null，需跳过
      refreshTaskPill(layoutEl.pill);
    }
    // 高亮导航
    const navKey = "/" + path.split("/")[1];
    layoutEl.layout.querySelectorAll(".nav a").forEach((a) =>
      a.classList.toggle("active", a.dataset.nav === navKey));
    // 搜索框回填
    const gs = layoutEl.layout.querySelector("#global-search");
    if (query.q && path.startsWith("/videos")) gs.value = query.q;
    layoutEl.view.classList.remove("bare");
    layoutEl.view.scrollTop = 0;
    const t = await r.mod[fn](layoutEl.view, params, query);
    if (typeof t === "function") current.teardown = t;
    document.title = `${r.title} · MediaBoss`;
    // 内容渲染完成后恢复之前的滚动位置；骨架屏阶段高度不足会被钳制，
    // 故带重试：直到 scrollTop 生效或数据渲染完成（最多约 2 秒）
    const saved = scrollMemory.get(routeKey(path, query));
    if (saved > 0) {
      const restore = (tries) => {
        if (!layoutEl?.view) return;
        layoutEl.view.scrollTop = saved;
        if (Math.abs(layoutEl.view.scrollTop - saved) > 4 && tries > 0) {
          setTimeout(() => restore(tries - 1), 300);
        }
      };
      requestAnimationFrame(() => restore(6));
    }
    lastRouteKey = routeKey(path, query);
    return;
  }
  // 404
  if (!layoutEl) { nav("/"); return; }
  layoutEl.view.innerHTML = "";
  layoutEl.view.append(h("div", { class: "empty" }, h("div", { class: "big" }, "🤔"), h("p", {}, "页面不存在")));
}

window.addEventListener("mb:unauthorized", () => {
  if (!location.hash.startsWith("#/login")) {
    teardownCurrent();
    location.hash = "#/login";
  }
});

window.addEventListener("hashchange", route);

// 启动：探测登录态
(async function boot() {
  if (!location.hash) location.hash = "#/";
  try {
    await api.get("/stats");
    try {  // 应用服务器端外观设置（本地缓存优先，避免闪烁）
      const s = await api.get("/settings");
      applyTheme(localStorage.getItem("mb_theme") || s.theme || "dark");
      applyAccent(localStorage.getItem("mb_accent") || s.accent_color || "");
      applyWallpaper(localStorage.getItem("mb_wallpaper") || s.wallpaper || "");
      applyLang(localStorage.getItem("mb_lang") || s.lang || "zh");
    } catch { /* ignore */ }
    await route();
  } catch (e) {
    if (e.status === 401 || e.status === 0) {
      location.hash = "#/login";
    } else {
      await route();
      toast(`启动异常: ${e.message}`, "err");
    }
  }
})();
