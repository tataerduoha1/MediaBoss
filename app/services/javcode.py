"""JAV 番号识别：从文件名中提取番号，支持标准番号、FC2、前缀数字番号等格式。"""
import re

# 已知噪声词（大小写不敏感），避免把分辨率/编码/分卷信息误认为番号
NOISE_WORDS = {
    "4K", "8K", "2K", "HDR", "SDR", "FHD", "UHD", "HD", "SD", "HQ", "LQ",
    "H264", "H265", "X264", "X265", "AVC", "HEVC", "AAC", "FLAC", "MP3", "AC3",
    "MP4", "MKV", "AVI", "WMV", "MOV", "MPG", "MPEG", "TS", "WEBM", "M4V", "ISO", "VOB", "FLV",
    "JAV", "JAVR", "CEN", "UNC", "CHS", "CHT", "CH", "BIG", "SMALL", "NEW",
    "CD1", "CD2", "CD3", "CD4", "CD5", "DISC1", "DISC2", "DISC3", "PART1", "PART2",
    "SUB", "SUBS", "RAW", "CAM", "RIP", "WEB", "WEBDL", "BLU", "RAY", "DVD", "DVDRIP",
    "XXX", "ADULT", "SEX", "VIDEO", "MOVIE", "FILM", "CLIP", "SCENE", "EP", "EPS",
    "C", "E", "V", "A", "B", "S", "T", "D", "M", "N", "K", "R", "W", "X", "Y", "Z",
    "AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III", "JJJ", "KKK",
    "LLL", "MMM", "NNN", "OOO", "PPP", "QQQ", "RRR", "SSS", "TTT", "UUU", "VVV",
    "WWW", "XXX2", "YYY", "ZZZ",
    "AM", "PM", "GB", "MB", "KB", "TB", "BIT", "BITS", "FPS", "BITRATE", "VBR", "CBR",
    "HIANIME", "TOKYO", "HOT", "TOKYOHOT",
}

_FC2_RE = re.compile(r"FC2[\s_-]*PPV[\s_-]*(\d{6,10})", re.IGNORECASE)
# 前缀数字番号: 259LUXU-1585 / 300MIUM-736 / 200GANA-2821 / 120SIRO-5203
_PREFIXED_RE = re.compile(r"\b(\d{2,4})([A-Z]{2,8})[-_ ](\d{2,6})\b")
# 标准番号: ABC-123 / ABC123 / ABC 123
_STANDARD_RE = re.compile(r"\b([A-Z]{2,7})[-_ ]?(\d{2,6})\b")


def _clean_word(word: str) -> str:
    return word.upper().strip()


def _is_noise(word: str) -> bool:
    return _clean_word(word) in NOISE_WORDS


def _std_candidates(text: str) -> list[str]:
    out = []
    for m in re.finditer(r"\b([A-Z]{2,7})[-_ ]?(\d{2,6})\b", text.upper()):
        letters, digits = m.group(1), m.group(2)
        if _is_noise(letters):
            continue
        # 避免把年份当番号数字部分（如 ABC-2023 保留，但 2023 单独出现不会匹配）
        code = f"{letters}-{digits}"
        has_sep = "-" in m.group(0) or "_" in m.group(0)
        score = (2 if has_sep else 0) + (2 if len(digits) >= 3 else 0) + (1 if len(letters) >= 3 else 0)
        out.append((score, code))
    out.sort(key=lambda t: -t[0])
    return [c for _, c in out]


def extract_codes(filename: str) -> list[str]:
    """从文件名提取番号候选列表，按可信度降序。返回空列表表示未识别。"""
    text = filename
    results: list[str] = []

    m = _FC2_RE.search(text)
    if m:
        results.append(f"FC2-PPV-{m.group(1)}")

    for m in _PREFIXED_RE.finditer(text.upper()):
        num, letters, digits = m.group(1), m.group(2), m.group(3)
        if not _is_noise(letters):
            results.append(f"{num}{letters}-{digits}")

    results.extend(_std_candidates(text))

    # 去重保持顺序
    seen = set()
    uniq = []
    for c in results:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def primary_code(filename: str) -> str | None:
    codes = extract_codes(filename)
    return codes[0] if codes else None
