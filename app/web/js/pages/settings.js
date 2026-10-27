/** 设置页：媒体目录 / 扫描 / 刮削 / 播放器 / 界面 / 数据管理 / CD2 下载 / 整理 / 安全 / 关于 */
import { api } from "../api.js?v=22";
import { h, toast, confirmModal, modal, fmtSize, applyTheme, applyAccent, applyWallpaper, applyLang } from "../util.js?v=22";

export async function render(view) {
  document.title = "设置 · MediaBoss";
  view.innerHTML = "";
  view.append(h("div", { class: "page-head" }, h("h1", {}, "⚙️ 设置")));
  const wrap = h("div", { class: "settings-wrap" });
  view.append(wrap);

  let settings, dirs, info;
  try {
    [settings, dirs, info] = await Promise.all([
      api.get("/settings"), api.get("/directories"), api.get("/system/info"),
    ]);
  } catch (e) {
    wrap.append(h("div", { class: "empty" }, h("div", { class: "big" }, "⚠️"), e.message));
    return;
  }

  const dirty = {};
  const group = (icon, title, ...body) => h("div", { class: "set-group" },
    h("div", { class: "h" }, `${icon} ${title}`), h("div", { class: "b" }, ...body));

  const setRow = (label, tip, ...ctls) => h("div", { class: "set-row" },
    h("div", { class: "lbl" }, label, tip ? h("span", { class: "tip" }, tip) : null),
    h("div", { class: "ctl" }, ...ctls));

  const txt = (key, ph = "") => {
    const i = h("input", { class: "input", type: "text", value: settings[key] ?? "", placeholder: ph });
    i.addEventListener("change", () => { dirty[key] = i.value; });
    return i;
  };
  const num = (key) => {
    const i = h("input", { class: "input", type: "number", value: settings[key] ?? "", style: "max-width:110px" });
    i.addEventListener("change", () => { dirty[key] = i.value; });
    return i;
  };
  const toggle = (key) => {
    const on = settings[key] === "1";
    const sw = h("label", { class: "switch" }, h("input", { type: "checkbox" }), h("i", {}));
    sw.firstChild.checked = on;
    sw.firstChild.addEventListener("change", () => { dirty[key] = sw.firstChild.checked ? "1" : "0"; });
    return sw;
  };

  /* ===== 媒体目录 ===== */
  const dirList = h("div", {});
  const renderDirs = () => {
    dirList.replaceChildren(...dirs.map((d) => h("div", { class: "dir-row" },
      h("span", { class: "path" }, d.path),
      h("span", { class: "n" }, `${d.video_count} 视频${d.jav_count ? ` / ${d.jav_count} JAV` : ""}`),
      (() => {
        const sel = h("select", { class: "input" },
          h("option", { value: "normal", selected: d.mode === "normal" }, "普通模式"),
          h("option", { value: "jav", selected: d.mode === "jav" }, "JAV 模式"));
        sel.addEventListener("change", async () => {
          try { await api.patch(`/directories/${d.id}`, { mode: sel.value }); toast("已更新", "ok", 1200); }
          catch (e) { toast(e.message, "err"); }
        });
        return sel;
      })(),
      (() => {
        const sw = h("label", { class: "switch" }, h("input", { type: "checkbox" }), h("i", {}));
        sw.firstChild.checked = !!d.enabled;
        sw.firstChild.addEventListener("change", async () => {
          try { await api.patch(`/directories/${d.id}`, { enabled: sw.firstChild.checked }); }
          catch (e) { toast(e.message, "err"); }
        });
        return sw;
      })(),
      h("button", {
        class: "btn sm danger", onclick: () => confirmModal("删除目录", `移除监控目录并清空其视频索引：${d.path}（不会删除磁盘文件）`,
          async () => { await api.del(`/directories/${d.id}`); dirs = await api.get("/directories"); renderDirs(); }, true),
      }, "移除"),
    )));
  };
  renderDirs();

  const newDirInput = h("input", { class: "input", type: "text", placeholder: "输入本机视频文件夹完整路径，如 D:\\Movies" });
  const addDirBtn = h("button", { class: "btn primary" }, "＋ 添加目录");
  const scanBtn = h("button", { class: "btn" }, "🔍 立即扫描");
  addDirBtn.addEventListener("click", async () => {
    const p = newDirInput.value.trim();
    if (!p) return;
    try {
      await api.post("/directories", { path: p });
      toast("目录已添加，开始扫描", "ok");
      newDirInput.value = "";
      dirs = await api.get("/directories");
      renderDirs();
    } catch (e) { toast(e.message, "err"); }
  });
  scanBtn.addEventListener("click", async () => {
    try { await api.post("/directories/scan"); toast("已触发扫描", "ok"); }
    catch (e) { toast(e.message, "err"); }
  });

  /* ===== 保存按钮 ===== */
  const saveBtn = h("button", { class: "btn primary", disabled: true }, "保存设置");
  const markDirty = () => {
    saveBtn.disabled = false;
    saveBtn.textContent = `保存设置（${Object.keys(dirty).length} 项已修改）`;
  };
  wrap.addEventListener("change", () => {
    if (Object.keys(dirty).length) markDirty();
  });
  saveBtn.addEventListener("click", async () => {
    if (!Object.keys(dirty).length) return;
    try {
      await api.put("/settings", dirty);
      toast("设置已保存", "ok");
      for (const k of Object.keys(dirty)) settings[k] = dirty[k];
      for (const k of Object.keys(dirty)) delete dirty[k];
      saveBtn.disabled = true;
      saveBtn.textContent = "保存设置";
    } catch (e) { toast(e.message, "err"); }
  });

  /* ===== 工具检测/安装 ===== */
  const toolInfo = h("span", { style: "font-size:12.5px" },
    info.ffmpeg?.available ? h("span", { class: "badge ok" }, `ffmpeg ${info.ffmpeg.version || "可用"}`)
      : h("span", { class: "badge err" }, "ffmpeg 不可用"),
    " ",
    info.mpv?.available ? h("span", { class: "badge ok" }, "mpv 可用") : h("span", { class: "badge mut" }, "mpv 未配置"));
  const detectBtn = h("button", { class: "btn sm" }, "重新检测");
  detectBtn.addEventListener("click", async () => {
    try {
      const r = await api.post("/system/detect");
      toast("检测完成，刷新查看", "ok");
      location.reload();
    } catch (e) { toast(e.message, "err"); }
  });
  const installBtn = h("button", { class: "btn sm" }, "自动下载 ffmpeg");
  installBtn.addEventListener("click", async () => {
    installBtn.disabled = true;
    installBtn.textContent = "下载中…（约 80MB，请稍候）";
    try { await api.post("/system/ffmpeg/install"); toast("ffmpeg 安装完成", "ok"); location.reload(); }
    catch (e) { toast(e.message, "err"); installBtn.disabled = false; installBtn.textContent = "自动下载 ffmpeg"; }
  });

  /* ===== 安全：改密 + API 令牌 ===== */
  const oldPwd = h("input", { class: "input", type: "password", placeholder: "原密码", style: "max-width:150px" });
  const newPwd = h("input", { class: "input", type: "password", placeholder: "新密码(≥4位)", style: "max-width:150px" });
  const pwdBtn = h("button", { class: "btn sm" }, "修改密码");
  pwdBtn.addEventListener("click", async () => {
    try {
      await api.post("/auth/password", { old: oldPwd.value, new: newPwd.value });
      toast("密码已修改", "ok");
      oldPwd.value = newPwd.value = "";
    } catch (e) { toast(e.message, "err"); }
  });

  const tokenList = h("div", {});
  const renderTokens = (tokens) => {
    tokenList.replaceChildren(...(tokens.length ? tokens.map((t) => h("div", { class: "dir-row" },
      h("span", { class: "path" }, t.name || "(未命名)"),
      h("span", { style: "font-family:Consolas,monospace;font-size:12px;color:var(--faint);word-break:break-all" }, t.token),
      h("button", { class: "btn sm danger", onclick: async () => { await api.del(`/auth/tokens/${t.id}`); loadTokens(); } }, "删除"),
    )) : [h("div", { style: "color:var(--faint);font-size:12.5px;padding:6px 0" }, "暂无 API 令牌")]));
  };
  const loadTokens = async () => renderTokens(await api.get("/auth/tokens"));
  loadTokens();
  const tokenName = h("input", { class: "input", type: "text", placeholder: "令牌名称", style: "max-width:140px" });
  const tokenBtn = h("button", { class: "btn sm primary" }, "生成令牌");
  tokenBtn.addEventListener("click", async () => {
    try {
      const r = await api.post("/auth/tokens", { name: tokenName.value.trim() });
      toast(`令牌已生成: ${r.token}`, "ok", 6000);
      loadTokens();
    } catch (e) { toast(e.message, "err"); }
  });

  /* ===== 界面：主题 ===== */
  const themeSel = h("select", { class: "input", style: "max-width:170px" },
    h("option", { value: "dark", selected: (settings.theme || "dark") === "dark" }, "🌙 暗色"),
    h("option", { value: "light", selected: settings.theme === "light" }, "☀️ 亮色"),
    h("option", { value: "oled", selected: settings.theme === "oled" }, "🖤 纯黑"),
    h("option", { value: "mocha", selected: settings.theme === "mocha" }, "☕ 暖棕"),
    h("option", { value: "forest", selected: settings.theme === "forest" }, "🌲 墨绿"),
    h("option", { value: "sepia", selected: settings.theme === "sepia" }, "📜 羊皮纸"),
    h("option", { value: "ocean", selected: settings.theme === "ocean" }, "🌊 深海"),
    h("option", { value: "neon", selected: settings.theme === "neon" }, "🌌 霓虹"),
    h("option", { value: "gold", selected: settings.theme === "gold" }, "🥂 黑金"),
    h("option", { value: "sakura", selected: settings.theme === "sakura" }, "🌸 樱花"),
    h("option", { value: "auto", selected: settings.theme === "auto" }, "🌗 跟随系统"));
  themeSel.addEventListener("change", () => {
    applyTheme(themeSel.value);
    applyAccent(settings.accent_color || "");  // 重算派生色（亮/暗色方向不同）
    dirty.theme = themeSel.value;
    markDirty();
  });

  /* ===== 界面：强调色 / 壁纸 / 语言（A10） ===== */
  const accentInput = h("input", { type: "color", value: settings.accent_color || "#e0556b",
    style: "width:46px;height:32px;padding:2px;border:1px solid var(--border2);border-radius:8px;background:var(--surface);cursor:pointer" });
  accentInput.addEventListener("input", () => {
    applyAccent(accentInput.value);
    dirty.accent_color = accentInput.value;
    markDirty();
  });
  const accentReset = h("button", { class: "btn sm" }, "重置");
  accentReset.addEventListener("click", () => {
    applyAccent("");
    accentInput.value = "#e0556b";
    dirty.accent_color = "";
    markDirty();
    toast("已恢复默认强调色", "ok", 1500);
  });
  const wpInput = h("input", { class: "input", type: "text", value: settings.wallpaper || "",
    placeholder: "图片 URL，留空不使用壁纸" });
  wpInput.addEventListener("change", () => {
    applyWallpaper(wpInput.value.trim());
    dirty.wallpaper = wpInput.value.trim();
    markDirty();
  });
  const wpClear = h("button", { class: "btn sm" }, "清除");
  wpClear.addEventListener("click", () => {
    applyWallpaper("");
    wpInput.value = "";
    dirty.wallpaper = "";
    markDirty();
  });
  const langSel = h("select", { class: "input", style: "max-width:170px" },
    h("option", { value: "zh", selected: (settings.lang || "zh") === "zh" }, "🇨🇳 中文"),
    h("option", { value: "en", selected: settings.lang === "en" }, "🇺🇸 English"));
  langSel.addEventListener("change", () => {
    applyLang(langSel.value);
    dirty.lang = langSel.value;
    markDirty();
  });

  /* ===== 数据管理 ===== */
  const restoreInput = h("input", { type: "file", accept: ".zip", style: "display:none" });
  restoreInput.addEventListener("change", () => {
    const f = restoreInput.files[0];
    restoreInput.value = "";
    if (!f) return;
    confirmModal("恢复备份", `将用「${f.name}」覆盖当前全部数据（视频索引 / JAV 元数据 / 历史 / 设置 / 封面），操作不可撤销。`,
      async () => {
        toast("恢复中，请勿关闭页面…", "info", 10000);
        try {
          const res = await fetch("/api/system/restore?confirm=RESTORE", {
            method: "POST",
            headers: { "Content-Type": "application/octet-stream" },
            body: await f.arrayBuffer(),
          });
          const d = await res.json().catch(() => ({}));
          if (!res.ok || d.ok === false) throw new Error(d.error || `恢复失败 (${res.status})`);
          toast(d.data?.msg || "恢复完成，即将刷新…", "ok", 5000);
          setTimeout(() => location.reload(), 2000);
        } catch (e) { toast(e.message, "err"); }
      }, true);
  });

  const dictWrap = h("div", {});
  const renderDict = async () => {
    let dd;
    try { dd = await api.get("/data/dict"); } catch (e) { toast(e.message, "err"); return; }
    const typeBadge = (t) => h("span", { class: `badge ${t === "长期" ? "info" : t === "缓存" ? "ok" : "warn"}` }, t);
    const table = h("table", { class: "table" },
      h("thead", {}, h("tr", {},
        h("th", {}, "名称"), h("th", {}, "类型"), h("th", {}, "大小 / 数量"),
        h("th", {}, "作用"), h("th", {}, "操作"))),
      h("tbody", {}, ...dd.entries.map((e) => h("tr", {},
        h("td", {}, h("b", {}, e.name),
          h("div", { style: "font-size:11px;color:var(--faint);font-family:Consolas,monospace" },
            e.path.replace(/^.*MediaBoss/i, "…"))),
        h("td", {}, typeBadge(e.type)),
        h("td", { style: "white-space:nowrap" }, e.size_h, h("div", { style: "font-size:11px;color:var(--faint)" },
          e.key === "db" ? `${dd.counts.videos} 视频 / ${dd.counts.jav} JAV` : `${e.count} 个文件`)),
        h("td", { style: "font-size:12px;color:var(--muted);max-width:280px" }, e.role,
          e.rebuild ? h("div", { style: "font-size:11px;color:var(--faint)" }, `重建方式：${e.rebuild}`) : null),
        h("td", {}, e.clearable ? h("button", {
          class: "btn sm danger",
          onclick: () => confirmModal(`清除「${e.name}」`, e.clear_note, async () => {
            try {
              const r = await api.post("/data/clear", { targets: [e.key] });
              toast(Object.values(r.results)[0].msg, "ok");
              renderDict();
            } catch (err) { toast(err.message, "err"); }
          }, true),
        }, "清除")
        : h("span", { style: "color:var(--faint);font-size:12px" }, "—")),
      ))),
    );
    const cnt = dd.counts;
    const summary = h("div", { style: "display:flex;gap:14px;flex-wrap:wrap;font-size:12.5px;color:var(--muted);margin-bottom:10px" },
      h("span", {}, `📊 库存：${cnt.videos} 视频 · ${cnt.scraped}/${cnt.jav} 已刮削`),
      h("span", {}, `⏳ 待刮削 ${cnt.pending} · 失败 ${cnt.failed} · 无番号 ${cnt.no_code}`),
      h("span", {}, `🗄 数据库 ${dd.db_size_h}`));
    const btns = h("div", { style: "display:flex;gap:9px;flex-wrap:wrap;margin-top:12px" },
      h("button", {
        class: "btn sm", onclick: async () => {
          try {
            const r = await api.post("/data/optimize");
            toast(`数据库已压缩: ${r.before_h} → ${r.after_h}`, "ok", 4000);
            renderDict();
          } catch (e) { toast(e.message, "err"); }
        },
      }, "🗜 压缩数据库 (VACUUM)"),
      h("button", {
        class: "btn sm", onclick: () => confirmModal("重置刮削状态",
          "将所有视频的刮削状态重置为待处理（不动任何文件与已刮削数据），之后可在顶栏「更新」中选择全量/增量。",
          async () => {
            try {
              const r = await api.post("/data/reset-scrape");
              toast(`已重置 ${r.reset} 个视频的刮削状态`, "ok");
              renderDict();
            } catch (e) { toast(e.message, "err"); }
          }),
      }, "↺ 重置刮削状态"),
      h("button", {
        class: "btn sm danger", onclick: () => factoryResetModal(renderDict),
      }, "⚠️ 工厂重置"),
    );
    dictWrap.replaceChildren(summary, table, btns);
  };
  renderDict();

  /* ===== A8 检查更新 ===== */
  const checkUpdBtn = h("button", { class: "btn sm" }, "🔍 检查更新");
  checkUpdBtn.addEventListener("click", async () => {
    checkUpdBtn.disabled = true;
    checkUpdBtn.textContent = "检查中…";
    try {
      const r = await api.get("/system/check-update");
      if (r.available && r.has_update) {
        modal((box, close) => {
          box.append(
            h("h3", { style: "margin-top:0" }, "🎉 发现新版本"),
            h("p", { style: "margin:4px 0" },
              h("b", {}, `v${r.current}`), " → ",
              h("b", { style: "color:var(--accent-h)" }, `v${r.latest}`),
              r.published_at ? h("span", { class: "mut" }, ` · ${r.published_at}`) : null),
            r.name ? h("p", { style: "font-weight:600;margin:2px 0 8px" }, r.name) : null,
            r.notes ? h("pre", { style: "max-height:300px;overflow:auto;white-space:pre-wrap;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:10px 12px;font-size:12.5px;margin:0 0 12px" }, r.notes) : null,
            h("div", { class: "acts" },
              r.url ? h("a", { class: "btn primary", href: r.url, target: "_blank", rel: "noopener" }, "前往下载") : null,
              h("button", { class: "btn", onclick: close }, "关闭")));
        });
      } else if (r.available) {
        toast(`已是最新版本 v${r.current}`, "ok", 4000);
      } else {
        toast(r.reason || "暂无法在线检查更新", "info", 4500);
      }
    } catch (e) { toast(e.message, "err"); }
    checkUpdBtn.disabled = false;
    checkUpdBtn.textContent = "🔍 检查更新";
  });

  /* ===== 组装 ===== */
  wrap.append(
    saveBtn,
    group("📂", "媒体目录",
      dirList,
      h("div", { style: "display:flex;gap:9px;margin-top:10px;flex-wrap:wrap" }, newDirInput, addDirBtn, scanBtn)),
    group("🔍", "扫描",
      setRow("自动扫描", "按间隔周期扫描目录变更", toggle("auto_scan")),
      setRow("扫描间隔", "分钟", num("scan_interval_min")),
      setRow("JAV 模式", "全局默认按番号识别文件", toggle("jav_mode"))),
    group("💋", "刮削",
      setRow("启用刮削", "", toggle("scrape_enabled")),
      setRow("数据源顺序", "逗号分隔，可用：javbus,javdb,javlib,dmm,fc2,missav", txt("scrape_provider_order")),
      setRow("源域名列表", "一个框管所有源。格式：javbus=镜像域名,dmm=镜像域名；源名：javbus/javdb/javlib/dmm/fc2/missav，留空用默认", txt("scrape_domains")),
      setRow("标题翻译", "使用 Google 翻译接口", toggle("translate_enabled")),
      setRow("网络代理", "如 http://127.0.0.1:7890，留空不使用", txt("proxy", "http://127.0.0.1:7890"))),
    group("🎬", "播放器与缩略图",
      setRow("mpv 路径", "外部播放器可执行文件路径（mpv 按钮仅服务器本机网页显示）", txt("mpv_path")),
      setRow("ffmpeg 路径", "留空自动探测；也可点下方自动下载", txt("ffmpeg_path")),
      setRow("缩略图并发", "同时生成缩略图的线程数", num("thumb_workers")),
      setRow("进度条雪碧图", "播放页悬停预览", toggle("sprite_enabled")),
      setRow("工具状态", "", toolInfo, detectBtn, info.ffmpeg?.available ? null : installBtn)),
    group("🖥", "界面",
      setRow("主题", "暗色 / 亮色 / 纯黑 / 暖棕 / 墨绿 / 羊皮纸 / 深海 / 霓虹 / 黑金 / 樱花 / 跟随系统，立即生效", themeSel),
      setRow("强调色", "自定义按钮 / 高亮颜色，立即生效", accentInput, accentReset),
      setRow("壁纸", "背景图片 URL，界面面板自动半透明", wpInput, wpClear),
      setRow("语言 Language", "界面语言（基础翻译）", langSel),
      setRow("每页数量", "", num("page_size")),
      setRow("缩略图", "", toggle("sprite_enabled"))),
    group("🗄", "数据管理",
      h("p", { style: "color:var(--faint);font-size:12.5px;margin:0 0 12px" },
        "数据分三类：长期（数据库/截图/工具，删除不可恢复）、缓存（封面/缩略图/雪碧图，可自动重建）、临时（日志/缓存，随时可清）。"),
      dictWrap,
      h("div", { style: "display:flex;gap:9px;flex-wrap:wrap;margin-top:14px" },
        h("a", { class: "btn sm", href: "/api/system/backup", download: "" }, "📦 下载数据备份"),
        h("button", {
          class: "btn sm", onclick: () => restoreInput.click(),
        }, "♻️ 恢复备份"),
        restoreInput,
        h("span", { style: "align-self:center;font-size:12px;color:var(--faint)" },
          "备份包含完整数据库 + 封面 / 自定义海报，恢复将覆盖现有数据"))),
    group("🗂", "文件整理",
      setRow("命名模板", "可用 {code} {title} {ext}", txt("organize_template")),
      setRow("说明", "", h("span", { style: "color:var(--faint);font-size:12.5px" },
        "在 视频库 页点击「整理」可预览并应用重命名"))),
    group("🔒", "安全",
      setRow("修改密码", "", oldPwd, newPwd, pwdBtn),
      setRow("局域网访问", "允许其他设备通过 IP 访问", toggle("lan_access")),
      setRow("API 令牌", "用于外部程序调用 API（Bearer 认证）", tokenName, tokenBtn),
      tokenList),
    group("ℹ️", "关于",
      setRow("版本", "", h("span", { class: "badge info" }, `v${info.version}`), checkUpdBtn),
      setRow("运行环境", "", h("span", { style: "color:var(--muted);font-size:12.5px" },
        `Python ${info.python} · ${info.platform}`)),
      setRow("数据库大小", "", h("span", {}, fmtSize(info.db_size))),
      setRow("局域网地址", "", h("span", { style: "font-family:Consolas,monospace;font-size:13px" },
        `http://${info.host}:${info.port}`))),
  );
  wrap.insertBefore(saveBtn, wrap.firstChild);
}

/** 工厂重置：输入 RESET 确认。 */
function factoryResetModal(onDone) {
  modal((box, close) => {
    const input = h("input", { class: "input", placeholder: "输入 RESET 确认", style: "margin-top:6px" });
    box.append(
      h("h3", {}, "⚠️ 工厂重置"),
      h("p", { style: "color:var(--muted);font-size:13px" },
        "将清空 全部数据（视频索引、JAV 元数据、历史、设置）与缓存文件，密码重置为 admin。",
        h("br"), "保留：ffmpeg 工具、config.toml。磁盘上的视频文件不受影响。",
        h("br"), h("b", { style: "color:var(--err)" }, "此操作不可恢复，常用于迁移服务器前重置或彻底重新开始。")),
      input,
      h("div", { class: "acts" },
        h("button", { class: "btn", onclick: close }, "取消"),
        h("button", {
          class: "btn danger",
          onclick: async () => {
            if (input.value.trim().toUpperCase() !== "RESET") { toast("请输入 RESET 确认", "err"); return; }
            try {
              await api.post("/data/factory-reset", { confirm: "RESET" });
              close();
              toast("已恢复初始状态，请重新登录（admin/admin）", "ok", 5000);
              setTimeout(() => location.reload(), 1500);
            } catch (e) { toast(e.message, "err"); }
          },
        }, "确认重置"),
      ),
    );
  });
}
