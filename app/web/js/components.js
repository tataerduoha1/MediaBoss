/** 共享 UI 组件：卡片、分页、骨架屏、空状态。 */
import { h, fmtSize, fmtDur, lazyimg, toast } from "./util.js?v=17";
import { api } from "./api.js?v=17";

/** 封面缺失时的美观占位：有番号则用番号稳定哈希生成双色渐变 + 大字番号。 */
function coverPh(item) {
  const code = item.code || "";
  if (code) {
    let hue = 0;
    for (const ch of code) hue = (hue * 31 + ch.charCodeAt(0)) % 360;
    return h("div", { class: "ph-code",
      style: `background:linear-gradient(135deg,hsl(${hue},42%,26%),hsl(${(hue + 50) % 360},48%,13%))` },
      h("span", {}, code));
  }
  return h("div", { class: "ph" }, "🎬");
}

function coverEl(item) {
  // 封面优先级：刮削封面(cover_url/cover_path) > ffmpeg 缩略图 > 美观占位
  const src = item.cover_url
    || (item.cover_path ? `/api/videos/${item.video_id ?? item.id}/cover` : "")
    || item.thumb_url || "";
  const cover = h("div", { class: "cover" });
  if (src) {
    const img = lazyimg(src, item.title || item.cn_title || item.code || "");
    img.addEventListener("error", () => img.replaceWith(coverPh(item)), { once: true });
    cover.append(img);
  } else {
    cover.append(coverPh(item));
  }
  if (item.duration || item.duration_sec) {
    cover.append(h("div", { class: "dur" }, fmtDur(item.duration || item.duration_sec)));
  }
  if (item.favorite) cover.append(h("div", { class: "badge-fav" }, "♥"));
  if (item.watched) cover.append(h("div", { class: "watched-mark" }, "已看"));
  return cover;
}

export function videoCard(v) {
  const card = h("a", { class: "vcard", href: `#/player/${v.id}` }, coverEl(v),
    h("div", { class: "meta" },
      h("div", { class: "t", title: v.title || v.filename }, v.title || v.filename),
      h("div", { class: "s" },
        h("span", {}, fmtSize(v.size)),
        v.code ? h("span", { style: "color:var(--accent-h);font-weight:700" }, v.code) : null,
        h("span", {}, v.width ? `${v.width}x${v.height}` : ""),
      ),
    ),
  );
  if (v.resume_position && v.duration && v.resume_position / v.duration > 0.02
      && v.resume_position / v.duration < 0.9) {
    card.append(h("div", { class: "prog", style: `width:${(v.resume_position / v.duration * 100).toFixed(1)}%` }));
  }
  return card;
}

export function javCard(j) {
  const card = h("a", { class: "vcard jmode", href: `#/jav/${j.id}` },
    coverEl(j),
    h("div", { class: "meta" },
      h("div", { class: "code-line" }, j.code),
      h("div", { class: "t", title: j.cn_title || j.title || j.code }, j.cn_title || j.title || j.code),
      h("div", { class: "acts" }, (j.actresses || []).map((a) => a.name).join(" / ")),
      h("div", { class: "s" },
        h("span", {}, j.release_date || ""),
        h("span", {}, fmtSize(j.size)),
      ),
    ),
  );
  return card;
}

export function entityCard(e, { square = false, avatarUrl = null } = {}) {
  const avatar = h("div", { class: "avatar" }, (e.name || "?").slice(0, 1).toUpperCase());
  if (avatarUrl && e.avatar_url !== false) {
    const img = lazyimg(avatarUrl, e.name);
    img.addEventListener("error", () => img.remove(), { once: true });
    avatar.prepend(img);
  }
  // 影片数：实体库端点用 video_count，仪表盘端点用 count，兜底 0 防 "undefined 部"
  const cnt = e.video_count ?? e.count ?? 0;
  const card = h("a", { class: `ecard ${square ? "sq" : ""}`, href: e.href },
    avatar,
    h("div", { class: "name", title: e.name }, e.name),
    h("div", { class: "cnt" }, `${cnt} 部`),
  );
  return card;
}

export function skeletonGrid(n = 12, jmode = false) {
  const g = h("div", { class: `grid ${jmode ? "javg" : ""}` });
  for (let i = 0; i < n; i++) {
    g.append(h("div", { class: "skel" }, h("div", { class: "cover-ph", style: jmode ? "aspect-ratio:2/2.85" : "" }),
      h("div", { style: "height:36px" })));
  }
  return g;
}

export function emptyState(icon = "📭", text = "暂无内容", hint = "") {
  return h("div", { class: "empty" },
    h("div", { class: "big" }, icon),
    h("p", {}, text),
    hint ? h("p", { class: "hint" }, hint) : null,
  );
}

export function pager({ page, total, page_size, onPage }) {
  const pages = Math.max(1, Math.ceil(total / page_size));
  if (pages <= 1) return h("div");
  const cur = Math.min(page, pages);
  const nums = [];
  const push = (n) => { if (!nums.includes(n) && n >= 1 && n <= pages) nums.push(n); };
  push(1); push(pages);
  for (let d = 0; d <= 2; d++) { push(cur - d); push(cur + d); }
  push(cur - 5 > 1 ? cur - 5 : 2);
  push(cur + 5 < pages ? cur + 5 : pages - 1);
  nums.sort((a, b) => a - b);
  const bar = h("div", { class: "pager" });
  const mk = (label, target, dis = false) =>
    h("button", { class: "pg", disabled: dis || target < 1 || target > pages, onclick: () => onPage(target) }, label);
  bar.append(mk("‹", cur - 1, cur <= 1));
  let last = 0;
  for (const n of nums) {
    if (n - last > 1) bar.append(h("span", { class: "info" }, "…"));
    bar.append(h("button", { class: `pg ${n === cur ? "on" : ""}`, onclick: () => onPage(n) }, n));
    last = n;
  }
  bar.append(mk("›", cur + 1, cur >= pages));
  bar.append(h("span", { class: "info" }, `${total} 条`));
  return bar;
}

/** 评分小组件（5 星，可点击）。 */
export function ratingStars(current, onSet) {
  const wrap = h("span", { class: "score-stars", title: "点击评分" });
  const draw = () => { wrap.textContent = "★".repeat(current || 0) + "☆".repeat(5 - (current || 0)); };
  draw();
  wrap.addEventListener("click", async (e) => {
    const rect = wrap.getBoundingClientRect();
    const n = Math.max(0, Math.min(5, Math.ceil((e.clientX - rect.left) / rect.width * 5)));
    try { await onSet(n); current = n; draw(); } catch (err) { toast(err.message, "err"); }
  });
  return wrap;
}

/** 收藏按钮 */
export function favBtn(item, onToggle) {
  const b = h("button", { class: "btn sm", title: "收藏" });
  const draw = () => { b.textContent = item.favorite ? "♥ 已收藏" : "♡ 收藏"; };
  draw();
  b.addEventListener("click", async () => {
    try {
      const r = await api.post(`/videos/${item.id}/favorite`);
      item.favorite = r.favorite;
      draw();
      onToggle?.(item.favorite);
    } catch (e) { toast(e.message, "err"); }
  });
  return b;
}
