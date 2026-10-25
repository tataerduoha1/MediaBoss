/** 应用入口：hash 路由 + 布局 + 启动引导。 */
import { api } from "./api.js?v=4";
import { h, toast, applyTheme } from "./util.js?v=4";
import { openUpdateDialog } from "./update.js?v=4";
import * as Login from "./pages/login.js?v=4";
import * as Dashboard from "./pages/dashboard.js?v=4";
import * as Videos from "./pages/videos.js?v=4";
import * as Jav from "./pages/jav.js?v=4";
import * as Entities from "./pages/entities.js?v=4";
import * as Player from "./pages/player.js?v=4";
import * as History from "./pages/history.js?v=4";
import * as Downloads from "./pages/downloads.js?v=4";
import * as Settings from "./pages/settings.js?v=4";

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
  { re: /^\/history$/, mod: History, title: "观看历史" },
  { re: /^\/downloads$/, mod: Downloads, title: "下载" },
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

function buildLayout() {
  const sidebar = h("aside", { class: "sidebar", id: "sidebar" },
    h("div", { class: "logo" }, h("span", { class: "mark" }, "▶"), "MediaBoss"),
    h("nav", { class: "nav" },
      h("a", { href: "#/", "data-nav": "/" }, h("span", { class: "ico" }, "📊"), "仪表盘"),
      h("div", { class: "group" }, "媒体库"),
      h("a", { href: "#/videos", "data-nav": "/videos" }, h("span", { class: "ico" }, "🎬"), "视频库"),
      h("a", { href: "#/jav", "data-nav": "/jav" }, h("span", { class: "ico" }, "💋"), "JAV 库"),
      h("a", { href: "#/actresses", "data-nav": "/actresses" }, h("span", { class: "ico" }, "👩" ), "女优"),
      h("a", { href: "#/studios", "data-nav": "/studios" }, h("span", { class: "ico" }, "🏢"), "厂商"),
      h("a", { href: "#/series", "data-nav": "/series" }, h("span", { class: "ico" }, "📚"), "系列"),
      h("a", { href: "#/genres", "data-nav": "/genres" }, h("span", { class: "ico" }, "🏷"), "类别"),
      h("div", { class: "group" }, "其他"),
      h("a", { href: "#/history", "data-nav": "/history" }, h("span", { class: "ico" }, "🕘"), "观看历史"),
      h("a", { href: "#/downloads", "data-nav": "/downloads" }, h("span", { class: "ico" }, "⬇️"), "下载"),
      h("a", { href: "#/settings", "data-nav": "/settings" }, h("span", { class: "ico" }, "⚙️"), "设置"),
    ),
    h("div", { class: "foot" }, "MediaBoss · 本地媒体管家"),
  );

  const searchInput = h("input", {
    type: "text", placeholder: "搜索番号 / 标题 / 文件名…", id: "global-search",
  });
  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && searchInput.value.trim()) {
      nav(`/videos?q=${encodeURIComponent(searchInput.value.trim())}`);
      searchInput.blur();
    }
  });

  const pill = h("span", { class: "task-pill", id: "task-pill", title: "后台任务" },
    h("span", { class: "dot" }), h("span", { class: "txt" }, "空闲"));
  pill.addEventListener("click", openUpdateDialog);

  const updBtn = h("button", { class: "btn sm", id: "upd-btn", title: "扫描目录并更新媒体库元数据" }, "🔄 更新");
  updBtn.addEventListener("click", openUpdateDialog);

  const burger = h("button", { class: "burger", onclick: () => sidebar.classList.toggle("open") }, "☰");
  const scrim = h("div", { class: "scrim", style: "display:none" });
  scrim.addEventListener("click", () => { sidebar.classList.remove("open"); scrim.style.display = "none"; });
  sidebar.addEventListener("click", (e) => {
    if (e.target.closest("a")) { sidebar.classList.remove("open"); scrim.style.display = "none"; }
  });

  const logout = h("button", { class: "btn ghost sm", title: "退出登录" }, "退出");
  logout.addEventListener("click", async () => {
    try { await api.post("/auth/logout"); } catch { /* ignore */ }
    location.hash = "#/login";
  });

  const topbar = h("div", { class: "topbar" },
    burger,
    h("div", { class: "searchbox" },
      h("span", { class: "s-ico" }, "🔍"), searchInput, h("kbd", {}, "/")),
    h("div", { class: "spacer" }),
    updBtn,
    pill,
    logout,
  );

  const view = h("div", { class: "view", id: "view" });
  const layout = h("div", { class: "layout" }, sidebar, scrim, h("div", { class: "main" }, topbar, view));

  // 快捷键：/ 聚焦搜索
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement?.tagName !== "INPUT"
        && document.activeElement?.tagName !== "TEXTAREA" && !e.target.isContentEditable) {
      e.preventDefault();
      searchInput.focus();
    }
  });
  return { layout, view, pill };
}

async function refreshTaskPill(pill) {
  try {
    const s = await api.get("/tasks/status");
    const busy = s.scan?.running || s.scrape?.running || (s.scrape?.queue || 0) > 0 || (s.thumb_queue || 0) > 0;
    pill.classList.toggle("busy", !!busy);
    const parts = [];
    if (s.scan?.running) parts.push("扫描中");
    if (s.scrape?.running || s.scrape?.queue > 0) parts.push(`刮削 ${s.scrape.queue || 0}`);
    if (s.thumb_queue > 0) parts.push(`缩略图 ${s.thumb_queue}`);
    pill.querySelector(".txt").textContent = busy ? parts.join(" · ") : "空闲";
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
      taskTimer = setInterval(() => refreshTaskPill(layoutEl.pill), 6000);
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
    try {  // 应用服务器端主题设置（本地缓存优先，避免闪烁）
      const s = await api.get("/settings");
      applyTheme(localStorage.getItem("mb_theme") || s.theme || "dark");
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
