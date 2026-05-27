#!/usr/bin/env python3
"""Generate dependency-free marketing assets for Scholar Alert Reader."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "docs" / "assets"

PALETTE = {
    "bg": 0,
    "ink": 1,
    "muted": 2,
    "blue": 3,
    "blue2": 4,
    "green": 5,
    "green2": 6,
    "amber": 7,
    "amber2": 8,
    "red": 9,
    "panel": 10,
    "line": 11,
    "white": 12,
}

RGB = [
    (248, 250, 252),
    (17, 24, 39),
    (71, 85, 105),
    (37, 99, 235),
    (219, 234, 254),
    (5, 150, 105),
    (209, 250, 229),
    (217, 119, 6),
    (254, 243, 199),
    (220, 38, 38),
    (255, 255, 255),
    (148, 163, 184),
    (255, 255, 255),
] + [(0, 0, 0)] * 243

FONT = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "J": ["00111", "00010", "00010", "00010", "10010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["10010", "10010", "10010", "11111", "00010", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
    "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
    ":": ["00000", "01100", "01100", "00000", "01100", "01100", "00000"],
}


def svg_assets() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    logo_mark = """
<rect width="512" height="512" rx="108" fill="#101827"/>
<circle cx="394" cy="128" r="72" fill="#0ea5a4" opacity=".18"/>
<path d="M148 112h188c28 0 50 22 50 50v206c0 28-22 50-50 50H148c-28 0-50-22-50-50V162c0-28 22-50 50-50z" fill="#f8fafc"/>
<path d="M336 112v74c0 18 15 33 33 33h17" fill="none" stroke="#cbd5e1" stroke-width="20" stroke-linecap="round"/>
<path d="M150 174h126M150 220h152M150 266h104" stroke="#2563eb" stroke-width="22" stroke-linecap="round"/>
<path d="M122 352c44-32 86-32 126 0 40-32 82-32 126 0v42c-44-30-86-30-126 0-40-30-82-30-126 0v-42z" fill="#dbeafe"/>
<circle cx="356" cy="154" r="28" fill="#10b981"/>
<path d="M356 92v-26M356 242v-26M294 154h-26M444 154h-26" stroke="#10b981" stroke-width="17" stroke-linecap="round"/>
<path d="M306 104a78 78 0 0 1 100 0M306 204a78 78 0 0 0 100 0" fill="none" stroke="#10b981" stroke-width="13" stroke-linecap="round" opacity=".88"/>
<path d="M146 333c42-20 75-16 102 10 27-26 60-30 102-10" fill="none" stroke="#93c5fd" stroke-width="16" stroke-linecap="round"/>
"""
    logo = f"""<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512" role="img" aria-labelledby="title desc">
<title id="title">Scholar Alert Reader logo</title>
<desc id="desc">A paper, alert signal, and reading foundation mark for Scholar Alert Reader.</desc>
{logo_mark}
</svg>
"""
    architecture = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675" role="img" aria-labelledby="title desc">
<title id="title">Scholar Alert Reader architecture</title>
<desc id="desc">Scholar Alert Reader 中文宣传架构图：从 Scholar Alert 邮件到每日简报、重点阅读、个人知识库、深读问答和 Obsidian/Zotero 导出。</desc>
<defs>
  <linearGradient id="hero" x1="0" x2="1" y1="0" y2="1">
    <stop offset="0" stop-color="#101827"/>
    <stop offset=".58" stop-color="#12343b"/>
    <stop offset="1" stop-color="#0f766e"/>
  </linearGradient>
  <linearGradient id="panel" x1="0" x2="0" y1="0" y2="1">
    <stop offset="0" stop-color="#ffffff"/>
    <stop offset="1" stop-color="#f8fafc"/>
  </linearGradient>
  <pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse">
    <path d="M 28 0 H 0 V 28" fill="none" stroke="#dbe4ee" stroke-width="1" opacity=".45"/>
  </pattern>
  <filter id="shadow" x="-20%" y="-25%" width="140%" height="150%">
    <feDropShadow dx="0" dy="14" stdDeviation="12" flood-color="#0f172a" flood-opacity=".14"/>
  </filter>
  <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
    <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b"/>
  </marker>
</defs>
<rect width="1200" height="675" fill="#f6f8fb"/>
<rect width="1200" height="675" fill="url(#grid)"/>
<rect x="48" y="38" width="1104" height="126" rx="28" fill="url(#hero)" filter="url(#shadow)"/>
<g transform="translate(82 66) scale(.13)">{logo_mark}</g>
<text x="168" y="94" fill="#ffffff" font-family="PingFang SC, Inter, Arial, sans-serif" font-size="34" font-weight="850">Scholar Alert Reader</text>
<text x="168" y="128" fill="#cdece8" font-family="PingFang SC, Inter, Arial, sans-serif" font-size="20" font-weight="600">每天筛论文，长期积累自己的研究线索</text>
<text x="835" y="92" fill="#ffffff" font-family="PingFang SC, Inter, Arial, sans-serif" font-size="17" font-weight="750">本地运行 · 隐私可控 · 多工具可用</text>
<text x="835" y="123" fill="#cdece8" font-family="PingFang SC, Inter, Arial, sans-serif" font-size="14">Codex / Claude / 终端均可使用</text>

<g font-family="PingFang SC, Inter, Arial, sans-serif">
  <rect x="62" y="205" width="302" height="318" rx="24" fill="url(#panel)" stroke="#d8e0ea" filter="url(#shadow)"/>
  <text x="92" y="246" fill="#0f172a" font-size="25" font-weight="850">1. 汇聚来源</text>
  <text x="92" y="276" fill="#64748b" font-size="16">自动读取 Scholar Alert</text>
  <rect x="92" y="314" width="216" height="58" rx="14" fill="#dbeafe" stroke="#bfdbfe"/>
  <text x="116" y="350" fill="#1d4ed8" font-size="18" font-weight="800">Gmail API</text>
  <rect x="114" y="394" width="216" height="58" rx="14" fill="#dcfce7" stroke="#bbf7d0"/>
  <text x="138" y="430" fill="#047857" font-size="18" font-weight="800">邮件归档</text>
  <rect x="92" y="474" width="216" height="58" rx="14" fill="#fef3c7" stroke="#fde68a"/>
  <text x="116" y="510" fill="#92400e" font-size="18" font-weight="800">Apple Mail</text>
  <path d="M285 318l32 18 -32 18z" fill="#93c5fd" opacity=".7"/>
  <path d="M307 398l32 18 -32 18z" fill="#86efac" opacity=".7"/>
  <path d="M285 478l32 18 -32 18z" fill="#fcd34d" opacity=".7"/>

  <rect x="449" y="188" width="302" height="352" rx="28" fill="#ffffff" stroke="#2563eb" stroke-width="2.5" filter="url(#shadow)"/>
  <rect x="477" y="216" width="246" height="70" rx="18" fill="#eff6ff"/>
  <text x="508" y="246" fill="#1e3a8a" font-size="18" font-weight="800">2. 自动分诊</text>
  <text x="508" y="270" fill="#475569" font-size="14">去重、打分、按偏好排序</text>
  <g font-size="15" font-weight="760">
    <rect x="489" y="318" width="94" height="42" rx="12" fill="#dbeafe"/><text x="520" y="344" fill="#1d4ed8">抽取</text>
    <rect x="607" y="318" width="94" height="42" rx="12" fill="#dcfce7"/><text x="638" y="344" fill="#047857">合并</text>
    <rect x="489" y="380" width="94" height="42" rx="12" fill="#ede9fe"/><text x="520" y="406" fill="#6d28d9">排序</text>
    <rect x="607" y="380" width="94" height="42" rx="12" fill="#fef3c7"/><text x="638" y="406" fill="#92400e">反馈</text>
  </g>
  <path d="M536 457h128" stroke="#94a3b8" stroke-width="2.5" stroke-linecap="round"/>
  <circle cx="536" cy="457" r="5" fill="#2563eb"/><circle cx="664" cy="457" r="5" fill="#10b981"/>
  <text x="491" y="492" fill="#0f172a" font-size="17" font-weight="800">研究方向 + 你的选择</text>
  <text x="491" y="518" fill="#64748b" font-size="14">越用越贴近当前问题</text>

  <rect x="836" y="205" width="302" height="318" rx="24" fill="url(#panel)" stroke="#d8e0ea" filter="url(#shadow)"/>
  <text x="866" y="246" fill="#0f172a" font-size="25" font-weight="850">3. 形成知识库</text>
  <text x="866" y="276" fill="#64748b" font-size="16">把值得读的论文留下来</text>
  <g font-size="16" font-weight="800">
    <rect x="866" y="313" width="104" height="48" rx="14" fill="#e0f2fe" stroke="#bae6fd"/><text x="886" y="343" fill="#075985">每日简报</text>
    <rect x="990" y="313" width="116" height="48" rx="14" fill="#d1fae5" stroke="#a7f3d0"/><text x="1014" y="343" fill="#047857">阅读队列</text>
    <rect x="866" y="381" width="130" height="48" rx="14" fill="#ede9fe" stroke="#ddd6fe"/><text x="899" y="411" fill="#6d28d9">文献底座</text>
    <rect x="1008" y="381" width="98" height="48" rx="14" fill="#fef3c7" stroke="#fde68a"/><text x="1025" y="411" fill="#92400e">深读问答</text>
    <rect x="866" y="449" width="240" height="48" rx="14" fill="#fff7ed" stroke="#fed7aa"/><text x="929" y="479" fill="#c2410c">笔记与引用</text>
  </g>
</g>

<g stroke="#64748b" stroke-width="4" fill="none" marker-end="url(#arrow)">
  <path d="M364 364 C398 364 412 364 449 364"/>
  <path d="M751 364 C790 364 800 364 836 364"/>
</g>
<g font-family="PingFang SC, Inter, Arial, sans-serif">
  <rect x="190" y="570" width="820" height="56" rx="18" fill="#ffffff" stroke="#d8e0ea"/>
  <text x="224" y="604" fill="#475569" font-size="17" font-weight="650">本地处理 · 授权文件只留本机 · 筛掉的论文不进知识库</text>
  <text x="1035" y="606" fill="#64748b" font-size="15" font-weight="650">作者：Xin Liu</text>
</g>
</svg>
"""
    social = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-labelledby="title desc">
<title id="title">Scholar Alert Reader social card</title>
<desc id="desc">A social sharing card for Scholar Alert Reader.</desc>
<rect width="1200" height="630" fill="#0f172a"/>
<circle cx="1010" cy="90" r="180" fill="#1d4ed8" opacity=".28"/><circle cx="170" cy="530" r="220" fill="#10b981" opacity=".20"/>
<rect x="80" y="78" width="1040" height="474" rx="34" fill="#f8fafc"/>
<g transform="translate(132 124) scale(.15)">{logo_mark}</g>
<text x="230" y="180" fill="#111827" font-family="Inter, Arial, sans-serif" font-size="64" font-weight="850">Scholar Alert Reader</text>
<text x="136" y="235" fill="#475569" font-family="Inter, Arial, sans-serif" font-size="27">Turn Google Scholar Alerts into a personal literature copilot.</text>
<g font-family="Inter, Arial, sans-serif" font-weight="800" font-size="24">
  <rect x="138" y="304" width="180" height="68" rx="18" fill="#dbeafe"/><text x="176" y="347" fill="#1d4ed8">Digest</text>
  <rect x="346" y="304" width="216" height="68" rx="18" fill="#dcfce7"/><text x="382" y="347" fill="#047857">Foundation</text>
  <rect x="590" y="304" width="176" height="68" rx="18" fill="#ede9fe"/><text x="636" y="347" fill="#6d28d9">Q&amp;A</text>
  <rect x="794" y="304" width="218" height="68" rx="18" fill="#fef3c7"/><text x="828" y="347" fill="#92400e">Obsidian</text>
</g>
<text x="138" y="456" fill="#111827" font-family="Inter, Arial, sans-serif" font-size="30" font-weight="750">Local · Private · Codex-only optional · Zotero/Obsidian ready</text>
<text x="138" y="506" fill="#64748b" font-family="Inter, Arial, sans-serif" font-size="22" font-weight="650">Created by Xin Liu · RunningXinLiu</text>
</svg>
"""
    (ASSET_DIR / "logo.svg").write_text(logo, encoding="utf-8")
    (ASSET_DIR / "architecture.svg").write_text(architecture, encoding="utf-8")
    (ASSET_DIR / "architecture-showcase.svg").write_text(architecture, encoding="utf-8")
    (ASSET_DIR / "social-card.svg").write_text(social, encoding="utf-8")


def png_assets() -> None:
    sips = shutil.which("sips")
    if not sips:
        return
    for name in ["architecture", "architecture-showcase", "social-card", "logo"]:
        subprocess.run(
            [sips, "-s", "format", "png", str(ASSET_DIR / f"{name}.svg"), "--out", str(ASSET_DIR / f"{name}.png")],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def blank(width: int, height: int, color: int) -> bytearray:
    return bytearray([color] * (width * height))


def rect(buf: bytearray, width: int, x: int, y: int, w: int, h: int, color: int) -> None:
    height = len(buf) // width
    for yy in range(max(0, y), min(height, y + h)):
        start = yy * width + max(0, x)
        end = yy * width + min(width, x + w)
        buf[start:end] = bytes([color]) * max(0, end - start)


def line(buf: bytearray, width: int, x1: int, y1: int, x2: int, y2: int, color: int) -> None:
    dx = abs(x2 - x1)
    dy = -abs(y2 - y1)
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    err = dx + dy
    x, y = x1, y1
    height = len(buf) // width
    while True:
        if 0 <= x < width and 0 <= y < height:
            buf[y * width + x] = color
        if x == x2 and y == y2:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy


def arrow(buf: bytearray, width: int, x1: int, y1: int, x2: int, y2: int, color: int) -> None:
    for offset in range(-2, 3):
        line(buf, width, x1, y1 + offset, x2, y2 + offset, color)
    rect(buf, width, x2 - 10, y2 - 8, 16, 16, color)


def text(buf: bytearray, width: int, x: int, y: int, value: str, color: int, scale: int = 3) -> None:
    cursor = x
    for char in value.upper():
        if char == " ":
            cursor += 4 * scale
            continue
        pattern = FONT.get(char)
        if not pattern:
            cursor += 4 * scale
            continue
        for row, bits in enumerate(pattern):
            for col, bit in enumerate(bits):
                if bit == "1":
                    rect(buf, width, cursor + col * scale, y + row * scale, scale, scale, color)
        cursor += 6 * scale


def text_width(value: str, scale: int) -> int:
    total = 0
    for char in value.upper():
        total += (4 if char == " " else 6) * scale
    return total


def fit_scale(value: str, max_width: int, preferred: int = 3, minimum: int = 1) -> int:
    for scale in range(preferred, minimum - 1, -1):
        if text_width(value, scale) <= max_width:
            return scale
    return minimum


def fit_text(buf: bytearray, width: int, x: int, y: int, max_width: int, value: str, color: int, preferred: int = 3) -> None:
    scale = fit_scale(value, max_width, preferred=preferred)
    text(buf, width, x, y, value, color, scale)


def card(buf: bytearray, width: int, x: int, y: int, w: int, h: int, fill: int, label: str, label_color: int) -> None:
    rect(buf, width, x + 6, y + 6, w, h, PALETTE["line"])
    rect(buf, width, x, y, w, h, fill)
    rect(buf, width, x, y, w, 6, PALETTE["white"])
    scale = fit_scale(label, w - 48, preferred=3)
    text(buf, width, x + 24, y + h // 2 - (7 * scale) // 2, label, label_color, scale)


def gif_pack_codes(codes: list[int], code_size: int) -> bytes:
    out = bytearray()
    acc = 0
    bits = 0
    for code in codes:
        acc |= code << bits
        bits += code_size
        while bits >= 8:
            out.append(acc & 0xFF)
            acc >>= 8
            bits -= 8
    if bits:
        out.append(acc & 0xFF)
    return bytes(out)


def gif_image_data(indexes: bytes) -> bytes:
    clear = 256
    end = 257
    codes: list[int] = []
    chunk = 200
    for start in range(0, len(indexes), chunk):
        codes.extend([clear] + list(indexes[start : start + chunk]))
    codes.append(end)
    packed = gif_pack_codes(codes, 9)
    blocks = bytearray([8])
    for start in range(0, len(packed), 255):
        block = packed[start : start + 255]
        blocks.append(len(block))
        blocks.extend(block)
    blocks.append(0)
    return bytes(blocks)


def write_gif(path: Path, frames: list[bytearray], width: int, height: int, delay_cs: int = 100) -> None:
    data = bytearray(b"GIF89a")
    data.extend(width.to_bytes(2, "little"))
    data.extend(height.to_bytes(2, "little"))
    data.extend(bytes([0xF7, 0, 0]))
    for r, g, b in RGB[:256]:
        data.extend(bytes([r, g, b]))
    data.extend(b"!\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00")
    for frame in frames:
        data.extend(b"!\xf9\x04\x04")
        data.extend(delay_cs.to_bytes(2, "little"))
        data.extend(b"\x00\x00")
        data.extend(b",\x00\x00\x00\x00")
        data.extend(width.to_bytes(2, "little"))
        data.extend(height.to_bytes(2, "little"))
        data.extend(b"\x00")
        data.extend(gif_image_data(bytes(frame)))
    data.extend(b";")
    path.write_bytes(data)


def gif_assets() -> None:
    width, height = 800, 450
    frames: list[bytearray] = []
    steps = [
        ("SCHOLAR ALERT READER", "DAILY PAPER TRIAGE", ["GMAIL", "MBOX", "MAIL.APP"], "CODEX SKILL"),
        ("REDUCE NOISE FIRST", "DEDUPE + SCORE + FEEDBACK", ["ALERTS", "PROFILE", "FEEDBACK"], "READING QUEUE"),
        ("BUILD FOUNDATION", "CUMULATIVE RESEARCH MEMORY", ["DIGEST", "FOUNDATION", "INTERESTED"], "COPILOT"),
        ("OPTIONAL INTEGRATIONS", "OBSIDIAN AND ZOTERO READY", ["OBSIDIAN", "ZOTERO", "EXPORTS"], "YOUR WORKFLOW"),
        ("CODEX-ONLY WORKS", "LOCAL PRIVATE EXTENSIBLE", ["DEMO", "SOURCE CHECK", "HTML"], "START HERE"),
    ]
    for title, subtitle, left_labels, right_label in steps:
        buf = blank(width, height, PALETTE["bg"])
        rect(buf, width, 0, 0, width, 76, PALETTE["ink"])
        text(buf, width, 32, 24, title, PALETTE["white"], 4)
        text(buf, width, 36, 96, subtitle, PALETTE["muted"], 3)
        y_positions = [170, 245, 320]
        fills = [PALETTE["blue2"], PALETTE["green2"], PALETTE["amber2"]]
        colors = [PALETTE["blue"], PALETTE["green"], PALETTE["amber"]]
        for y, fill, color, label in zip(y_positions, fills, colors, left_labels):
            card(buf, width, 50, y, 210, 58, fill, label, color)
            arrow(buf, width, 270, y + 29, 370, y + 29, PALETTE["line"])
        card(buf, width, 380, 216, 270, 90, PALETTE["white"], right_label, PALETTE["ink"])
        arrow(buf, width, 660, 261, 724, 261, PALETTE["line"])
        rect(buf, width, 728, 222, 30, 78, PALETTE["blue"])
        text(buf, width, 706, 324, "OUTPUT", PALETTE["muted"], 2)
        text(buf, width, 642, 402, "BY XIN LIU", PALETTE["muted"], 2)
        frames.append(buf)
    write_gif(ASSET_DIR / "workflow.gif", frames, width, height, delay_cs=120)


def main() -> int:
    svg_assets()
    png_assets()
    gif_assets()
    print(f"Generated assets in {ASSET_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
