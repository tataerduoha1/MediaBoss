/** 观看历史：同视频一条记录、显示进度、点击续播、单删/批删/清空。 */
import { api } from "../api.js?v=4";
import { h, fmtDur, toast, confirmModal } from "../util.js?v=4";
import { pager, emptyState } from "../components.js?v=4";

export async function render(view) {
  document.title = "观看历史 · MediaBoss";
  const state = { page: 1, selected: new Set() };
  view.innerHTML = "";
  view.append(h("div", { class: "page-head" }, h("h1", {}, "🕘 观看历史")));

  /* ---- 工具栏 ---- */
  const selAll = h("input", { type: "checkbox", title: "全选本页" });
  const delSelBtn = h("button", { class: "btn sm danger", disabled: true }, "删除所选");
  const clearBtn = h("button", { class: "btn sm danger" }, "🗑 清空全部");
  const toolbar = h("div", { class: "toolbar", style: "margin-bottom:14px" },
    h("label", { class: "chk-wrap", style: "display:inline-flex;align-items:center;gap:7px;cursor:pointer;font-size:13px;color:var(--muted)" },
      selAll, "全选"),
    h("div", { class: "sep" }),
    delSelBtn, clearBtn);
  view.append(toolbar);

  const list = h("div", {});
  const pagerHolder = h("div", {});
  view.append(list, pagerHolder);

  const refreshSel = () => {
    delSelBtn.disabled = !state.selected.size;
    delSelBtn.textContent = state.selected.size ? `删除所选（${state.selected.size}）` : "删除所选";
    selAll.checked = list.querySelectorAll(".hrow input[type=checkbox]:checked").length > 0
      && list.querySelectorAll(".hrow").length > 0
      && state.selected.size >= list.querySelectorAll(".hrow").length;
  };

  selAll.addEventListener("change", () => {
    for (const cb of list.querySelectorAll(".hrow input[type=checkbox]")) {
      cb.checked = selAll.checked;
      const vid = Number(cb.dataset.vid);
      if (selAll.checked) state.selected.add(vid); else state.selected.delete(vid);
    }
    refreshSel();
  });

  const deleteItems = async (vids, tip) => {
    try {
      if (vids.length === 1) await api.del(`/history/${vids[0]}`);
      else await api.post("/history/batch-delete", { video_ids: vids });
      toast(tip, "ok");
      state.selected.clear();
      load();
    } catch (e) { toast(e.message, "err"); }
  };

  delSelBtn.addEventListener("click", () => {
    if (!state.selected.size) return;
    confirmModal("删除所选记录",
      `将删除 ${state.selected.size} 条观看记录（不影响视频文件与播放进度）`,
      () => deleteItems([...state.selected], "已删除所选记录"), true);
  });
  clearBtn.addEventListener("click", () => {
    confirmModal("清空观看历史", "将删除全部观看记录（不影响视频文件与播放进度）",
      async () => {
        try { await api.del("/history"); toast("已清空", "ok"); state.selected.clear(); load(); }
        catch (e) { toast(e.message, "err"); }
      }, true);
  });

  /* ---- 行封面：缩略图失败退到番号渐变占位 ---- */
  const coverNode = (it) => {
    const code = it.code || "";
    const wrap = h("div", { class: "cv" });
    const mkPh = () => {
      if (code) {
        let hue = 0;
        for (const ch of code) hue = (hue * 31 + ch.charCodeAt(0)) % 360;
        return h("div", { class: "ph-code", style: `position:relative;background:linear-gradient(135deg,hsl(${hue},42%,26%),hsl(${(hue + 50) % 360},48%,13%))` },
          h("span", {}, code));
      }
      return h("div", { style: "position:relative;display:grid;place-items:center;height:100%;color:var(--faint)" }, "🎬");
    };
    const img = h("img", { loading: "lazy", alt: "" });
    img.addEventListener("error", () => img.replaceWith(mkPh()), { once: true });
    img.src = it.cover_url || `/api/videos/${it.video_id}/thumbnail`;
    wrap.append(img);
    return wrap;
  };

  async function load() {
    list.replaceChildren(h("div", { style: "color:var(--faint);padding:30px;text-align:center" }, "加载中…"));
    pagerHolder.replaceChildren();
    try {
      const r = await api.get(`/history?page=${state.page}&page_size=50`);
      if (!r.items.length) {
        list.replaceChildren(emptyState("🕘", "暂无观看记录", "去视频库挑一部开始看吧"));
        toolbar.style.display = "none";
        return;
      }
      toolbar.style.display = "";
      state.selected.clear();
      refreshSel();
      list.replaceChildren(...r.items.map((it) => {
        const cb = h("input", { type: "checkbox" });
        cb.dataset.vid = it.video_id;
        cb.addEventListener("change", () => {
          if (cb.checked) state.selected.add(it.video_id); else state.selected.delete(it.video_id);
          refreshSel();
        });
        cb.addEventListener("click", (e) => e.stopPropagation());
        const delOne = h("button", {
          class: "btn sm danger", title: "删除这条记录",
          onclick: (e) => {
            e.stopPropagation();
            confirmModal("删除记录", `删除「${(it.title || it.filename || "").slice(0, 40)}」的观看记录？`,
              () => deleteItems([it.video_id], "已删除"), true);
          },
        }, "✕");
        const prog = it.seconds > 0 ? ` · 看到 ${fmtDur(it.seconds)}` : "";
        return h("div", { class: "hrow", onclick: () => { location.hash = `#/player/${it.video_id}`; } },
          cb,
          coverNode(it),
          h("div", { class: "inf" },
            h("div", { class: "t" }, it.code ? `${it.code} · ${it.title || it.filename}` : (it.title || it.filename)),
            h("div", { class: "s" }, `${it.started_at_fmt}${prog}`)),
          delOne);
      }));
      pagerHolder.replaceChildren(pager({ ...r, onPage: (p) => { state.page = p; load(); } }));
    } catch (e) {
      list.replaceChildren(emptyState("⚠️", e.message));
    }
  }
  load();
}
