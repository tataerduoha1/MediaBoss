/** JAV 库：封面墙 + 多维筛选（女优/厂商/系列/类别）+ 列表与详情 */
import { api } from "../api.js?v=22";
import { h, debounce, toast, confirmModal, promptModal, modal, fmtDur, fmtSize, fmtAgo, stars, lazyimg, pageMem, isLocal } from "../util.js?v=22";
import { javCard, pager, skeletonGrid, emptyState, ratingStars, favBtn } from "../components.js?v=22";

export async function render(view, params, query) {
  document.title = "JAV 库 · MediaBoss";
  const memKey = "/jav" + JSON.stringify(query || {});
  const state = {
    q: query.q || "", sort: "created", order: "desc", page: pageMem.get(memKey),
    actress_id: query.actress_id || "", studio_id: query.studio_id || "",
    series_id: query.series_id || "", genre_id: query.genre_id || "",
    favorite: "", watched: "", unscraped: "",
    prefix: query.prefix || "",
  };
  view.innerHTML = "";
  view.append(h("div", { class: "page-head" }, h("h1", {}, "JAV 库")));
  const toolbar = h("div", { class: "toolbar" });
  const gridHolder = h("div", {});
  const pagerHolder = h("div", {});
  view.append(toolbar, gridHolder, pagerHolder);

  const search = h("input", { class: "input", type: "text", placeholder: "番号 / 标题 / 女优", value: state.q });
  search.style.width = "170px";
  search.addEventListener("input", debounce(() => { state.q = search.value.trim(); state.page = 1; load(); }, 400));
  const mkSel = (opts, key, allLabel) => {
    const sel = h("select", { class: "input" }, h("option", { value: "" }, allLabel),
      opts.map((o) => h("option", { value: o[0], selected: String(state[key]) === String(o[0]) }, o[1])));
    sel.addEventListener("change", () => { state[key] = sel.value; state.page = 1; load(); });
    return sel;
  };
  toolbar.append(
    search,
    mkSel([["1", "已看"], ["0", "未看"]], "watched", "观看状态"),
    mkSel([["1", "已收藏"]], "favorite", "收藏"),
    mkSel([["1", "只看失败"]], "unscraped", "刮削状态"),
    mkSel([["created", "添加时间"], ["date", "发行日期"], ["score", "站点评分"], ["rating", "我的评分"],
      ["play_count", "播放次数"], ["code", "番号"], ["size", "大小"], ["duration", "时长"], ["random", "随机"]], "sort", "排序:添加时间"),
    mkSel([["desc", "降序"], ["asc", "升序"]], "order", "降序"),
    h("span", { class: "cnt", id: "j-cnt" }),
  );
  // 番号首字母快速筛选条
  const prefixBar = h("div", { class: "prefix-bar" });
  const setPrefix = (p) => {
    state.prefix = p; state.page = 1;
    for (const b of prefixBar.querySelectorAll(".pb-item")) b.classList.toggle("on", b.dataset.p === p);
    load();
  };
  const pbItem = (p, label) => h("button", {
    class: "pb-item" + (state.prefix === p ? " on" : ""), "data-p": p, onclick: () => setPrefix(p),
  }, label);
  prefixBar.append(pbItem("", "全部"),
    ..."ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("").map((L) => pbItem(L, L)),
    pbItem("0-9", "0-9"), pbItem("#", "#"));
  view.insertBefore(prefixBar, gridHolder); // 筛选条置于 toolbar 与网格之间
  // 实体筛选下拉（异步填充）
  const entitySels = {};
  for (const [key, url, label] of [["actress_id", "/actresses?sort=video_count", "女优"],
    ["studio_id", "/studios", "厂商"], ["series_id", "/series", "系列"], ["genre_id", "/genres", "类别"]]) {
    const sel = h("select", { class: "input" }, h("option", { value: "" }, `${label}:全部`));
    sel.addEventListener("change", () => { state[key] = sel.value; state.page = 1; load(); });
    entitySels[key] = sel;
    toolbar.append(sel);
  }
  api.get("/actresses?sort=video_count").then((rows) => fillSel(entitySels.actress_id, rows, state.actress_id)).catch(() => {});
  api.get("/studios").then((rows) => fillSel(entitySels.studio_id, rows, state.studio_id)).catch(() => {});
  api.get("/series").then((rows) => fillSel(entitySels.series_id, rows, state.series_id)).catch(() => {});
  api.get("/genres").then((rows) => fillSel(entitySels.genre_id, rows, state.genre_id)).catch(() => {});

  function fillSel(sel, rows, cur) {
    for (const r of rows.slice(0, 300)) {
      sel.append(h("option", { value: r.id, selected: String(cur) === String(r.id) }, `${r.name} (${r.video_count})`));
    }
  }

  async function load() {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(state)) if (v !== "" && k !== "page") qs.set(k, v);
    qs.set("page", state.page);
    pageMem.set(memKey, state.page);  // 记住页码，详情返回时恢复
    gridHolder.replaceChildren(skeletonGrid(12, true));
    pagerHolder.replaceChildren();
    try {
      const r = await api.get(`/jav?${qs}`);
      toolbar.querySelector(".cnt").textContent = `共 ${r.total} 部`;
      if (!r.items.length) {
        gridHolder.replaceChildren(emptyState("💋", "没有匹配的影片",
          "刮削成功后影片会出现在这里；可先到视频库查看已扫描文件"));
        return;
      }
      gridHolder.replaceChildren(h("div", { class: "grid javg" }, r.items.map(javCard)));
      pagerHolder.replaceChildren(pager({ ...r, onPage: (p) => { state.page = p; load(); } }));
    } catch (e) {
      gridHolder.replaceChildren(emptyState("⚠️", e.message));
    }
  }
  load();
}

/* ================= 详情页 ================= */
export async function renderDetail(view, params) {
  const jid = params[1];
  view.innerHTML = "";
  const holder = h("div", {}, "加载中…");
  view.append(holder);
  document.title = "详情 · MediaBoss";

  let r;
  try { r = await api.get(`/jav/${jid}`); } catch (e) {
    holder.replaceChildren(emptyState("⚠️", e.message, ""));
    return;
  }
  const { jav: j, video: v, related } = r;
  document.title = `${j.code} · MediaBoss`;
  holder.replaceChildren(buildDetail(j, v, related, holder));
}

function buildDetail(j, v, related, holder) {
  const metalist = h("div", { class: "metalist" });
  const addMeta = (k, val) => { if (val) metalist.append(h("div", { class: "k" }, k), h("div", { class: "v" }, val)); };
  addMeta("发行日期", j.release_date);
  addMeta("时长", fmtDur(j.duration_sec));
  addMeta("厂商", h("a", { class: "lnk", href: `#/jav?studio_id=${j.studio_id}` }, j.studio));
  addMeta("系列", h("a", { class: "lnk", href: `#/jav?series_id=${j.series_id}` }, j.series));
  addMeta("导演", j.director);
  addMeta("文件", `${v.ext?.toUpperCase() || ""} · ${fmtSize(v.size)} · ${v.width ? `${v.width}x${v.height}` : ""}`);
  addMeta("添加", fmtAgo(v.created_at));
  addMeta("播放", `${v.play_count || 0} 次${v.watched ? " · 已看完" : ""}`);

  // 评分
  const ratingWrap = ratingStars(v.rating, async (n) => {
    await api.patch(`/videos/${v.id}`, { rating: n });
    toast(`评分 ${n} 星`, "ok", 1500);
  });
  // 收藏
  const item = { id: v.id, favorite: v.favorite };
  // 标签
  let tagList = h("div", { class: "chips" });
  const renderTags = (tags) => {
    tagList.replaceChildren(...tags.map((t) => h("span", { class: "chip" }, t)),
      h("span", { class: "chip", onclick: editTags }, "＋ 编辑标签"));
  };
  const editTags = () => {
    promptModal("编辑标签（逗号分隔）", [{ key: "tags", label: "标签", value: tags.join(", ") }],
      async ({ tags: raw }) => {
        const names = raw.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
        const rr = await api.post(`/videos/${v.id}/tags`, { tags: names });
        tags = rr.tags;
        renderTags(tags);
      });
  };
  let tags = [];
  api.get(`/videos/${v.id}`).then((vd) => { tags = vd.tags; renderTags(tags); }).catch(() => {});
  renderTags(tags);

  const playBtn = h("a", { class: "btn primary", href: `#/player/${v.id}` }, "▶ 网页播放");
  // mpv 是唤起服务器本机的外部播放器，仅服务器本机浏览时显示（手机端点会在电脑上弹窗口）
  const mpvBtn = isLocal() ? h("button", {
    class: "btn", onclick: async () => {
      try { await api.post(`/videos/${v.id}/mpv`, {}); toast("已调用 mpv 播放", "ok"); }
      catch (e) { toast(e.message, "err"); }
    },
  }, "🖥 mpv 播放") : null;
  const rescrapeBtn = h("button", {
    class: "btn", onclick: async () => {
      try { await api.post(`/jav/${j.id}/rescrape`); toast("已加入刮削队列", "ok"); }
      catch (e) { toast(e.message, "err"); }
    },
  }, "🔄 重新刮削");
  const nfoBtn = h("a", { class: "btn", href: `/api/videos/${v.id}/nfo`, download: "" }, "📄 导出 NFO");
  const editBtn = h("button", {
    class: "btn", onclick: () => {
      promptModal("编辑信息", [
        { key: "title", label: "标题", value: j.title || "" },
        { key: "cn_title", label: "中文标题", value: j.cn_title || "" },
        { key: "director", label: "导演", value: j.director || "" },
      ], async (vals) => {
        await api.patch(`/jav/${j.id}`, vals);
        toast("已保存", "ok");
        renderDetail(holder.closest(".view") || holder.parentElement, { 1: j.id });
      });
    },
  }, "✏️ 编辑");

  /* ---- A2 自选海报：8 等分抽帧 ---- */
  const coverBox = j.cover_url ? lazyimg(j.cover_url, j.code)
    : h("div", { class: "ph", style: "aspect-ratio:2/2.85;display:grid;place-items:center;background:var(--card);border:1px solid var(--border);border-radius:10px;color:var(--faint);font-size:40px" }, "🎞");
  const pickPoster = () => {
    modal((box, close) => {
      box.append(h("h3", { style: "margin-top:0" }, "🖼 自选海报"),
        h("p", { class: "mut", style: "margin:0 0 12px;font-size:12.5px" },
          "按时长 8 等分抽帧，点击一帧即设为封面（Emby/Kodi 导出也使用此封面）"));
      const grid = h("div", { class: "poster-picker" });
      for (let i = 0; i < 8; i++) {
        const cell = h("button", { class: "pf", title: `第 ${i + 1} 帧` });
        cell.append(lazyimg(`/api/videos/${v.id}/frames/${i}?n=8&_p${i}`, `frame-${i}`));
        cell.addEventListener("click", async () => {
          cell.disabled = true; cell.style.opacity = ".5";
          try {
            const r = await api.post(`/videos/${v.id}/poster`, { n: 8, idx: i });
            toast("海报已更新", "ok", 1500);
            close();
            if (coverBox.tagName === "IMG") coverBox.src = r.poster_url;
            else renderDetail(holder.closest(".view") || holder.parentElement, { 1: j.id });
          } catch (e) { toast(e.message, "err"); cell.disabled = false; cell.style.opacity = ""; }
        });
        grid.append(cell);
      }
      box.append(grid, h("div", { class: "acts" },
        h("button", {
          class: "btn", onclick: async () => {
            try {
              await api.del(`/videos/${v.id}/poster`);
              toast("已恢复默认封面", "ok", 1500);
              close();
              if (coverBox.tagName === "IMG") coverBox.src = `/api/videos/${v.id}/cover?t=${Date.now()}`;
              else renderDetail(holder.closest(".view") || holder.parentElement, { 1: j.id });
            } catch (e) { toast(e.message, "err"); }
          },
        }, "恢复默认封面"),
        h("button", { class: "btn primary", onclick: close }, "完成")));
    });
  };

  /* ---- A9 加入片单 ---- */
  const pickCollection = () => {
    modal(async (box, close) => {
      box.append(h("h3", { style: "margin-top:0" }, "📋 加入片单"));
      const listWrap = h("div", { class: "coll-pick" }, "加载中…");
      box.append(listWrap, h("div", { class: "acts" },
        h("button", { class: "btn primary", onclick: close }, "完成")));
      try {
        const [all, mine] = await Promise.all([
          api.get("/collections"), api.get(`/videos/${v.id}/collections`)]);
        const memberIds = new Set(mine.ids);
        const newInput = h("input", { class: "input", placeholder: "输入名称回车，新建片单并加入" });
        listWrap.replaceChildren(
          ...all.items.map((c) => {
            const cb = h("input", { type: "checkbox" });
            cb.checked = memberIds.has(c.id);
            cb.addEventListener("change", async () => {
              try {
                if (cb.checked) await api.post(`/collections/${c.id}/items`, { video_id: v.id });
                else await api.del(`/collections/${c.id}/items/${v.id}`);
              } catch (e) { toast(e.message, "err"); cb.checked = !cb.checked; }
            });
            return h("label", { class: "coll-row" }, cb,
              h("span", { class: "nm" }, c.name),
              h("span", { class: "mut" }, `${c.count} 部`));
          }),
          newInput);
        if (!all.items.length) {
          listWrap.insertBefore(h("p", { class: "mut", style: "font-size:12.5px;margin:0 0 8px" },
            "还没有片单，在下方输入名称创建第一个："), newInput);
        }
        newInput.addEventListener("keydown", async (e) => {
          if (e.key === "Enter" && newInput.value.trim()) {
            try {
              const r = await api.post("/collections", { name: newInput.value.trim() });
              await api.post(`/collections/${r.id}/items`, { video_id: v.id });
              toast(`已创建「${r.name}」并加入`, "ok");
              close();
            } catch (err) { toast(err.message, "err"); }
          }
        });
        if (all.items.length) setTimeout(() => newInput.focus(), 60);
      } catch (e) { listWrap.replaceChildren(h("span", { class: "mut" }, e.message)); }
    });
  };

  const wrap = h("div", {},
    h("div", { class: "detail" },
      h("div", { class: "cover-col" },
        coverBox,
        h("div", { class: "cover-acts" },
          h("button", { class: "btn sm", onclick: pickPoster, title: "从视频抽帧自选封面" }, "🖼 自选海报"),
          h("button", { class: "btn sm", onclick: pickCollection, title: "加入/移出片单" }, "📋 加入片单"))),
      h("div", { class: "info-col" },
        h("div", { class: "code" }, j.code),
        h("h1", { class: "title" }, j.title || "(未刮削到标题)"),
        h("div", { class: "cn" }, j.cn_title || ""),
        h("div", { class: "btn-row" },
          h("span", { style: "align-self:center" }, ratingWrap),
          favBtn(item, (fav) => toast(fav ? "已收藏" : "已取消收藏", "ok", 1200)),
        ),
        metalist,
        // 女优
        j.actresses?.length ? [
          h("div", { class: "section-h", style: "margin:10px 0 10px" }, h("h2", {}, "女优")),
          h("div", { class: "chips" }, j.actresses.map((a) =>
            h("a", { class: "chip", href: `#/jav?actress_id=${a.id}` }, a.name))),
        ] : null,
        // 类别
        j.genres?.length ? [
          h("div", { class: "section-h", style: "margin:14px 0 10px" }, h("h2", {}, "类别")),
          h("div", { class: "chips" }, j.genres.map((g) => h("span", { class: "chip" }, g))),
        ] : null,
        // 标签
        h("div", { class: "section-h", style: "margin:14px 0 10px" }, h("h2", {}, "标签")),
        tagList,
        h("div", { class: "btn-row", style: "margin-top:20px" },
          playBtn, mpvBtn, rescrapeBtn, nfoBtn, editBtn),
      ),
    ),
    related?.length ? [
      h("div", { class: "section-h" }, h("h2", {}, "相关推荐")),
      h("div", { class: "grid javg" }, related.map((rl) => javCard({
        id: rl.id, video_id: rl.video_id, code: rl.code, title: rl.title,
        cover_path: rl.cover_path ? "1" : "", actresses: [],
      }))),
    ] : null,
  );
  return wrap;
}
