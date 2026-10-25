/** 视频库：网格 + 筛选/排序/搜索 + 分页 */
import { api } from "../api.js?v=4";
import { h, debounce, toast, confirmModal, pageMem } from "../util.js?v=4";
import { videoCard, pager, skeletonGrid, emptyState } from "../components.js?v=4";

export async function render(view, params, query) {
  document.title = "视频库 · MediaBoss";
  const memKey = "/videos" + JSON.stringify(query || {});
  const state = {
    q: query.q || "",
    sort: "created", order: "desc", page: pageMem.get(memKey),
    watched: "", favorite: "", min_rating: "", tag: "", ext: "", dir_id: query.dir_id || "",
  };
  view.innerHTML = "";
  const head = h("div", { class: "page-head" }, h("h1", {}, "视频库"));
  const toolbar = h("div", { class: "toolbar" });
  const gridHolder = h("div", {});
  const pagerHolder = h("div", {});
  view.append(head, toolbar, gridHolder, pagerHolder);

  // 批量整理入口
  const organizeBtn = h("button", { class: "btn sm" }, "🗂 整理");
  organizeBtn.addEventListener("click", () => organizeDialog());
  head.append(organizeBtn);

  // 筛选控件
  const search = h("input", { class: "input", type: "text", placeholder: "搜索…", value: state.q });
  search.addEventListener("input", debounce(() => { state.q = search.value.trim(); state.page = 1; load(); }, 400));
  const mkSel = (opts, key, allLabel) => {
    const sel = h("select", { class: "input" },
      h("option", { value: "" }, allLabel),
      opts.map((o) => h("option", { value: o[0] }, o[1])));
    sel.addEventListener("change", () => { state[key] = sel.value; state.page = 1; load(); });
    return sel;
  };
  toolbar.append(
    search,
    mkSel([["1", "已看"], ["0", "未看"]], "watched", "观看状态"),
    mkSel([["1", "已收藏"]], "favorite", "收藏"),
    mkSel([["1", "★+"], ["2", "★★+"], ["3", "★★★+"], ["4", "★★★★+"], ["5", "★★★★★"]], "min_rating", "评分"),
    mkSel([["mp4", "MP4"], ["mkv", "MKV"], ["wmv", "WMV"], ["avi", "AVI"], ["ts", "TS"]], "ext", "格式"),
    mkSel([["created", "添加时间"], ["mtime", "文件时间"], ["size", "大小"], ["duration", "时长"],
      ["rating", "我的评分"], ["play_count", "播放次数"], ["last_played", "最后播放"], ["title", "标题"],
      ["random", "随机"]], "sort", "排序:添加时间"),
    mkSel([["desc", "降序"], ["asc", "升序"]], "order", "降序"),
    h("span", { class: "cnt", id: "v-cnt" }),
  );
  toolbar.querySelector("select.input").style.minWidth = "150px";
  search.style.width = "170px";

  async function load() {
    pageMem.set(memKey, state.page);  // 记住页码，详情返回时恢复
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(state)) if (v !== "" && k !== "page") qs.set(k, v);
    qs.set("page", state.page);
    gridHolder.replaceChildren(skeletonGrid(12));
    pagerHolder.replaceChildren();
    try {
      const r = await api.get(`/videos?${qs}`);
      toolbar.querySelector(".cnt").textContent = `共 ${r.total} 个视频`;
      if (!r.items.length) {
        gridHolder.replaceChildren(emptyState("🎬", "没有匹配的视频",
          state.q ? "换个关键词试试，或先在设置中添加媒体目录并扫描" : "添加媒体目录后开始扫描"));
        return;
      }
      gridHolder.replaceChildren(h("div", { class: "grid" }, r.items.map(videoCard)));
      pagerHolder.replaceChildren(pager({ ...r, onPage: (p) => { state.page = p; load(); } }));
    } catch (e) {
      gridHolder.replaceChildren(emptyState("⚠️", e.message));
    }
  }

  async function organizeDialog() {
    try {
      const plan = await api.post("/videos/organize/preview", {});
      if (!plan.items?.length) { toast("没有需要整理的文件", "info"); return; }
      confirmModal("整理预览",
        `将按模板「${plan.template}」重命名 ${plan.items.length} 个已刮削的文件（原地改名，不移动目录）。确认执行？`,
        async () => {
          const r2 = await api.post("/videos/organize/apply", { items: plan.items });
          toast(`整理完成：成功 ${r2.ok} 个${r2.failed ? `，失败 ${r2.failed} 个` : ""}`, r2.failed ? "info" : "ok");
          load();
        });
    } catch (e) { toast(e.message, "err"); }
  }

  load();
}
