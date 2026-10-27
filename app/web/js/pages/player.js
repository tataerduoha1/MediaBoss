/** 播放器：自定义控制栏、雪碧图悬停预览、进度记忆、智能转码（不兼容编码网页直播）、截图、触屏与快捷键。 */
import { api } from "../api.js?v=22";
import { h, toast, fmtDur, modal, isLocal } from "../util.js?v=22";

export async function render(root, params) {
  const vid = params[1];
  document.title = "播放 · MediaBoss";

  let v, j, info;
  try {
    const [d, pi] = await Promise.all([
      api.get(`/videos/${vid}`),
      api.get(`/videos/${vid}/playinfo`).catch(() => null),
    ]);
    v = d.video; j = d.jav; info = pi;
  } catch (e) {
    root.innerHTML = "";
    root.append(h("div", { class: "login-wrap" },
      h("div", { class: "empty" }, h("div", { class: "big" }, "⚠️"), h("p", {}, e.message),
        h("p", {}, h("a", { href: "#/videos", style: "color:var(--accent-h)" }, "← 返回视频库")))));
    return;
  }

  root.innerHTML = "";
  root.className = "";
  const page = h("div", { class: "player-page" });
  root.append(page);

  /* ---- 播放方式：direct 原文件直出 / transcode 服务端转码 fMP4（网页直播不兼容编码）---- */
  const transcoded = () => info?.mode === "transcode";
  let startOffset = 0; // 转码流的起始秒（currentTime 需加回该偏移才是真实进度）
  const resumeAt = (v.resume_position && v.resume_position < (v.duration || 1e9) * 0.9)
    ? v.resume_position : 0;
  const srcUrl = (t) => transcoded()
    ? `/api/videos/${vid}/transcode?start=${Math.max(0, t).toFixed(2)}`
    : `/api/videos/${vid}/stream`;
  // 转码流是"边转边播"的直播式 fMP4：video.duration 会随转码进度增长（或为 Infinity），
  // 进度条总长必须用元数据时长（库内/探测值），播放位置 = start 偏移 + 流内位置
  const dur = () => {
    if (transcoded()) {
      return v.duration || info?.duration || (isFinite(video.duration) ? video.duration : 0) || 0;
    }
    return (isFinite(video.duration) && video.duration > 0) ? video.duration : (v.duration || 0);
  };
  const curPos = () => startOffset + (video.currentTime || 0);

  const video = h("video", { src: srcUrl(resumeAt), autoplay: "", playsinline: "" });
  const title = j?.code ? `${j.code} ${j.cn_title || j.title || ""}` : (v.title || v.filename);

  /* ---- 控制栏 ---- */
  const seekKnob = h("div", { class: "knob" });
  const playedBar = h("div", { class: "played" });
  const bufBar = h("div", { class: "buf" });
  const spritePop = h("div", { class: "sprite-pop" },
    h("canvas", { width: 160, height: 90 }),
    h("div", { class: "t" }, "0:00"));
  const seekbar = h("div", { class: "seekbar" },
    h("div", { class: "track" }, bufBar, playedBar, seekKnob), spritePop);

  const timeLabel = h("span", { class: "time" }, "0:00 / 0:00");
  const tcBadge = transcoded()
    ? h("span", { class: "p-badge", title: info?.v_transcode
        ? "该视频编码网页无法直播，服务端正在实时转码（CPU 占用较高）"
        : "该音频编码网页无法直播，服务端正在实时转码" }, "⚡ 转码")
    : null;
  const playBtn = h("button", { class: "pb", title: "播放/暂停 (空格)" }, "⏸");
  const back10 = h("button", { class: "pb", title: "后退 10s (← / J)" }, "⏪");
  const fwd10 = h("button", { class: "pb", title: "前进 10s (→ / L)" }, "⏩");
  const muteBtn = h("button", { class: "pb m-mute", title: "静音 (M)" }, "🔊");
  const volSlider = h("input", { class: "vol", type: "range", min: 0, max: 1, step: 0.05, value: 1 });
  const rateSel = h("select", { class: "pb rate", title: "倍速", style: "background:none;border:none;color:#fff;outline:none" },
    ["0.5", "0.75", "1", "1.25", "1.5", "2", "3"].map((r) =>
      h("option", { value: r, selected: r === "1" }, `${r}x`)));
  const fsBtn = h("button", { class: "pb", title: "全屏 (F)" }, "⛶");
  const pipBtn = h("button", { class: "pb m-pip", title: "画中画 (P)" }, "PiP");
  const helpBtn = h("button", { class: "pb m-help", title: "快捷键帮助 (?)" }, "⌨");
  let ccBtn = null; // 字幕按钮（A3，检测到字幕文件时注入）

  const btnBar = h("div", { class: "p-btns" },
    playBtn, back10, fwd10, timeLabel, tcBadge,
    h("span", { class: "spacer" }),
    muteBtn, volSlider, rateSel, pipBtn, fsBtn, helpBtn);

  const controls = h("div", { class: "p-controls" }, seekbar, btnBar);

  /* ---- 顶栏按钮 ---- */
  const shotBtn = h("button", { class: "btn sm", title: "截图当前画面" }, "📷 截图");
  // mpv 是唤起服务器本机的外部播放器，仅服务器本机浏览时显示（手机端点会在电脑上弹窗口）
  const mpvBtn = h("button", { class: "btn sm", title: "使用 mpv 外部播放" }, "🖥 mpv");
  const favB = h("button", { class: "btn sm" });
  const drawFav = () => { favB.textContent = v.favorite ? "♥" : "♡"; };
  drawFav();
  favB.addEventListener("click", async () => {
    try {
      const r = await api.post(`/videos/${vid}/favorite`);
      v.favorite = r.favorite; drawFav();
    } catch (e) { toast(e.message, "err"); }
  });
  const closeBtn = h("button", { class: "back", title: "退出播放 (Esc / Backspace)" }, "← 退出");
  const topbar = h("div", { class: "p-topbar" },
    closeBtn, h("div", { class: "tt" }, title),
    h("div", { class: "acts" }, shotBtn, isLocal() ? mpvBtn : null, favB));

  page.append(video, topbar, controls,
    h("div", { class: "loadtip", id: "loadtip" },
      transcoded() ? "⚡ 转码启动中，请稍候…" : "加载中…"));

  /* ---- 进度上报 ---- */
  let startedSent = false;
  let lastReport = 0;
  function report(force = false) {
    if (!dur()) return;
    const now = Date.now();
    if (!force && now - lastReport < 9000) return;
    lastReport = now;
    const pos = curPos();
    fetch(`/api/videos/${vid}/progress`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ position: pos, duration: dur(), started: startedSent ? false : true }),
      keepalive: true,
    }).then(() => { startedSent = true; }).catch(() => {});
  }
  const reportTimer = setInterval(() => report(), 10000);
  const reportNow = () => report(true);
  video.addEventListener("pause", reportNow);
  window.addEventListener("pagehide", reportNow, { once: true });

  /* ---- 雪碧图预览 ---- */
  let spriteImg = null;
  const spriteCanvas = spritePop.querySelector("canvas");
  const spriteTime = spritePop.querySelector(".t");
  fetch(`/api/videos/${vid}/sprite`).then((r) => r.ok ? r.blob() : null).then((blob) => {
    if (!blob) return;
    spriteImg = new Image();
    spriteImg.onload = () => {
      spriteCanvas.width = Math.round(spriteImg.width / 10);
      spriteCanvas.height = Math.round(spriteImg.height / 10);
      spritePop.classList.add("have");
    };
    spriteImg.src = URL.createObjectURL(blob);
  }).catch(() => {});

  function drawSprite(t) {
    if (!spriteImg || !spriteImg.width || !dur()) return;
    const idx = Math.min(99, Math.max(0, Math.floor(t / dur() * 100)));
    const col = idx % 10, row = Math.floor(idx / 10);
    const tw = spriteImg.width / 10, th = spriteImg.height / 10;
    const ctx = spriteCanvas.getContext("2d");
    ctx.drawImage(spriteImg, col * tw, row * th, tw, th, 0, 0, spriteCanvas.width, spriteCanvas.height);
    spriteTime.textContent = fmtDur(t);
  }

  /* ---- A3 字幕：同目录 srt/ass/ssa/vtt 自动转 vtt ---- */
  fetch(`/api/videos/${vid}/subtitle`).then((r) => r.ok ? r.blob() : null).then((blob) => {
    if (!blob) return;
    const track = document.createElement("track");
    track.kind = "subtitles";
    track.label = "字幕";
    track.default = true;
    track.src = URL.createObjectURL(blob);
    video.append(track);
    ccBtn = h("button", { class: "pb on", title: "字幕开关 (C)" }, "CC");
    const toggleCc = () => {
      const tt = video.textTracks[0];
      if (!tt) return;
      const show = tt.mode !== "showing";
      tt.mode = show ? "showing" : "hidden";
      ccBtn.classList.toggle("on", show);
    };
    ccBtn.addEventListener("click", toggleCc);
    btnBar.insertBefore(ccBtn, pipBtn);
    setTimeout(() => { try { video.textTracks[0].mode = "showing"; } catch { /* ignore */ } }, 0);
  }).catch(() => { /* 无字幕文件，静默 */ });

  /* ---- 进度条交互：拖动只预览，松手才跳转（转码流下松手会重启转码）---- */
  let seeking = false;      // 鼠标/触摸拖动中
  let pendingT = 0;         // 拖动目标时间
  const posFromX = (clientX) => {
    const rect = seekbar.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    return ratio * (dur() || 0);
  };
  const previewSeek = (clientX) => {
    if (!dur()) return;
    pendingT = posFromX(clientX);
    const rect = seekbar.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    playedBar.style.width = `${ratio * 100}%`;
    seekKnob.style.left = `${ratio * 100}%`;
    timeLabel.textContent = `${fmtDur(pendingT)} / ${fmtDur(dur())}`;
    const x = Math.min(rect.width - 80, Math.max(80, clientX - rect.left));
    spritePop.style.left = `${x}px`;
    drawSprite(pendingT);
  };
  const commitSeek = () => {
    if (!seeking) return;
    seeking = false;
    if (dur() && pendingT >= 0) doSeek(pendingT);
    updTime();
  };
  seekbar.addEventListener("mousemove", (e) => {
    if (!dur()) return;
    if (seeking) previewSeek(e.clientX);
    else {
      const rect = seekbar.getBoundingClientRect();
      const t = posFromX(e.clientX);
      const x = Math.min(rect.width - 80, Math.max(80, e.clientX - rect.left));
      spritePop.style.left = `${x}px`;
      drawSprite(t);
    }
  });
  seekbar.addEventListener("mousedown", (e) => {
    if (!dur()) return;
    seeking = true;
    previewSeek(e.clientX);
  });
  window.addEventListener("mouseup", commitSeek);
  // 触屏：触摸拖动预览，抬手跳转
  seekbar.addEventListener("touchstart", (e) => {
    if (!dur()) return;
    seeking = true;
    previewSeek(e.touches[0].clientX);
  }, { passive: true });
  seekbar.addEventListener("touchmove", (e) => {
    if (seeking) previewSeek(e.touches[0].clientX);
  }, { passive: true });
  seekbar.addEventListener("touchend", commitSeek);
  seekbar.addEventListener("click", (e) => {
    if (dur()) doSeek(posFromX(e.clientX));
  });

  /* ---- 视频事件 ---- */
  let resumeShown = false;
  video.addEventListener("loadedmetadata", () => {
    page.querySelector("#loadtip")?.remove();
    // 转码流的断点续播通过 ?start= 已生效，这里只提示；直连流直接跳转
    if (resumeAt && !resumeShown) {
      resumeShown = true;
      if (!transcoded()) video.currentTime = resumeAt;
      toast(`已恢复到 ${fmtDur(resumeAt)}（从头看请拖回开头）`, "info", 2400);
    }
    video.volume = parseFloat(localStorage.getItem("mb_vol") || "1");
    volSlider.value = video.volume;
    const rate = parseFloat(localStorage.getItem("mb_rate") || "1");
    if (rate !== 1) { video.playbackRate = rate; rateSel.value = String(rate); }
    updTime();
    video.play?.().catch(() => { /* 自动播放被拦截时由用户手动开始 */ });
  });
  video.addEventListener("timeupdate", () => {
    if (!seeking) updTime();
    report();
  });
  video.addEventListener("progress", () => {
    try {
      if (video.buffered.length && dur()) {
        const end = video.buffered.end(video.buffered.length - 1);
        bufBar.style.width = `${Math.min(100, end / dur() * 100)}%`;
      }
    } catch { /* ignore */ }
  });
  video.addEventListener("play", () => { playBtn.textContent = "⏸"; });
  video.addEventListener("pause", () => { playBtn.textContent = "▶"; });
  video.addEventListener("ended", () => {
    // 转码流"假结束"保护：位置远未到片尾却触发 ended，说明转码流异常中断
    // （如封装拷贝失败输出零点几秒），按失败引导重试，且不标记已看完
    const meta = v.duration || 0;
    if (transcoded() && meta > 60 && curPos() < meta * 0.9) {
      page.querySelector("#loadtip")?.remove();
      page.append(h("div", { class: "loadtip", id: "loadtip" },
        h("div", { style: "text-align:center" }, `转码流异常中断 — 点击「↻ 重试转码」重试${isLocal() ? "，或用 mpv 外放" : ""}`,
          h("div", { style: "margin-top:12px;display:flex;gap:10px;justify-content:center;flex-wrap:wrap" },
            h("button", { class: "btn primary sm", onclick: () => doSeek(curPos()) }, "↻ 重试转码"),
            isLocal() ? h("button", { class: "btn primary sm", onclick: () => mpvBtn.click() }, "🖥 用 mpv 播放") : null,
            h("a", { class: "btn sm", href: "#/videos" }, "← 返回视频库")))));
      return;
    }
    toast("播放结束", "ok");
    report(true);
  });
  // 直连播放失败的兜底：强制切换为转码模式（覆盖一切 probe 误判场景）
  const forceTranscode = () => {
    info = { ...(info || {}), mode: "transcode", ffmpeg: true };
    startOffset = Math.max(0, video.currentTime || 0);
    page.querySelector("#loadtip")?.remove();
    page.append(h("div", { class: "loadtip", id: "loadtip" }, "⚡ 转码启动中，请稍候…"));
    if (!tcBadge?.isConnected) { // 强制转码后补上 ⚡ 徽标（直连起播时未创建）
      const badge = tcBadge || h("span", { class: "p-badge", title: "服务端正在实时转码" }, "⚡ 转码");
      btnBar.insertBefore(badge, timeLabel.nextSibling);
    }
    video.src = srcUrl(startOffset);
    video.play()?.catch(() => {});
    toast("已切换为转码播放", "info");
  };
  video.addEventListener("error", () => {
    page.querySelector("#loadtip")?.remove();
    const ec = video.error?.code || 0;
    const unsupported = ec === 4 /* SRC_NOT_SUPPORTED */ || ec === 3 /* DECODE */;
    let reason;
    if (transcoded()) {
      reason = "转码播放失败 — 请确认 ffmpeg 可用或文件未损坏，可重试";
      if (isLocal()) reason += "或改用 mpv 外放";
    } else if (unsupported) {
      reason = info?.ffmpeg
        ? `该视频编码${v.codec ? `（${v.codec}）` : ""}无法直接网页播放 — 点击「⚡ 尝试转码播放」即可在线观看${isLocal() ? "，或用 mpv 外放" : ""}`
        : `该视频编码${v.codec ? `（${v.codec}）` : ""}浏览器无法解码 — 建议在设置中配置 ffmpeg 以启用网页转码${isLocal() ? "，或用 mpv 外放" : ""}`;
    } else {
      reason = "视频流加载失败，请检查文件是否被移动或删除";
    }
    page.append(h("div", { class: "loadtip", id: "loadtip" },
      h("div", { style: "text-align:center" }, reason,
        h("div", { style: "margin-top:12px;display:flex;gap:10px;justify-content:center;flex-wrap:wrap" },
          transcoded() ? h("button", { class: "btn primary sm", onclick: () => doSeek(curPos()) }, "↻ 重试转码") : null,
          !transcoded() && info?.ffmpeg ? h("button", { class: "btn primary sm", onclick: forceTranscode }, "⚡ 尝试转码播放") : null,
          isLocal() ? h("button", { class: "btn primary sm", onclick: () => mpvBtn.click() }, "🖥 用 mpv 播放") : null,
          h("a", { class: "btn sm", href: "#/videos" }, "← 返回视频库")))));
  });

  function updTime() {
    const cur = curPos(), total = dur();
    playedBar.style.width = total ? `${cur / total * 100}%` : "0";
    seekKnob.style.left = total ? `${cur / total * 100}%` : "0";
    timeLabel.textContent = `${fmtDur(cur)} / ${fmtDur(total)}`;
  }

  /* ---- 播放控制 ---- */
  // 统一 seek 入口：直连流直接跳；转码流重启 ffmpeg（?start=）续转
  const doSeek = (t) => {
    if (!dur()) return;
    t = Math.min(Math.max(0, t), dur() - 0.5);
    if (transcoded()) {
      seeking = false;
      startOffset = Math.max(0, t);
      page.querySelector("#loadtip")?.remove();
      page.append(h("div", { class: "loadtip", id: "loadtip" }, "⚡ 转码跳转中…"));
      video.src = srcUrl(startOffset);
      video.play()?.catch(() => {});
      updTime();
    } else {
      video.currentTime = t;
    }
  };
  const seekBy = (dt) => doSeek(curPos() + dt);
  const togglePlay = () => { video.paused ? video.play().catch(() => {}) : video.pause(); };
  playBtn.addEventListener("click", togglePlay);
  back10.addEventListener("click", () => seekBy(-10));
  fwd10.addEventListener("click", () => seekBy(10));
  muteBtn.addEventListener("click", () => { video.muted = !video.muted; muteBtn.textContent = video.muted ? "🔇" : "🔊"; });
  volSlider.addEventListener("input", () => {
    video.volume = parseFloat(volSlider.value);
    video.muted = video.volume === 0;
    localStorage.setItem("mb_vol", String(video.volume));
    muteBtn.textContent = video.muted ? "🔇" : "🔊";
  });
  rateSel.addEventListener("change", () => {
    video.playbackRate = parseFloat(rateSel.value);
    localStorage.setItem("mb_rate", rateSel.value);
  });
  const toggleFs = () => {
    if (document.fullscreenElement) document.exitFullscreen?.();
    else if (page.requestFullscreen) page.requestFullscreen();
    else video.webkitEnterFullscreen?.(); // iOS Safari
  };
  fsBtn.addEventListener("click", toggleFs);
  document.addEventListener("fullscreenchange", () => {
    fsBtn.textContent = document.fullscreenElement ? "⤡" : "⛶";
  });
  pipBtn.addEventListener("click", async () => {
    try { await video.requestPictureInPicture?.(); } catch { toast("画中画不可用", "err"); }
  });

  /* ---- 顶栏动作 ---- */
  shotBtn.addEventListener("click", async () => {
    try {
      const r = await api.post(`/videos/${vid}/screenshots`, { time: curPos(), note: title });
      toast(`截图成功 #${r.id}`, "ok");
    } catch (e) { toast(e.message, "err"); }
  });
  mpvBtn.addEventListener("click", async () => {
    try {
      video.pause();
      await api.post(`/videos/${vid}/mpv`, { position: curPos() });
      toast("已调用 mpv 播放", "ok");
    } catch (e) { toast(e.message, "err"); }
  });
  const goBack = () => {
    report(true);
    if (window.history.length > 1) history.back();
    else location.hash = "#/videos";
  };
  closeBtn.addEventListener("click", goBack);

  /* ---- 快捷键帮助 ---- */
  const showHelp = () => {
    modal((box, close) => {
      const rows = [
        ["空格 / 点击画面", "播放 / 暂停"],
        ["← / → 或 J / L", "后退 / 前进 10 秒"],
        ["↑ / ↓", "音量加减"],
        ["0-9", "跳转到 0%-90% 位置"],
        ["F", "全屏切换"],
        ["M", "静音"],
        ["P", "画中画"],
        ["C", "字幕开关（有字幕文件时）"],
        ["Esc / Backspace", "退出全屏 / 退出播放"],
        ["双击画面左侧 / 右侧", "快退 / 快进 10 秒"],
        ["双击画面中间", "全屏切换"],
        ["拖动进度条", "预览缩略图，松手跳转"],
        ["⚡ 转码徽标", "该格式正在服务端实时转码（拖动进度会短暂重启转码）"],
        ["/", "返回页面后聚焦搜索"],
      ];
      box.append(h("h3", {}, "⌨ 播放器快捷键"),
        h("div", { class: "kbd-list" }, ...rows.map(([k, d]) =>
          h("div", { class: "kbd-row" }, h("kbd", {}, k), h("span", {}, d)))),
        h("div", { class: "acts" }, h("button", { class: "btn primary", onclick: close }, "知道了")));
    });
  };
  helpBtn.addEventListener("click", showHelp);

  /* ---- 键盘 ---- */
  const onKey = (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || e.target.tagName === "TEXTAREA") return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    switch (e.key) {
      case " ": e.preventDefault(); togglePlay(); break;
      case "ArrowLeft": e.preventDefault(); seekBy(-10); break;
      case "ArrowRight": e.preventDefault(); seekBy(10); break;
      case "j": case "J": seekBy(-10); break;
      case "l": case "L": seekBy(10); break;
      case "ArrowUp": e.preventDefault(); video.volume = Math.min(1, video.volume + 0.1); volSlider.value = video.volume; break;
      case "ArrowDown": e.preventDefault(); video.volume = Math.max(0, video.volume - 0.1); volSlider.value = video.volume; break;
      case "f": case "F": toggleFs(); break;
      case "m": case "M": muteBtn.click(); break;
      case "p": case "P": pipBtn.click(); break;
      case "c": case "C": ccBtn?.click(); break;
      case "?": showHelp(); break;
      case "Escape":
        if (document.fullscreenElement) document.exitFullscreen?.();
        else goBack();
        break;
      case "Backspace":
        if (!document.fullscreenElement) goBack();
        break;
      default:
        if (/^[0-9]$/.test(e.key) && dur()) {
          doSeek(dur() * (parseInt(e.key, 10) / 10));
        }
    }
  };
  document.addEventListener("keydown", onKey);

  /* ---- 双击区域：左快退 / 右快进 / 中全屏 ---- */
  video.addEventListener("dblclick", (e) => {
    const rect = page.getBoundingClientRect();
    const rx = (e.clientX - rect.left) / rect.width;
    if (rx < 0.33) seekBy(-10);
    else if (rx > 0.67) seekBy(10);
    else toggleFs();
  });
  video.addEventListener("click", togglePlay);

  /* ---- 空闲隐藏控制栏 ---- */
  let idleTimer = null;
  const wake = () => {
    page.classList.remove("player-idle");
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => {
      if (!video.paused) page.classList.add("player-idle");
    }, 2600);
  };
  page.addEventListener("mousemove", wake);
  page.addEventListener("touchstart", wake, { passive: true });
  page.addEventListener("mouseleave", () => { if (!video.paused) page.classList.add("player-idle"); });
  wake();

  return () => {
    clearInterval(reportTimer);
    document.removeEventListener("keydown", onKey);
    report(true);
    video.pause();
    video.removeAttribute("src");
    video.load();
  };
}
