/** 实体页：女优 / 厂商 / 系列 / 类别 */
import { api } from "../api.js?v=4";
import { h, debounce } from "../util.js?v=4";
import { entityCard, skeletonGrid, emptyState } from "../components.js?v=4";

const CONF = {
  actresses: { title: "女优", icon: "👩", avatar: true, param: "actress_id" },
  studios: { title: "厂商", icon: "🏢", square: true, param: "studio_id" },
  series: { title: "系列", icon: "📚", square: true, param: "series_id" },
  genres: { title: "类别", icon: "🏷", square: true, param: "genre_id" },
};

export async function render(view, params) {
  const kind = params[1];
  const conf = CONF[kind] || CONF.actresses;
  document.title = `${conf.title} · MediaBoss`;
  view.innerHTML = "";
  view.append(h("div", { class: "page-head" }, h("h1", {}, `${conf.icon} ${conf.title}`)));

  const toolbar = h("div", { class: "toolbar" });
  const search = h("input", { class: "input", type: "text", placeholder: `搜索${conf.title}…` });
  search.style.width = "200px";
  const sortSel = h("select", { class: "input" },
    h("option", { value: "video_count" }, "按影片数"),
    h("option", { value: "name" }, "按名称"));
  const cnt = h("span", { class: "cnt" });
  toolbar.append(search, sortSel, cnt);
  const gridHolder = h("div", {});
  view.append(toolbar, gridHolder);

  async function load() {
    gridHolder.replaceChildren(skeletonGrid(12));
    try {
      const rows = await api.get(`/${kind}?q=${encodeURIComponent(search.value.trim())}&sort=${sortSel.value}`);
      cnt.textContent = `${rows.length} 个`;
      if (!rows.length) {
        gridHolder.replaceChildren(emptyState(conf.icon, `暂无${conf.title}数据`, "刮削成功后会自动归类"));
        return;
      }
      gridHolder.replaceChildren(h("div", { class: "grid" }, rows.map((e) => entityCard({
        ...e, href: `#/jav?${conf.param}=${e.id}`,
      }, { square: conf.square, avatarUrl: conf.avatar ? `/api/${kind}/${e.id}/avatar` : null }))));
    } catch (e) {
      gridHolder.replaceChildren(emptyState("⚠️", e.message));
    }
  }
  search.addEventListener("input", debounce(load, 350));
  sortSel.addEventListener("change", load);
  load();
}
