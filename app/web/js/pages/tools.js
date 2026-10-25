/** 工具箱（A5 重复检测 / A7 存储分析+缓存清理 / A6 NFO 批量导出）。 */
import { api } from "../api.js?v=6";
import { h, toast, confirmModal, fmtSize, fmtDur, fmtAgo } from "../util.js?v=6";
import { emptyState } from "../components.js?v=6";

export async function render(view) {
  document.title = "工具箱 · MediaBoss";
  view.innerHTML = "";
  view.append(h("div", { class: "page-head" }, h("h1", {}, "🧰 工具箱")));
  const wrap = h("div", { class: "tools-wrap" });
  view.append(wrap);

  /* ===== A5 重复检测 ===== */
  const dupBox = h("div", { class: "tool-body" },
    h("p", { class: "mut", style: "margin:0 0 10px" },
      "两种检测：同番号多文件、同大小且同时长（±1s）的疑似重复。每组建议保留体积最大的一个。"));
  const dupBtn = h("button", { class: "btn primary" }, "开始检测");
  dupBtn.addEventListener("click", async () => {
    dupBtn.disabled = true; dupBtn.textContent = "检测中…";
    try {
      const r = await api.get("/tools/duplicates");
      dupBox.querySelector("p").after(renderDups(r));
    } catch (e) { toast(e.message, "err"); }
    dupBtn.disabled = false; dupBtn.textContent = "重新检测";
  });
  wrap.append(toolCard("🔁", "重复文件检测", dupBox, dupBtn));

  /* ===== A7 存储分析 ===== */
  const storeBox = h("div", { class: "tool-body" }, h("p", { class: "mut" }, "加载中…"));
  loadStorage(storeBox);
  const cleanBtn = h("button", { class: "btn" }, "🧹 清理孤儿缓存");
  cleanBtn.addEventListener("click", () => {
    confirmModal("清理孤儿缓存", "删除「对应视频已不存在」的缩略图 / 雪碧图 / 抽帧 / 自定义海报缓存文件（不影响正常缓存，可自动重建）。",
      async () => {
        try {
          const r = await api.post("/tools/cleanup-orphans");
          toast(r.msg || `已清理 ${r.cleaned} 个`, "ok", 4000);
          loadStorage(storeBox);
        } catch (e) { toast(e.message, "err"); }
      });
  });
  wrap.append(toolCard("📦", "存储分析", storeBox, cleanBtn));

  /* ===== A6 NFO 批量导出 ===== */
  const nfoQ = h("input", { class: "input", type: "text", placeholder: "按关键词筛选（番号/标题/女优，留空=全部已刮削）" });
  nfoQ.style.flex = "1";
  const nfoCover = h("label", { class: "mut", style: "display:flex;align-items:center;gap:6px;font-size:12.5px" },
    Object.assign(h("input", { type: "checkbox", checked: true }), { style: "accent-color:var(--accent)" }), "包含封面");
  const nfoBtn = h("button", { class: "btn primary" }, "📄 导出 NFO 压缩包");
  nfoBtn.addEventListener("click", async () => {
    nfoBtn.disabled = true; nfoBtn.textContent = "收集中…";
    try {
      const ids = await collectIds(nfoQ.value.trim());
      if (!ids.length) { toast("没有匹配的已刮削影片", "err"); return; }
      const cover = nfoCover.querySelector("input").checked;
      let done = 0;
      for (let i = 0; i < ids.length; i += 500) {
        const chunk = ids.slice(i, i + 500);
        nfoBtn.textContent = `导出中 ${Math.min(i + 500, ids.length)}/${ids.length}…`;
        await downloadZip(chunk, cover);
        done += chunk.length;
      }
      toast(`已导出 ${done} 个 NFO（浏览器已开始下载）`, "ok", 5000);
    } catch (e) { toast(e.message, "err"); }
    nfoBtn.disabled = false; nfoBtn.textContent = "📄 导出 NFO 压缩包";
  });
  wrap.append(toolCard("🗃", "NFO 批量导出（Emby / Kodi）",
    h("div", { class: "tool-body" },
      h("p", { class: "mut", style: "margin:0 0 10px" },
        "从已刮削影片生成 {番号}.nfo + {番号}.jpg 的 zip，供媒体中心刮削器导入。单包上限 500，超出自动分包。"),
      h("div", { style: "display:flex;gap:9px;flex-wrap:wrap;align-items:center" }, nfoQ, nfoCover, nfoBtn))));
}

function toolCard(icon, title, body, ...btns) {
  return h("div", { class: "tool-card" },
    h("div", { class: "tool-h" },
      h("h2", {}, `${icon} ${title}`),
      h("div", { style: "display:flex;gap:9px" }, ...btns)),
    body);
}

/* ---------- 重复检测 ---------- */
function renderDups(r) {
  if (!r.groups.length) {
    return h("p", { class: "mut ok-c", style: "margin:10px 0 0" }, "✓ 未发现重复文件");
  }
  const rows = [];
  for (const g of r.groups) {
    rows.push(h("div", { class: "dup-group" },
      h("div", { class: "dup-label" }, g.label, h("span", { class: "badge warn" }, `${g.items.length} 个`)),
      h("table", { class: "table" },
        h("thead", {}, h("tr", {}, h("th", {}, "建议"), h("th", {}, "文件"), h("th", {}, "番号"),
          h("th", {}, "大小"), h("th", {}, "时长"), h("th", {}, "添加时间"))),
        h("tbody", {}, ...g.items.map((it, i) => h("tr", {},
          h("td", {}, i === 0 ? h("span", { class: "badge ok" }, "保留") : h("span", { class: "badge err" }, "疑似多余")),
          h("td", { class: "mono" }, h("a", { href: `#/player/${it.id}`, style: "color:var(--accent-h)" }, it.filename)),
          h("td", {}, it.code || "—"),
          h("td", { style: "white-space:nowrap" }, fmtSize(it.size)),
          h("td", { style: "white-space:nowrap" }, fmtDur(it.duration)),
          h("td", { style: "white-space:nowrap" }, fmtAgo(it.created_at)))))),
      g.items.length > 1 ? h("div", { class: "dup-paths" },
        ...g.items.slice(1).map((it) => h("div", { class: "mono", title: it.path }, it.path))) : null,
    ));
  }
  return h("div", { class: "dup-wrap" },
    h("p", { class: "mut", style: "margin:12px 0" }, `发现 ${r.total_groups} 组疑似重复（每页最多 50 组）`),
    ...rows);
}

/* ---------- 存储分析 ---------- */
async function loadStorage(box) {
  try {
    const s = await api.get("/tools/storage");
    const maxDir = Math.max(1, ...s.per_dir.map((d) => d.size));
    const caches = Object.entries(s.caches);
    const maxCache = Math.max(1, ...caches.map(([, c]) => c.size));
    box.replaceChildren(
      h("div", { class: "stat-cards" },
        h("div", { class: "stat-card" }, h("div", { class: "k" }, "影片总占用"), h("div", { class: "v" }, s.total_size_h)),
        h("div", { class: "stat-card" }, h("div", { class: "k" }, "监控目录"), h("div", { class: "v" }, `${s.per_dir.length} 个`)),
        h("div", { class: "stat-card" }, h("div", { class: "k" }, "缓存占用"),
          h("div", { class: "v" }, fmtSize(caches.reduce((t, [, c]) => t + c.size, 0))))),
      h("h3", { style: "margin:16px 0 8px" }, "各目录占用"),
      ...s.per_dir.map((d) => h("div", { class: "store-row" },
        h("div", { class: "lb", title: d.path }, d.path),
        h("div", { class: "bar" }, h("i", { style: `width:${Math.max(2, Math.round(d.size / maxDir * 100))}%` })),
        h("div", { class: "val" }, `${d.size_h} · ${d.count} 个`,
          h("span", { class: "mut" }, `  ${d.exts.map((e) => e.ext.toUpperCase()).join(" / ")}`)))),
      h("h3", { style: "margin:16px 0 8px" }, "缓存目录"),
      h("div", { class: "cache-grid" }, caches.map(([k, c]) =>
        h("div", { class: "cache-item", title: `${c.count} 个文件` },
          h("div", { class: "lb" }, cacheName(k)), h("div", { class: "v" }, c.size_h)))),
      h("h3", { style: "margin:16px 0 8px" }, "最大的 20 个文件"),
      h("table", { class: "table" },
        h("thead", {}, h("tr", {}, h("th", {}, "#"), h("th", {}, "文件"), h("th", {}, "番号"), h("th", {}, "大小"), h("th", {}, "时长"))),
        h("tbody", {}, ...s.biggest.map((v, i) => h("tr", {},
          h("td", { class: "mut" }, i + 1),
          h("td", { class: "mono" }, h("a", { href: `#/player/${v.id}`, style: "color:var(--accent-h)" }, v.filename)),
          h("td", {}, v.code || "—"),
          h("td", { style: "white-space:nowrap" }, fmtSize(v.size)),
          h("td", { style: "white-space:nowrap" }, fmtDur(v.duration)))))),
    );
  } catch (e) {
    box.replaceChildren(emptyState("⚠️", e.message));
  }
}

function cacheName(k) {
  return { covers: "封面", thumbs: "缩略图", sprites: "雪碧图", screenshots: "截图", cache: "临时缓存", logs: "日志" }[k] || k;
}

/* ---------- NFO 导出 ---------- */
async function collectIds(q) {
  const ids = [];
  for (let page = 1; page <= 30; page++) {
    const qs = new URLSearchParams({ page: String(page), page_size: "200", sort: "code", order: "asc" });
    if (q) qs.set("q", q);
    const r = await api.get(`/jav?${qs}`);
    for (const it of r.items) {
      if (it.scrape_status === 1 && it.video_id) ids.push(it.video_id);
    }
    if (!r.has_more) break;
    if (ids.length >= 2500) break; // 上限保护
  }
  return ids;
}

async function downloadZip(ids, cover) {
  const res = await fetch("/api/tools/export-nfo", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_ids: ids, cover }),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.error || `导出失败 (${res.status})`);
  }
  const blob = await res.blob();
  const a = h("a", { href: URL.createObjectURL(blob), download: `mediaboss_nfo_${ids.length}.zip` });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}
