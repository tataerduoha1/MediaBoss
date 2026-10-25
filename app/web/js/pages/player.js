/** 播放器：自定义控制栏、雪碧图悬停预览、进度记忆、mpv 外放、截图、触屏与快捷键。 */
import { api } from "../api.js?v=4";
import { h, toast, fmtDur, modal } from "../util.js?v=4";

export async function render(root, params) {
  const vid = params[1];
  document.title = "播放 · MediaBoss";

  let v, j;
  try {
    const d = await api.get(`/videos/${vid}`);
    v = d.video; j = d.jav;
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

  const video = h("video", { src: `/api/videos/${vid}/stream`, autoplay: "", playsinline: "" });
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
  const playBtn = h("button", { class: "pb", title: "播放/暂停 (空格)" }, "⏸");
  const back10 = h("button", { class: "pb", title: "后退 10s (← / J)" }, "⏪");
  const fwd10 = h("button", { class: "pb", title: "前进 10s (→ / L)" }, "⏩");
  const muteBtn = h("button", { class: "pb", title: "静音 (M)" }, "🔊");
  const volSlider = h("input", { class: "vol", type: "range", min: 0, max: 1, step: 0.05, value: 1 });
  const rateSel = h("select", { class: "pb rate", title: "倍速", style: "background:none;border:none;color:#fff;outline:none" },
    ["0.5", "0.75", "1", "1.25", "1.5", "2", "3"].map((r) =>
      h("option", { value: r, selected: r === "1" }, `${r}x`)));
  const fsBtn = h("button", { class: "pb", title: "全屏 (F)" }, "⛶");
  const pipBtn = h("button", { class: "pb", title: "画中画 (P)" }, "PiP");
  const helpBtn = h("button", { class: "pb", title: "快捷键帮助 (?)" }, "⌨");

  const btnBar = h("div", { class: "p-btns" },
    playBtn, back10, fwd10, timeLabel,
    h("span", { class: "spacer" }),
    muteBtn, volSlider, rateSel, pipBtn, fsBtn, helpBtn);

  const controls = h("div", { class: "p-controls" }, seekbar, btnBar);

  /* ---- 顶栏按钮 ---- */
  const shotBtn = h("button", { class: "btn sm", title: "截图当前画面" }, "📷 截图");
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
  const closeBtn = h("button", { class: "back", title: "返回 (Esc)" }, "←");
  const topbar = h("div", { class: "p-topbar" },
    closeBtn, h("div", { class: "tt" }, title),
    h("div", { class: "acts" }, shotBtn, mpvBtn, favB));

  page.append(video, topbar, controls,
    h("div", { class: "loadtip", id: "loadtip" }, "加载中…"));

  /* ---- 进度上报 ---- */
  let startedSent = false;
  let lastReport = 0;
  function report(force = false) {
    if (!video.duration) return;
    const now = Date.now();
    if (!force && now - lastReport < 9000) return;
    lastReport = now;
    const pos = video.currentTime;
    fetch(`/api/videos/${vid}/progress`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ position: pos, duration: video.duration, started: startedSent ? false : true }),
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
    if (!spriteImg || !spriteImg.width || !video.duration) return;
    const idx = Math.min(99, Math.max(0, Math.floor(t / video.duration * 100)));
    const col = idx % 10, row = Math.floor(idx / 10);
    const tw = spriteImg.width / 10, th = spriteImg.height / 10;
    const ctx = spriteCanvas.getContext("2d");
    ctx.drawImage(spriteImg, col * tw, row * th, tw, th, 0, 0, spriteCanvas.width, spriteCanvas.height);
    spriteTime.textContent = fmtDur(t);
  }

  /* ---- 进度条交互：拖动只预览，松手才跳转（避免拖动卡顿）---- */
  let seeking = false;      // 鼠标/触摸拖动中
  let pendingT = 0;         // 拖动目标时间
  const posFromX = (clientX) => {
    const rect = seekbar.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    return ratio * (video.duration || 0);
  };
  const previewSeek = (clientX) => {
    if (!video.duration) return;
    pendingT = posFromX(clientX);
    const rect = seekbar.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    playedBar.style.width = `${ratio * 100}%`;
    seekKnob.style.left = `${ratio * 100}%`;
    timeLabel.textContent = `${fmtDur(pendingT)} / ${fmtDur(video.duration)}`;
    const x = Math.min(rect.width - 80, Math.max(80, clientX - rect.left));
    spritePop.style.left = `${x}px`;
    drawSprite(pendingT);
  };
  const commitSeek = () => {
    if (!seeking) return;
    seeking = false;
    if (video.duration && pendingT >= 0) video.currentTime = pendingT;
    updTime();
  };
  seekbar.addEventListener("mousemove", (e) => {
    if (!video.duration) return;
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
    if (!video.duration) return;
    seeking = true;
    previewSeek(e.clientX);
  });
  window.addEventListener("mouseup", commitSeek);
  // 触屏：触摸拖动预览，抬手跳转
  seekbar.addEventListener("touchstart", (e) => {
    if (!video.duration) return;
    seeking = true;
    previewSeek(e.touches[0].clientX);
  }, { passive: true });
  seekbar.addEventListener("touchmove", (e) => {
    if (seeking) previewSeek(e.touches[0].clientX);
  }, { passive: true });
  seekbar.addEventListener("touchend", commitSeek);
  seekbar.addEventListener("click", (e) => {
    if (video.duration) video.currentTime = posFromX(e.clientX);
  });

  /* ---- 视频事件 ---- */
  video.addEventListener("loadedmetadata", () => {
    page.querySelector("#loadtip")?.remove();
    if (v.resume_position && v.resume_position < video.duration * 0.9) {
      video.currentTime = v.resume_position;
      toast(`已恢复到 ${fmtDur(v.resume_position)}（从头看请拖回开头）`, "info", 2400);
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
      if (video.buffered.length) {
        const end = video.buffered.end(video.buffered.length - 1);
        bufBar.style.width = `${end / video.duration * 100}%`;
      }
    } catch { /* ignore */ }
  });
  video.addEventListener("play", () => { playBtn.textContent = "⏸"; });
  video.addEventListener("pause", () => { playBtn.textContent = "▶"; });
  video.addEventListener("ended", () => { toast("播放结束", "ok"); report(true); });
  video.addEventListener("error", () => {
    page.querySelector("#loadtip")?.remove();
    const ec = video.error?.code || 0;
    const unsupported = ec === 4 /* SRC_NOT_SUPPORTED */ || ec === 3 /* DECODE */;
    const reason = unsupported
      ? `该视频编码${v.codec ? `（${v.codec}）` : ""}浏览器无法解码 — 常见于 H.265/HEVC 或低码率封装，建议用 mpv 外放`
      : "视频流加载失败，请检查文件是否被移动或删除";
    page.append(h("div", { class: "loadtip" },
      h("div", { style: "text-align:center" }, reason,
        h("div", { style: "margin-top:12px;display:flex;gap:10px;justify-content:center" },
          h("button", { class: "btn primary sm", onclick: () => mpvBtn.click() }, "🖥 用 mpv 播放"),
          h("a", { class: "btn sm", href: "#/videos" }, "← 返回视频库")))));
  });

  function updTime() {
    const cur = video.currentTime || 0, dur = video.duration || 0;
    playedBar.style.width = dur ? `${cur / dur * 100}%` : "0";
    seekKnob.style.left = dur ? `${cur / dur * 100}%` : "0";
    timeLabel.textContent = `${fmtDur(cur)} / ${fmtDur(dur)}`;
  }

  /* ---- 播放控制 ---- */
  const seekBy = (dt) => {
    video.currentTime = Math.min(video.duration || 1e9,
      Math.max(0, video.currentTime + dt));
  };
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
      const r = await api.post(`/videos/${vid}/screenshots`, { time: video.currentTime, note: title });
      toast(`截图成功 #${r.id}`, "ok");
    } catch (e) { toast(e.message, "err"); }
  });
  mpvBtn.addEventListener("click", async () => {
    try {
      video.pause();
      await api.post(`/videos/${vid}/mpv`, { position: video.currentTime });
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
        ["Esc", "退出全屏 / 返回"],
        ["双击画面左侧 / 右侧", "快退 / 快进 10 秒"],
        ["双击画面中间", "全屏切换"],
        ["拖动进度条", "预览缩略图，松手跳转"],
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
      case "?": showHelp(); break;
      case "Escape":
        if (document.fullscreenElement) document.exitFullscreen?.();
        else goBack();
        break;
      default:
        if (/^[0-9]$/.test(e.key) && video.duration) {
          video.currentTime = video.duration * (parseInt(e.key, 10) / 10);
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
