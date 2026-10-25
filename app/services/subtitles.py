"""外挂字幕服务：查找视频同名字幕并转换为 WebVTT（纯标准库）。

支持 srt / ass / ssa / vtt；编码自动尝试 utf-8 → utf-8-sig → gbk。
"""
import os
import re

SUB_EXTS = (".srt", ".ass", ".ssa", ".vtt")
MAX_BYTES = 4 * 1024 * 1024  # 超大字幕（>4MB）忽略

_TS_SRT = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})")
_ASS_FMT = re.compile(r"^\s*Format\s*:\s*(.+)\s*$", re.IGNORECASE)
_ASS_LINE = re.compile(r"^\s*Dialogue\s*:\s*(.*)$", re.IGNORECASE)
_ASS_TAG = re.compile(r"\{[^}]*\}")


def _read_text(path: str) -> str:
    raw = open(path, "rb").read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        return ""
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")


def find_subtitle(video_path: str) -> str | None:
    """查找与视频同名的字幕文件（同目录同名 + .chi/.chs/.sc 等常见后缀变体）。"""
    base = os.path.splitext(video_path)[0]
    stem = os.path.basename(base)
    dirname = os.path.dirname(video_path)
    try:
        entries = os.listdir(dirname)
    except OSError:
        return None
    # 精确同名优先，其次「同名.任意字符.扩展」
    cands = []
    for name in entries:
        low = name.lower()
        if not low.endswith(SUB_EXTS):
            continue
        root = os.path.splitext(name)[0].lower()
        if root == stem.lower() or root.startswith(stem.lower() + "."):
            cands.append(os.path.join(dirname, name))
    if not cands:
        return None
    # srt/vtt 优先于 ass（ffmpeg 兼容性无关紧要，此处统一转 vtt，按长度短者优先即可）
    cands.sort(key=lambda p: os.path.getsize(p))
    return cands[0]


def _fmt_ts(h: str, m: str, s: str, ms: str) -> str:
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}.{int((ms or '0').ljust(3, '0')[:3]):03d}"


def _srt_to_vtt(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out = ["WEBVTT", ""]
    for block in re.split(r"\n{2,}", text):
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        if "-->" not in lines[0] and len(lines) >= 2 and "-->" in lines[1]:
            lines = lines[1:]  # 去掉序号行
        converted = []
        for ln in lines:
            m = _TS_SRT.search(ln)
            if m and "-->" in ln:
                ln = _TS_SRT.sub(
                    lambda g: _fmt_ts(g.group(1), g.group(2), g.group(3), g.group(4)), ln)
            converted.append(ln)
        if any("-->" in ln for ln in converted):
            out.extend(converted)
            out.append("")
    return "\n".join(out)


def _ass_to_vtt(text: str) -> str:
    """解析 ass/ssa 的 [Events] Dialogue 行为顺序 cue（含简单标签清洗）。"""
    lines_raw = text.replace("\r\n", "\n").split("\n")
    fields = []      # Dialogue 字段顺序
    text_idx = -1
    cues = []
    for ln in lines_raw:
        m = _ASS_FMT.match(ln)
        if m:
            fields = [f.strip().lower() for f in m.group(1).split(",")]
            text_idx = fields.index("text") if "text" in fields else 9
            continue
        m = _ASS_LINE.match(ln)
        if not m:
            continue
        parts = m.group(1).split(",", text_idx if text_idx > 0 else 9)
        if len(parts) <= text_idx:
            continue
        start, end, body = parts[1].strip(), parts[2].strip(), parts[text_idx].strip()
        ts = _TS_SRT.search(start), _TS_SRT.search(end)
        if not all(ts):
            continue
        # 清洗 {\...} 覆写标签、\N/\n 换行、<i> 等 html 标签
        body = _ASS_TAG.sub("", body)
        body = body.replace(r"\N", "\n").replace(r"\n", "\n").replace(r"\h", " ")
        body = re.sub(r"</?[biu][^>]*>", "", body)
        body = body.strip()
        if not body:
            continue
        s = _fmt_ts(*ts[0].groups())
        e = _fmt_ts(*ts[1].groups())
        cues.append((s, e, body))

    def key(c):
        return _TS_SRT.search(c[0]).group(0)

    cues.sort(key=key)
    out = ["WEBVTT", ""]
    out.extend(f"{s} --> {e}\n{b}\n" for s, e, b in cues)
    return "\n".join(out)


def to_vtt(path: str) -> str | None:
    """读取字幕文件并转为 VTT 内容；无法解析返回 None。"""
    ext = os.path.splitext(path)[1].lower()
    text = _read_text(path)
    if not text:
        return None
    if ext == ".vtt":
        if text.lstrip().startswith("WEBVTT"):
            return text
        return _srt_to_vtt(text)
    if ext == ".ass" or ext == ".ssa":
        return _ass_to_vtt(text)
    return _srt_to_vtt(text)
