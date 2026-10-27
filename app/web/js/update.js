/** 更新任务对话框：全量/增量选择 + 实时进度（成功/失败/总数/耗时/预计剩余）+ 取消。 */
import { api } from "./api.js?v=22";
import { h, toast, modal } from "./util.js?v=22";

const fmtElapsed = (s) => {
  s = Math.max(0, Math.round(s || 0));
  const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
  return hh > 0 ? `${hh}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`
    : `${mm}:${String(ss).padStart(2, "0")}`;
};

/** 全局入口：topbar / 页面均可调用。 */
export function openUpdateDialog() {
  modal((box, close) => {
    let timer = null;
    let started = false;

    const modeSel = h("select", { class: "input" },
      h("option", { value: "incremental" }, "增量更新（推荐）—— 只处理新增与未完成/失败的项目，速度快"),
      h("option", { value: "full" }, "全量更新 —— 重置全部状态并重新刮削所有视频，耗时长"));

    const thumbChk = h("input", { type: "checkbox" });
    const thumbRow = h("label", { class: "checkline", style: "margin-top:10px" },
      thumbChk, "同时重建全部缩略图/雪碧图（ffmpeg 逐个处理，耗时较长）");

    const startBtn = h("button", { class: "btn primary" }, "开始更新");
    const cancelBtn = h("button", { class: "btn" }, "取消");

    /* 进度区（开始后显示） */
    const progWrap = h("div", { style: "display:none;margin-top:6px" },
      h("div", { class: "pbar upd-pbar" }, h("i")),
      h("div", { class: "upd-stats" }),
      h("div", { class: "upd-errors", style: "display:none" }));

    const stopPoll = () => { if (timer) { clearInterval(timer); timer = null; } };

    const render = (u) => {
      const job = u.update?.job || {};
      const running = !!job.running;
      const pct = job.total > 0 ? Math.min(100, job.done / job.total * 100)
        : (running ? 0 : (started && job.done > 0 ? 100 : 0));
      progWrap.querySelector(".pbar > i").style.width = `${pct.toFixed(1)}%`;

      const stats = progWrap.querySelector(".upd-stats");
      stats.replaceChildren(
        h("div", { class: "upd-line" },
          h("b", {}, running ? `正在更新 ${job.current || "…"} (${pct.toFixed(0)}%)`
            : job.mode ? `更新${job.mode === "full" ? "（全量）" : "（增量）"}${job.done >= job.total ? "已完成" : "已停止"}` : ""),
        ),
        h("div", { class: "upd-grid" },
          h("span", { class: "c-ok" }, `✔ 成功 ${job.success || 0}`),
          h("span", { class: "c-err" }, `✘ 失败 ${job.failed || 0}`),
          h("span", { class: "c-mut" }, `⊘ 跳过 ${job.skipped || 0}`),
          h("span", {}, `Σ 总计 ${job.total || 0} / 完成 ${job.done || 0}`),
          h("span", { class: "c-mut" }, `⏱ 已进行 ${fmtElapsed(job.elapsed)}`),
          running && job.eta > 0 ? h("span", { class: "c-mut" }, `≈ 剩余 ${fmtElapsed(job.eta)}`) : null,
        ),
      );

      const errs = progWrap.querySelector(".upd-errors");
      if (job.errors?.length) {
        errs.style.display = "";
        errs.replaceChildren(h("div", { class: "upd-err-t" }, "失败明细（番号 · 原因）"),
          ...job.errors.slice(-8).map((e) => h("div", { class: "upd-err-i" },
            `${e.code} — ${e.err || "未知原因"}`)));
      } else {
        errs.style.display = "none";
      }

      if (running) {
        startBtn.disabled = true;
        startBtn.textContent = "更新进行中…";
        cancelBtn.style.display = "";
      } else {
        if (started) {
          startBtn.disabled = false;
          startBtn.textContent = "再次更新";
          cancelBtn.style.display = "none";
          stopPoll(); // 完成后停止轮询
        }
      }
    };

    const poll = async () => {
      try { render(await api.get("/updates/progress")); } catch { /* 静默 */ }
    };

    startBtn.addEventListener("click", async () => {
      try {
        const r = await api.post("/updates/start",
          { mode: modeSel.value, rebuild_thumbs: thumbChk.checked });
        started = true;
        progWrap.style.display = "";
        modeSel.disabled = true;
        thumbChk.disabled = true;
        render(r);
        toast("更新任务已启动", "ok");
        stopPoll();
        timer = setInterval(poll, 1000);
      } catch (e) { toast(e.message, "err"); }
    });
    cancelBtn.addEventListener("click", async () => {
      try {
        await api.post("/updates/cancel");
        toast("已取消更新", "info");
        cancelBtn.style.display = "none";
        poll();
      } catch (e) { toast(e.message, "err"); }
    });

    // 打开时若已有任务在跑，直接显示进度并启动轮询
    api.get("/updates/progress").then((u) => {
      const job = u.update?.job || {};
      if (job.running) {
        started = true;
        progWrap.style.display = "";
        modeSel.disabled = true;
        thumbChk.disabled = true;
        render(u);
        stopPoll();
        timer = setInterval(poll, 1000);
      }
    }).catch(() => {});

    box.append(
      h("h3", {}, "🔄 更新媒体库"),
      h("p", { style: "color:var(--muted);margin:0 0 12px;font-size:13px" },
        "增量更新：扫描目录变更，仅刮削 新增 / 未完成 / 之前失败 的视频，已成功的不会重复请求网络。"),
      h("div", { class: "row" }, h("label", {}, "更新方式"), modeSel),
      thumbRow,
      progWrap,
      h("div", { class: "acts" },
        h("button", {
          class: "btn", onclick: () => { stopPoll(); close(); },
        }, "关闭"),
        cancelBtn, startBtn),
    );
    box._onclose = stopPoll; // 任何方式关闭对话框时停止轮询
  });
}
