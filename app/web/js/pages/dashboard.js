/** 仪表盘：统计 + 最近添加 + 热门女优/厂商 */
import { api } from "../api.js?v=4";
import { h } from "../util.js?v=4";
import { videoCard, entityCard, emptyState } from "../components.js?v=4";

export async function render(view) {
  view.innerHTML = "";
  view.append(h("div", { class: "page-head" }, h("h1", {}, "仪表盘"),
    h("span", { class: "sub" }, "媒体库总览")));
  const holder = h("div", {}, "加载中…");
  view.append(holder);
  document.title = "仪表盘 · MediaBoss";

  let s;
  try { s = await api.get("/stats"); } catch (e) {
    holder.replaceChildren(h("div", { class: "empty" }, h("div", { class: "big" }, "⚠️"), e.message));
    return;
  }

  const stat = (v, l) => h("div", { class: "stat-card" },
    h("div", { class: "v", html: v }), h("div", { class: "l" }, l));

  const parts = [
    h("div", { class: "stats-row" },
      stat(`${s.total_videos}`, "视频总数"),
      stat(`${s.total_size_h || "-"}`, "磁盘占用"),
      stat(`${s.total_duration_h || "-"}`, "总时长"),
      stat(`${s.total_jav} <span class="unit">/ ${s.scraped} 已刮削</span>`, "JAV 影片"),
      stat(`${s.watched} <span class="unit">/ 播放 ${s.play_count} 次</span>`, "已看完"),
      stat(`${s.week_plays}`, "本周观看次数"),
    ),
  ];
  // 热门女优
  if (s.top_actresses?.length) {
    parts.push(
      h("div", { class: "section-h" }, h("h2", {}, "热门女优"),
        h("a", { href: "#/actresses" }, "全部 ›")),
      h("div", { class: "hstrip" },
        s.top_actresses.map((a) => entityCard(
          { ...a, href: `#/jav?actress_id=${a.id}` }, { avatarUrl: a.avatar_url || null }))),
    );
  }
  // 热门厂商
  if (s.top_studios?.length) {
    parts.push(
      h("div", { class: "section-h" }, h("h2", {}, "热门厂商"),
        h("a", { href: "#/studios" }, "全部 ›")),
      h("div", { class: "hstrip" },
        s.top_studios.map((st) => entityCard({ ...st, href: `#/jav?studio_id=${st.id}` }, { square: true }))),
    );
  }
  // 最近添加
  parts.push(
    h("div", { class: "section-h" }, h("h2", {}, "最近添加"),
      h("a", { href: "#/videos" }, "全部视频 ›")),
    s.recent?.length
      ? h("div", { class: "grid" }, s.recent.map((r) => videoCard({
          id: r.id, code: r.code || "", title: r.title || `视频 #${r.id}`,
          cover_path: r.cover_path,
          thumb_url: r.cover_path ? "" : `/api/videos/${r.id}/thumbnail`,
        })))
      : emptyState("📥", "还没有视频", "前往 设置 → 媒体目录 添加视频文件夹开始扫描"),
  );
  holder.replaceChildren(...parts);
}
