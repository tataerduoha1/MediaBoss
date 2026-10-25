/** 下载管理：磁力提交 + 任务列表（CloudDrive2） */
import { api } from "../api.js?v=17";
import { h, toast, fmtSize, fmtTime, confirmModal } from "../util.js?v=17";
import { emptyState } from "../components.js?v=17";

const STATUS = {
  pending: ["mut", "等待"], running: ["info", "下载中"], paused: ["warn", "暂停"],
  done: ["ok", "完成"], error: ["err", "失败"],
};

export async function render(view) {
  document.title = "下载 · MediaBoss";
  view.innerHTML = "";
  view.append(h("div", { class: "page-head" }, h("h1", {}, "⬇️ 下载"),
    h("span", { class: "sub" }, "通过 CloudDrive2 提交磁力/URL 任务")));

  const urlInput = h("input", { class: "input", type: "text", placeholder: "粘贴磁力链接 magnet:?xt=… 或 http 直链" });
  const dirInput = h("input", { class: "input", type: "text", placeholder: "保存目录（留空用默认）", style: "max-width:240px" });
  const submitBtn = h("button", { class: "btn primary" }, "提交任务");
  const refreshBtn = h("button", { class: "btn" }, "🔄 同步状态");
  const clearBtn = h("button", { class: "btn danger" }, "清空已完成");

  const form = h("div", { class: "toolbar", style: "flex-direction:column;align-items:stretch" },
    h("div", { style: "display:flex;gap:9px;flex-wrap:wrap" }, urlInput, submitBtn),
    h("div", { style: "display:flex;gap:9px;flex-wrap:wrap;align-items:center" }, dirInput,
      h("span", { class: "spacer", style: "flex:1" }), refreshBtn, clearBtn));

  const list = h("div", {});
  view.append(form, list);

  submitBtn.addEventListener("click", async () => {
    const url = urlInput.value.trim();
    if (!url) { toast("请输入磁力链接或 URL", "err"); return; }
    submitBtn.disabled = true;
    try {
      await api.post("/downloads/magnet", { url, save_dir: dirInput.value.trim() });
      toast("任务已提交", "ok");
      urlInput.value = "";
      load();
    } catch (e) { toast(e.message, "err"); } finally { submitBtn.disabled = false; }
  });
  urlInput.addEventListener("keydown", (e) => { if (e.key === "Enter") submitBtn.click(); });
  refreshBtn.addEventListener("click", async () => {
    try { const r = await api.post("/downloads/refresh"); toast(`已同步 ${r.synced} 个任务`, "ok", 1500); load(); }
    catch (e) { toast(e.message, "err"); }
  });
  clearBtn.addEventListener("click", () => confirmModal("清空已完成", "删除所有已完成的下载记录？（不影响已下载文件）",
    async () => { await api.post("/downloads/0/clear"); load(); }));

  function row(t) {
    const [cls, label] = STATUS[t.status] || ["mut", t.status || "未知"];
    const pct = t.total_size > 0 ? Math.min(100, t.completed_size / t.total_size * 100) : 0;
    return h("div", { style: "background:var(--card);border:1px solid var(--border);border-radius:10px;padding:13px 16px;margin-bottom:10px" },
      h("div", { style: "display:flex;gap:10px;align-items:center;flex-wrap:wrap" },
        h("span", { class: `badge ${cls}` }, label),
        h("span", { style: "flex:1;min-width:200px;word-break:break-all;font-size:13px" },
          t.name || t.url || `任务 #${t.id}`),
        h("span", { style: "color:var(--faint);font-size:12px" }, fmtTime(t.created_at)),
        h("button", {
          class: "btn sm danger", onclick: async () => {
            await api.del(`/downloads/${t.id}`); load();
          },
        }, "删除")),
      t.total_size ? h("div", { style: "display:flex;gap:10px;align-items:center;margin-top:9px" },
        h("div", { class: "pbar", style: "flex:1" }, h("i", { style: `width:${pct}%` })),
        h("span", { style: "font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums" },
          `${pct.toFixed(1)}% · ${fmtSize(t.completed_size || 0)}/${fmtSize(t.total_size)}`)) : null,
      t.error ? h("div", { style: "color:var(--err);font-size:12px;margin-top:6px" }, t.error) : null,
    );
  }

  async function load() {
    list.replaceChildren(h("div", { style: "color:var(--faint);padding:20px;text-align:center" }, "加载中…"));
    try {
      const rows = await api.get("/downloads");
      if (!rows.length) {
        list.replaceChildren(emptyState("⬇️", "暂无下载任务",
          "需要先在 设置 → CD2 下载 中配置 CloudDrive2 地址"));
        return;
      }
      list.replaceChildren(...rows.map(row));
    } catch (e) {
      list.replaceChildren(emptyState("⚠️", e.message));
    }
  }
  load();
}
