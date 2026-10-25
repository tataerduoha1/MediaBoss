/** 观影统计（B1 年度报告 / B2 热力日历 / B5 女优合作网络）。 */
import { api } from "../api.js?v=6";
import { h, fmtDur } from "../util.js?v=6";
import { emptyState } from "../components.js?v=6";

export async function render(view, params, query) {
  document.title = "观影统计 · MediaBoss";
  view.innerHTML = "";
  const thisYear = new Date().getFullYear();
  const year = Math.min(thisYear, Math.max(2000, parseInt(query.year, 10) || thisYear));
  const yearSel = h("select", { class: "input", style: "max-width:130px" },
    ...Array.from({ length: 6 }, (_, i) => {
      const y = thisYear - i;
      return h("option", { value: y, selected: y === year }, `${y} 年`);
    }));
  yearSel.addEventListener("change", () => { location.hash = `#/insights?year=${yearSel.value}`; });

  view.append(h("div", { class: "page-head" }, h("h1", {}, "📈 观影统计"), yearSel));
  const holder = h("div", { class: "insights-wrap" });
  view.append(holder);

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  /* ---- 1. 年度报告 ---- */
  try {
    const a = await api.get(`/stats/annual?year=${year}`);
    holder.append(section("🗓", `${year} 年度报告`, [
      statCards([
        ["▶ 总播放", `${a.plays} 次`],
        ["⏱ 总时长", `${a.total_h} 小时`],
        ["🎞 看过影片", `${a.videos} 部`],
        ["📆 活跃天数", `${a.active_days} 天`],
        ["⚡ 日均播放", `${a.avg_per_day} 次`],
        ["🔥 最疯狂一天", a.best_day?.day ? `${a.best_day.day}（${a.best_day.plays} 次）` : "—"],
      ]),
      monthBars(a.months),
    ]));

    // 榜单
    holder.append(section("🏆", "年度榜单", [
      topList("最受欢迎影片", a.top_videos.map((r) => ({
        label: (r.code ? `${r.code} · ` : "") + (r.cn_title || r.title || r.vtitle || ""),
        value: `${r.plays} 次`, href: r.code ? `#/jav?q=${encodeURIComponent(r.code)}` : "",
      }))),
      topList("最常看女优", a.top_actresses.map((r) => ({
        label: r.name, value: `${r.plays} 次`, href: `#/jav?actress_id=${r.id}`,
      }))),
      topList("最爱类别", a.top_genres.map((r) => ({ label: r.name, value: `${r.plays} 次` }))),
      topList("常看厂商", a.top_studios.map((r) => ({
        label: r.name, value: `${r.plays} 次`, href: `#/jav?studio_id=${r.id}`,
      }))),
    ], true));
  } catch (e) {
    holder.append(section("🗓", "年度报告", [emptyState("⚠️", e.message)]));
  }

  /* ---- 2. 热力日历 ---- */
  try {
    const hm = await api.get(`/stats/heatmap?year=${year}`);
    holder.append(section("🔥", `${year} 观影热力图`, [heatmapEl(hm)]));
  } catch (e) {
    holder.append(section("🔥", "观影热力图", [emptyState("⚠️", e.message)]));
  }

  /* ---- 3. 女优合作网络 ---- */
  try {
    const net = await api.get("/stats/network?min=2&limit=48");
    holder.append(section("🕸", "女优合作网络",
      [net.nodes?.length ? networkSvg(net, esc) : emptyState("🕸", "合作数据还不多",
        "统计「同一部影片共同出演 ≥2 次」的女优组合，多看多刮削后会更丰富")]));
  } catch (e) {
    holder.append(section("🕸", "女优合作网络", [emptyState("⚠️", e.message)]));
  }
}

function section(icon, title, children, wide = false) {
  return h("div", { class: "ins-sec" + (wide ? " wide" : "") },
    h("div", { class: "ins-h" }, h("h2", {}, `${icon} ${title}`)),
    ...children);
}

function statCards(list) {
  return h("div", { class: "stat-cards" },
    list.map(([k, v]) => h("div", { class: "stat-card" },
      h("div", { class: "k" }, k), h("div", { class: "v" }, v))));
}

function monthBars(months) {
  const max = Math.max(1, ...months.map((m) => m.plays));
  return h("div", { class: "mon-wrap" },
    h("div", { class: "mon-bars" }, months.map((m) =>
      h("div", { class: "mon-col", title: `${m.m} 月：${m.plays} 次 / ${fmtDur(m.secs)}` },
        h("div", { class: "bar" }, h("i", { style: `height:${Math.round(m.plays / max * 100)}%` })),
        h("div", { class: "lb" }, `${m.m}`)))),
    h("div", { class: "mon-cap" }, "每月播放次数"));
}

function topList(title, rows) {
  if (!rows.length) return h("div", { class: "top-block" },
    h("h3", {}, title), h("p", { class: "mut" }, "暂无数据"));
  const max = Math.max(...rows.map((r) => parseFloat(r.value) || 1));
  return h("div", { class: "top-block" },
    h("h3", {}, title),
    h("div", { class: "top-list" }, rows.map((r, i) =>
      h("div", { class: "top-row" },
        h("span", { class: "rank" + (i < 3 ? ` r${i + 1}` : "") }, i + 1),
        h("span", { class: "lb" }, r.href && r.label !== "暂无数据"
          ? h("a", { class: "lnk", href: r.href }, r.label) : r.label),
        h("div", { class: "bar" }, h("i", { style: `width:${Math.round((parseFloat(r.value) || 0) / max * 100)}%` })),
        h("span", { class: "val" }, r.value)))));
}

function heatmapEl(hm) {
  const playsArr = hm.days.map((d) => d.plays);
  const max = Math.max(1, ...playsArr);
  const lv = (p) => (p <= 0 ? 0 : Math.min(4, Math.ceil(p / Math.max(1, max / 4))));
  const grid = h("div", { class: "heat-grid", style: `grid-template-rows:repeat(7,12px)` });
  for (let i = 0; i < hm.first_wday; i++) grid.append(h("i", { class: "heat-cell blank" }));
  for (const d of hm.days) {
    grid.append(h("i", {
      class: `heat-cell lv${lv(d.plays)}`,
      title: `${d.date} · ${d.plays} 次`,
    }));
  }
  const legend = h("div", { class: "heat-legend" }, "少",
    [0, 1, 2, 3, 4].map((n) => h("i", { class: `heat-cell lv${n}` })), "多",
    h("span", { class: "mut" }, `  全年 ${hm.days.reduce((s, d) => s + d.plays, 0)} 次 · 最忙一天 ${max} 次`));
  return h("div", { class: "heat-wrap" },
    h("div", { class: "heat-scroll" }, grid), legend);
}

function networkSvg(net, esc) {
  const W = 460, CX = W / 2, CY = W / 2, R = 168;
  const n = net.nodes.length;
  const pos = new Map();
  net.nodes.forEach((nd, i) => {
    const ang = (i / n) * Math.PI * 2 - Math.PI / 2;
    pos.set(nd.id, [CX + R * Math.cos(ang), CY + R * Math.sin(ang)]);
  });
  const maxW = Math.max(...net.edges.map((e) => e.weight), 1);
  const edges = net.edges.map((e) => {
    const [x1, y1] = pos.get(e.src), [x2, y2] = pos.get(e.dst);
    const w = 0.8 + (e.weight / maxW) * 3.4;
    return `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}"
      stroke="var(--accent)" stroke-opacity=".28" stroke-width="${w.toFixed(1)}"><title>${esc(labelOf(net, e.src))} × ${esc(labelOf(net, e.dst))}：${e.weight} 次</title></line>`;
  }).join("");
  const nodes = net.nodes.map((nd) => {
    const [x, y] = pos.get(nd.id);
    const r = Math.min(15, 4.5 + Math.sqrt(nd.video_count || 1) * 1.4);
    const lx = CX + (R + 26) * Math.cos(Math.atan2(y - CY, x - CX));
    const ly = CY + (R + 26) * Math.sin(Math.atan2(y - CY, x - CX));
    const anchor = Math.abs(lx - CX) < 30 ? "middle" : lx > CX ? "start" : "end";
    const name = (nd.name || "").length > 10 ? nd.name.slice(0, 9) + "…" : nd.name;
    return `<g><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r.toFixed(1)}"
        fill="var(--accent)" fill-opacity=".85"><title>${esc(nd.name)} · ${nd.video_count} 部</title></circle>
      <text x="${lx.toFixed(1)}" y="${(ly + 3).toFixed(1)}" text-anchor="${anchor}"
        font-size="10.5" fill="currentColor" opacity=".8">${esc(name)}</text></g>`;
  }).join("");
  return h("div", { class: "net-wrap" },
    h("div", {
      class: "net-svg", style: `max-width:${W}px;margin:0 auto;`,
      html: `<svg viewBox="0 0 ${W} ${W}" width="100%">${edges}${nodes}</svg>`,
    }),
    h("p", { class: "mut", style: "text-align:center;font-size:12px" },
      `节点大小 = 影片数 · 连线粗细 = 合作次数（≥${net.min_weight} 次，取前 ${net.limit} 组）· 点击节点旁文字无效，请到「女优」页查看`));
}

function labelOf(net, id) {
  return net.nodes.find((nd) => nd.id === id)?.name || `#${id}`;
}
