/** 片单/合集（A9）：列表卡片 + 详情网格管理（增删条目、设封面、改名、删除）。 */
import { api } from "../api.js?v=17";
import { h, toast, confirmModal, promptModal, fmtSize, fmtDur, lazyimg, fmtAgo } from "../util.js?v=17";
import { javCard, skeletonGrid, emptyState } from "../components.js?v=17";

export async function render(view) {
  document.title = "片单 · MediaBoss";
  view.innerHTML = "";
  const newBtn = h("button", { class: "btn primary", onclick: newCollection }, "＋ 新建片单");
  view.append(h("div", { class: "page-head" }, h("h1", {}, "📋 片单"), newBtn));
  const holder = h("div", {});
  view.append(holder);

  function newCollection() {
    promptModal("新建片单", [
      { key: "name", label: "名称", placeholder: "如：2026 精选" },
      { key: "description", label: "描述（可选）", placeholder: "" },
    ], async (vals) => {
      if (!vals.name.trim()) { toast("名称不能为空", "err"); return; }
      try {
        await api.post("/collections", { name: vals.name.trim(), description: vals.description.trim() });
        toast("已创建", "ok", 1500);
        load();
      } catch (e) { toast(e.message, "err"); }
    });
  }

  async function load() {
    holder.replaceChildren(skeletonGrid(6));
    try {
      const r = await api.get("/collections");
      if (!r.items.length) {
        holder.replaceChildren(emptyState("📋", "还没有片单",
          "在 JAV 详情页点「＋ 加入片单」把喜欢的影片归类整理"));
        return;
      }
      holder.replaceChildren(h("div", { class: "coll-grid" }, r.items.map(collCard)));
    } catch (e) {
      holder.replaceChildren(emptyState("⚠️", e.message));
    }
  }

  function collCard(c) {
    const cover = h("div", { class: "cover cv-coll" });
    if (c.cover_video_id) {
      cover.append(lazyimg(`/api/videos/${c.cover_video_id}/cover`, c.name));
    } else {
      cover.append(h("div", { class: "ph", style: "aspect-ratio:16/9;display:grid;place-items:center;background:var(--surface2);color:var(--faint);font-size:34px" }, "📋"));
    }
    return h("a", { class: "vcard coll-card", href: `#/collections/${c.id}` },
      cover,
      h("div", { class: "meta" },
        h("div", { class: "t", title: c.name }, c.name),
        h("div", { class: "s" }, h("span", {}, `${c.count} 部`),
          c.description ? h("span", { class: "desc", title: c.description }, c.description) : null)),
    );
  }

  load();
}

/* ================= 详情页 ================= */
export async function renderDetail(view, params) {
  const cid = params[1];
  document.title = "片单详情 · MediaBoss";
  view.innerHTML = "";
  const holder = h("div", {}, "加载中…");
  view.append(holder);

  let r;
  try { r = await api.get(`/collections/${cid}`); } catch (e) {
    holder.replaceChildren(emptyState("⚠️", e.message, ""));
    return;
  }
  document.title = `${r.collection.name} · MediaBoss`;
  holder.replaceChildren(buildDetail(r.collection, r.items, holder));
}

function buildDetail(c, items, holder) {
  const reload = () => renderDetail(holder.closest(".view") || holder.parentElement, { 1: c.id });

  const renameBtn = h("button", { class: "btn sm" }, "✏️ 重命名");
  renameBtn.addEventListener("click", () => {
    promptModal("编辑片单", [
      { key: "name", label: "名称", value: c.name },
      { key: "description", label: "描述", value: c.description || "" },
    ], async (vals) => {
      if (!vals.name.trim()) { toast("名称不能为空", "err"); return; }
      try { await api.patch(`/collections/${c.id}`, vals); toast("已保存", "ok", 1500); reload(); }
      catch (e) { toast(e.message, "err"); }
    });
  });
  const delBtn = h("button", { class: "btn sm danger" }, "🗑 删除片单");
  delBtn.addEventListener("click", () => {
    confirmModal("删除片单", `删除「${c.name}」？片单本身删除，影片文件与库内元数据不受影响。`,
      async () => { await api.del(`/collections/${c.id}`); location.hash = "#/collections"; }, true);
  });

  const grid = h("div", { class: "grid javg" });
  for (const it of items) {
    it._cid = c.id; // 详情接口未返回 collection_id，注入供条目操作使用
    grid.append(collItemCard(it, reload));
  }

  return h("div", {},
    h("div", { class: "page-head" },
      h("h1", {}, `📋 ${c.name}`),
      h("div", { style: "display:flex;gap:9px" }, renameBtn, delBtn)),
    h("p", { style: "color:var(--muted);margin:-6px 0 16px;font-size:13px" },
      `${c.count} 部${c.description ? ` · ${c.description}` : ""}`),
    items.length ? grid : emptyState("📭", "片单还是空的", "到 JAV 库 / 详情页点「＋ 加入片单」添加影片"));
}

/** 片单条目卡：jav 有记录 → 详情页；纯视频 → 播放页。带「设为封面 / 移除」操作。 */
function collItemCard(it, reload) {
  const inner = it.jid
    ? javCard({
        id: it.jid, video_id: it.video_id, code: it.code, title: it.title, cn_title: it.cn_title,
        cover_url: it.cover_url, cover_path: it.cover_path ? "1" : "", thumb_url: it.thumb_url,
        size: it.size, duration_sec: it.duration, favorite: it.favorite, watched: it.watched,
        actresses: [],
      })
    : h("a", { class: "vcard", href: `#/player/${it.video_id}` },
        h("div", { class: "cover" }, lazyimg(it.thumb_url || it.cover_url, it.title)),
        h("div", { class: "meta" },
          h("div", { class: "t" }, it.title || it.filename || `视频 #${it.video_id}`),
          h("div", { class: "s" }, h("span", {}, fmtSize(it.size)), h("span", {}, fmtDur(it.duration)))));

  const coverBtn = h("button", {
    class: "mini", title: "设为片单封面", onclick: async (e) => {
      e.preventDefault(); e.stopPropagation();
      try { await api.patch(`/collections/${it._cid}`, { cover_video_id: it.video_id }); toast("封面已更新", "ok", 1300); reload(); }
      catch (err) { toast(err.message, "err"); }
    },
  }, "🖼");
  const rmBtn = h("button", {
    class: "mini", title: "从片单移除", onclick: async (e) => {
      e.preventDefault(); e.stopPropagation();
      try { await api.del(`/collections/${it._cid}/items/${it.video_id}`); toast("已移除", "ok", 1300); reload(); }
      catch (err) { toast(err.message, "err"); }
    },
  }, "✖");
  inner.style.position = "relative";
  inner.append(h("div", { class: "coll-acts" }, coverBtn, rmBtn));
  return inner;
}
