#!/usr/bin/env python3
"""Generate dependency-free marketing assets for Scholar Alert Reader."""

from __future__ import annotations

import shutil
import struct
import subprocess
import tempfile
import zlib
from collections import Counter
from html import escape
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

LOGO_MARK = """
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


def logo_svg() -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512" role="img" aria-labelledby="title desc">
<title id="title">Scholar Alert Reader logo</title>
<desc id="desc">A paper, alert signal, and reading foundation mark for Scholar Alert Reader.</desc>
{LOGO_MARK}
</svg>
"""


def architecture_svg(locale: str) -> str:
    if locale == "zh":
        copy = {
            "desc": "Scholar Alert Reader 中文宣传架构图：从邮件、文献文件和结构化网页来源到个性化 digest、阅读队列、个人知识库和 Obsidian/Zotero 导出。",
            "subtitle": "多来源接入，按你的研究方向自动筛论文",
            "right1": "本地运行 · 隐私可控 · 多工具可用",
            "right2": "Codex / Claude / 终端均可使用",
            "source_title": "1. 汇聚来源",
            "source_subtitle": "邮件、网页来源、文献文件",
            "triage_title": "2. 自动分诊",
            "triage_subtitle": "抽取、去重、打分、反馈",
            "profile": "关键词 + 研究方向 + 反馈",
            "profile_subtitle": "越用越贴近当前问题",
            "kb_title": "3. 形成知识库",
            "kb_subtitle": "把值得读的论文留下来",
            "footer": "定时或手动推送 · 本地优先 · 可接 Zotero / Obsidian",
            "author": "作者：Xin Liu",
        }
        source_items = ["Gmail API", "Apple Mail", "mbox / 邮件归档", "BibTeX / RIS", "网页 / RSS / arXiv"]
        triage_items = ["抽取", "去重", "排序", "反馈"]
        kb_items = ["每日简报", "阅读队列", "文献底座", "深读问答", "笔记与引用"]
        font = "PingFang SC, Inter, Arial, sans-serif"
        small_font = 16
    else:
        copy = {
            "desc": "Scholar Alert Reader architecture: connect paper alerts, bibliography exports, scholarly webpages, feeds, and arXiv to personalized digests, reading queues, research memory, and Obsidian/Zotero exports.",
            "subtitle": "Connect sources, rank papers by your research profile",
            "right1": "Local-first · Private · Agent-friendly",
            "right2": "Codex / Claude / terminal ready",
            "source_title": "1. Collect sources",
            "source_subtitle": "Email, web, bibliography, feeds",
            "triage_title": "2. Triage automatically",
            "triage_subtitle": "Extract, dedupe, rank, feedback",
            "profile": "Keywords + Profile + Feedback",
            "profile_subtitle": "Adapts to your current questions",
            "kb_title": "3. Build knowledge",
            "kb_subtitle": "Keep papers worth reading",
            "footer": "Scheduled or manual digests · Local-first · Zotero / Obsidian ready",
            "author": "By Xin Liu",
        }
        source_items = ["Gmail API", "Apple Mail", "mbox archives", "BibTeX / RIS", "Web / RSS / arXiv"]
        triage_items = ["Extract", "Dedupe", "Rank", "Feedback"]
        kb_items = ["Digest", "Queue", "Foundation", "Deep read", "Notes"]
        font = "Inter, Arial, sans-serif"
        small_font = 15

    source_fills = [
        ("#dbeafe", "#bfdbfe", "#1d4ed8", "#93c5fd"),
        ("#dcfce7", "#bbf7d0", "#047857", "#86efac"),
        ("#fef3c7", "#fde68a", "#92400e", "#fcd34d"),
        ("#ede9fe", "#ddd6fe", "#6d28d9", "#c4b5fd"),
        ("#e0f2fe", "#bae6fd", "#075985", "#7dd3fc"),
    ]
    source_rows = []
    for index, (label, colors) in enumerate(zip(source_items, source_fills)):
        fill, stroke, text_color, arrow_color = colors
        y = 298 + index * 52
        x = 92 if index % 2 == 0 else 114
        tx = x + 24
        ax = 285 if index % 2 == 0 else 307
        source_rows.append(
            f'<rect x="{x}" y="{y}" width="216" height="40" rx="12" fill="{fill}" stroke="{stroke}"/>'
            f'<text x="{tx}" y="{y + 25}" fill="{text_color}" font-size="{small_font}" font-weight="800">{label}</text>'
            f'<path d="M{ax} {y + 2}l32 18 -32 18z" fill="{arrow_color}" opacity=".7"/>'
        )
    source_rows_svg = "\n  ".join(source_rows)

    triage_positions = [(489, 318), (607, 318), (489, 380), (607, 380)]
    triage_colors = [("#dbeafe", "#1d4ed8"), ("#dcfce7", "#047857"), ("#ede9fe", "#6d28d9"), ("#fef3c7", "#92400e")]
    triage_rows = []
    for label, (x, y), (fill, color) in zip(triage_items, triage_positions, triage_colors):
        text_x = x + (23 if locale == "en" else 31)
        triage_rows.append(
            f'<rect x="{x}" y="{y}" width="94" height="42" rx="12" fill="{fill}"/>'
            f'<text x="{text_x}" y="{y + 26}" fill="{color}">{label}</text>'
        )
    triage_rows_svg = "\n    ".join(triage_rows)

    kb_specs = [
        (866, 313, 104, "#e0f2fe", "#bae6fd", "#075985", 886 if locale == "zh" else 889),
        (990, 313, 116, "#d1fae5", "#a7f3d0", "#047857", 1014 if locale == "zh" else 1024),
        (866, 381, 130, "#ede9fe", "#ddd6fe", "#6d28d9", 899 if locale == "zh" else 888),
        (1008, 381, 98, "#fef3c7", "#fde68a", "#92400e", 1025 if locale == "zh" else 1022),
        (866, 449, 240, "#fff7ed", "#fed7aa", "#c2410c", 929 if locale == "zh" else 962),
    ]
    kb_rows = []
    for label, spec in zip(kb_items, kb_specs):
        x, y, w, fill, stroke, color, text_x = spec
        kb_rows.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="48" rx="14" fill="{fill}" stroke="{stroke}"/>'
            f'<text x="{text_x}" y="{y + 30}" fill="{color}">{label}</text>'
        )
    kb_rows_svg = "\n    ".join(kb_rows)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675" role="img" aria-labelledby="title desc">
<title id="title">Scholar Alert Reader architecture</title>
<desc id="desc">{copy['desc']}</desc>
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
<g transform="translate(82 66) scale(.13)">{LOGO_MARK}</g>
<text x="168" y="94" fill="#ffffff" font-family="{font}" font-size="34" font-weight="850">Scholar Alert Reader</text>
<text x="168" y="128" fill="#cdece8" font-family="{font}" font-size="20" font-weight="600">{copy['subtitle']}</text>
<text x="835" y="92" fill="#ffffff" font-family="{font}" font-size="17" font-weight="750">{copy['right1']}</text>
<text x="835" y="123" fill="#cdece8" font-family="{font}" font-size="14">{copy['right2']}</text>

<g font-family="{font}">
  <rect x="62" y="196" width="302" height="360" rx="24" fill="url(#panel)" stroke="#d8e0ea" filter="url(#shadow)"/>
  <text x="92" y="246" fill="#0f172a" font-size="25" font-weight="850">{copy['source_title']}</text>
  <text x="92" y="276" fill="#64748b" font-size="16">{copy['source_subtitle']}</text>
  {source_rows_svg}

  <rect x="449" y="188" width="302" height="352" rx="28" fill="#ffffff" stroke="#2563eb" stroke-width="2.5" filter="url(#shadow)"/>
  <rect x="477" y="216" width="246" height="70" rx="18" fill="#eff6ff"/>
  <text x="508" y="246" fill="#1e3a8a" font-size="18" font-weight="800">{copy['triage_title']}</text>
  <text x="508" y="270" fill="#475569" font-size="14">{copy['triage_subtitle']}</text>
  <g font-size="{14 if locale == 'en' else 15}" font-weight="760">
    {triage_rows_svg}
  </g>
  <path d="M536 457h128" stroke="#94a3b8" stroke-width="2.5" stroke-linecap="round"/>
  <circle cx="536" cy="457" r="5" fill="#2563eb"/><circle cx="664" cy="457" r="5" fill="#10b981"/>
  <text x="491" y="492" fill="#0f172a" font-size="{16 if locale == 'en' else 17}" font-weight="800">{copy['profile']}</text>
  <text x="491" y="518" fill="#64748b" font-size="14">{copy['profile_subtitle']}</text>

  <rect x="836" y="205" width="302" height="318" rx="24" fill="url(#panel)" stroke="#d8e0ea" filter="url(#shadow)"/>
  <text x="866" y="246" fill="#0f172a" font-size="25" font-weight="850">{copy['kb_title']}</text>
  <text x="866" y="276" fill="#64748b" font-size="16">{copy['kb_subtitle']}</text>
  <g font-size="{15 if locale == 'en' else 16}" font-weight="800">
    {kb_rows_svg}
  </g>
</g>

<g stroke="#64748b" stroke-width="4" fill="none" marker-end="url(#arrow)">
  <path d="M364 364 C398 364 412 364 449 364"/>
  <path d="M751 364 C790 364 800 364 836 364"/>
</g>
<g font-family="{font}">
  <rect x="190" y="570" width="820" height="56" rx="18" fill="#ffffff" stroke="#d8e0ea"/>
  <text x="224" y="604" fill="#475569" font-size="{16 if locale == 'en' else 17}" font-weight="650">{copy['footer']}</text>
  <text x="1035" y="606" fill="#64748b" font-size="15" font-weight="650">{copy['author']}</text>
</g>
</svg>
"""


def social_card_svg(locale: str) -> str:
    if locale == "zh":
        desc = "Scholar Alert Reader 中文社交分享图。"
        subtitle_lines = [
            "从邮件、网页来源、arXiv 和 Zotero 导出中，",
            "筛出真正值得读的论文。",
        ]
        badges = [("多来源", 138, 174, "#dbeafe", "#1d4ed8", 178), ("排序", 340, 168, "#dcfce7", "#047857", 398), ("反馈", 536, 196, "#ede9fe", "#6d28d9", 598), ("笔记引用", 760, 252, "#fef3c7", "#92400e", 832)]
        footer = "每日或手动推送 · 本地优先 · 可接 Obsidian / Zotero"
        author = "作者：Xin Liu · RunningXinLiu"
        font = "PingFang SC, Inter, Arial, sans-serif"
    else:
        desc = "A social sharing card for Scholar Alert Reader."
        subtitle_lines = [
            "Rank papers from email, web pages, feeds, arXiv,",
            "and your own research profile.",
        ]
        badges = [("Sources", 138, 174, "#dbeafe", "#1d4ed8", 174), ("Rank", 340, 168, "#dcfce7", "#047857", 382), ("Feedback", 536, 196, "#ede9fe", "#6d28d9", 574), ("Zotero + Notes", 760, 252, "#fef3c7", "#92400e", 792)]
        footer = "Daily or manual digests · Local-first · Obsidian/Zotero ready"
        author = "Created by Xin Liu · RunningXinLiu"
        font = "Inter, Arial, sans-serif"
    subtitle_svg = "\n".join(
        f'<text x="136" y="{235 + index * 37}" fill="#475569" font-family="{font}" font-size="27">{line}</text>'
        for index, line in enumerate(subtitle_lines)
    )
    badge_svg = "\n  ".join(
        f'<rect x="{x}" y="318" width="{width}" height="68" rx="18" fill="{fill}"/><text x="{tx}" y="361" fill="{color}">{label}</text>'
        for label, x, width, fill, color, tx in badges
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-labelledby="title desc">
<title id="title">Scholar Alert Reader social card</title>
<desc id="desc">{desc}</desc>
<rect width="1200" height="630" fill="#0f172a"/>
<circle cx="1010" cy="90" r="180" fill="#1d4ed8" opacity=".28"/><circle cx="170" cy="530" r="220" fill="#10b981" opacity=".20"/>
<rect x="80" y="78" width="1040" height="474" rx="34" fill="#f8fafc"/>
<g transform="translate(132 124) scale(.15)">{LOGO_MARK}</g>
<text x="230" y="180" fill="#111827" font-family="{font}" font-size="64" font-weight="850">Scholar Alert Reader</text>
{subtitle_svg}
<g font-family="{font}" font-weight="800" font-size="24">
  {badge_svg}
</g>
<text x="138" y="456" fill="#111827" font-family="{font}" font-size="30" font-weight="750">{footer}</text>
<text x="138" y="506" fill="#64748b" font-family="{font}" font-size="22" font-weight="650">{author}</text>
</svg>
"""


def svg_assets() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    english_architecture = architecture_svg("en")
    chinese_architecture = architecture_svg("zh")
    english_social = social_card_svg("en")
    chinese_social = social_card_svg("zh")
    assets = {
        "logo.svg": logo_svg(),
        "architecture.svg": english_architecture,
        "architecture.en.svg": english_architecture,
        "architecture.zh.svg": chinese_architecture,
        "architecture-showcase.svg": english_architecture,
        "architecture-showcase.en.svg": english_architecture,
        "architecture-showcase.zh.svg": chinese_architecture,
        "social-card.svg": english_social,
        "social-card.en.svg": english_social,
        "social-card.zh.svg": chinese_social,
    }
    for filename, content in assets.items():
        (ASSET_DIR / filename).write_text(content, encoding="utf-8")


def png_assets() -> None:
    sips = shutil.which("sips")
    if not sips:
        return
    names = [
        "architecture",
        "architecture.en",
        "architecture.zh",
        "architecture-showcase",
        "architecture-showcase.en",
        "architecture-showcase.zh",
        "social-card",
        "social-card.en",
        "social-card.zh",
        "logo",
    ]
    for name in names:
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


def write_gif(
    path: Path,
    frames: list[bytearray],
    width: int,
    height: int,
    delay_cs: int = 100,
    palette: list[tuple[int, int, int]] | None = None,
) -> None:
    data = bytearray(b"GIF89a")
    data.extend(width.to_bytes(2, "little"))
    data.extend(height.to_bytes(2, "little"))
    data.extend(bytes([0xF7, 0, 0]))
    colors = list((palette or RGB)[:256])
    colors.extend([(0, 0, 0)] * (256 - len(colors)))
    for r, g, b in colors:
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


def paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def read_png_rgb(path: Path) -> tuple[int, int, list[tuple[int, int, int]]]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not a PNG file: {path}")
    offset = 8
    width = height = bit_depth = color_type = interlace = 0
    idat = bytearray()
    while offset < len(data):
        size = int.from_bytes(data[offset : offset + 4], "big")
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + size]
        offset += 12 + size
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", chunk_data)
        elif chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            break
    if bit_depth != 8 or interlace != 0 or color_type not in {0, 2, 6}:
        raise ValueError(f"Unsupported PNG format in {path}: bit_depth={bit_depth}, color_type={color_type}, interlace={interlace}")
    channels = {0: 1, 2: 3, 6: 4}[color_type]
    row_bytes = width * channels
    raw = zlib.decompress(bytes(idat))
    rows: list[bytearray] = []
    pos = 0
    prev = bytearray(row_bytes)
    for _ in range(height):
        filter_type = raw[pos]
        pos += 1
        row = bytearray(raw[pos : pos + row_bytes])
        pos += row_bytes
        for i in range(row_bytes):
            left = row[i - channels] if i >= channels else 0
            up = prev[i]
            upper_left = prev[i - channels] if i >= channels else 0
            if filter_type == 1:
                row[i] = (row[i] + left) & 0xFF
            elif filter_type == 2:
                row[i] = (row[i] + up) & 0xFF
            elif filter_type == 3:
                row[i] = (row[i] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                row[i] = (row[i] + paeth(left, up, upper_left)) & 0xFF
            elif filter_type != 0:
                raise ValueError(f"Unsupported PNG filter {filter_type} in {path}")
        rows.append(row)
        prev = row

    pixels: list[tuple[int, int, int]] = []
    for row in rows:
        for i in range(0, row_bytes, channels):
            if color_type == 0:
                value = row[i]
                pixels.append((value, value, value))
            elif color_type == 2:
                pixels.append((row[i], row[i + 1], row[i + 2]))
            else:
                r, g, b, a = row[i], row[i + 1], row[i + 2], row[i + 3]
                if a < 255:
                    r = (r * a + 255 * (255 - a)) // 255
                    g = (g * a + 255 * (255 - a)) // 255
                    b = (b * a + 255 * (255 - a)) // 255
                pixels.append((r, g, b))
    return width, height, pixels


def quantize_color(color: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(min(255, max(0, round(channel / 17) * 17)) for channel in color)


def gif_palette(pixel_frames: list[list[tuple[int, int, int]]]) -> list[tuple[int, int, int]]:
    seeds = [
        (248, 250, 252),
        (255, 255, 255),
        (15, 23, 42),
        (17, 24, 39),
        (71, 85, 105),
        (100, 116, 139),
        (37, 99, 235),
        (219, 234, 254),
        (5, 150, 105),
        (209, 250, 229),
        (217, 119, 6),
        (254, 243, 199),
        (15, 118, 110),
        (205, 236, 232),
    ]
    counts: Counter[tuple[int, int, int]] = Counter()
    for pixels in pixel_frames:
        counts.update(quantize_color(pixel) for pixel in pixels[::3])
    palette = list(dict.fromkeys(seeds))
    for color, _ in counts.most_common():
        if color not in palette:
            palette.append(color)
        if len(palette) >= 256:
            break
    return palette[:256]


def indexed_frame(pixels: list[tuple[int, int, int]], palette: list[tuple[int, int, int]]) -> bytearray:
    cache: dict[tuple[int, int, int], int] = {}
    indexes = bytearray()
    for pixel in pixels:
        color = quantize_color(pixel)
        cached = cache.get(color)
        if cached is None:
            cached = min(
                range(len(palette)),
                key=lambda i: (
                    (palette[i][0] - color[0]) ** 2
                    + (palette[i][1] - color[1]) ** 2
                    + (palette[i][2] - color[2]) ** 2
                ),
            )
            cache[color] = cached
        indexes.append(cached)
    return indexes


def pixel_workflow_gif(path: Path) -> None:
    width, height = 800, 450
    frames: list[bytearray] = []
    steps = [
        ("PAPER SOURCE INBOX", "GMAIL MAIL MBOX WEB FEEDS", ["GMAIL", "BIBTEX", "WEB"], "NEW PAPERS"),
        ("PROFILE RANKING", "KEYWORDS METHODS AUTHORS FILTERS", ["EXTRACT", "DEDUPE", "SCORE"], "READING QUEUE"),
        ("FEEDBACK LOOP", "INTERESTED ARCHIVE MORE LIKE THIS", ["INTERESTED", "ARCHIVE", "FEEDBACK"], "BETTER NEXT RUN"),
        ("RESEARCH MEMORY", "FOUNDATION DEEP READS MAPS QA", ["DIGEST", "FOUNDATION", "DEEP READ"], "COPILOT"),
        ("WORKFLOW EXPORTS", "HTML MARKDOWN OBSIDIAN ZOTERO", ["HTML", "OBSIDIAN", "ZOTERO"], "YOUR WORKFLOW"),
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
            arrow(buf, width, 274, y + 29, 332, y + 29, PALETTE["line"])
        card(buf, width, 344, 196, 150, 118, PALETTE["white"], "TRIAGE", PALETTE["ink"])
        arrow(buf, width, 506, 255, 558, 255, PALETTE["line"])
        card(buf, width, 574, 196, 176, 118, PALETTE["blue2"], right_label, PALETTE["blue"])
        text(buf, width, 604, 340, "OUTPUT", PALETTE["muted"], 2)
        text(buf, width, 642, 402, "BY XIN LIU", PALETTE["muted"], 2)
        frames.append(buf)
    write_gif(path, frames, width, height, delay_cs=120)


def output_label_lines(label: str, locale: str) -> list[str]:
    if locale == "zh" or len(label) <= 18:
        return [label]
    parts = label.split()
    if len(parts) <= 1:
        return [label]
    split_at = max(1, len(parts) // 2)
    return [" ".join(parts[:split_at]), " ".join(parts[split_at:])]


def workflow_frame_svg(
    title: str,
    subtitle: str,
    left_labels: list[str],
    right_label: str,
    footer: str,
    locale: str,
    step_number: int = 1,
    total_steps: int = 5,
) -> str:
    font = "PingFang SC, Inter, Arial, sans-serif" if locale == "zh" else "Inter, Arial, sans-serif"
    raw_right_label = right_label
    title = escape(title)
    subtitle = escape(subtitle)
    footer = escape(footer)
    input_caption = "输入" if locale == "zh" else "Input"
    core_caption = "分诊核心" if locale == "zh" else "Reader Core"
    output_caption = "输出" if locale == "zh" else "Result"
    ready_caption = "可继续阅读" if locale == "zh" else "ready for review"
    step_badge = f"{step_number}/{total_steps}" if locale == "zh" else f"{step_number:02d}/{total_steps:02d}"
    progress_dots = "\n".join(
        f'<circle cx="{606 + index * 22}" cy="66" r="4.5" fill="{"#5eead4" if index + 1 == step_number else "#94a3b8"}" opacity="{"1" if index + 1 == step_number else ".62"}"/>'
        for index in range(total_steps)
    )
    output_lines = output_label_lines(raw_right_label, locale)
    if len(output_lines) == 1:
        output_text = (
            f'<text x="552" y="248" fill="#1e3a8a" font-size="{28 if locale == "zh" else 24}" '
            f'font-weight="850">{escape(output_lines[0])}</text>'
        )
    else:
        output_text = "\n  ".join(
            f'<text x="552" y="{238 + index * 30}" fill="#1e3a8a" font-size="22" font-weight="850">{escape(line)}</text>'
            for index, line in enumerate(output_lines)
        )
    left_svg = []
    fills = [("#dbeafe", "#1d4ed8"), ("#dcfce7", "#047857"), ("#fef3c7", "#92400e")]
    for index, (label, (fill, color)) in enumerate(zip(left_labels, fills)):
        label = escape(label)
        y = 204 + index * 46
        left_svg.append(
            f'<rect x="78" y="{y}" width="168" height="34" rx="10" fill="{fill}" stroke="#cbd5e1"/>'
            f'<text x="96" y="{y + 23}" fill="{color}" font-size="15" font-weight="800">{label}</text>'
        )
    left_content = "\n  ".join(left_svg)
    if locale == "zh":
        core_chips = [("抽取", 334, 214), ("去重", 406, 214), ("排序", 334, 260), ("反馈", 406, 260)]
        chip_font = 14
    else:
        core_chips = [("Extract", 334, 214), ("Dedupe", 406, 214), ("Rank", 334, 260), ("Feedback", 406, 260)]
        chip_font = 11
    core_svg = "\n  ".join(
        f'<rect x="{x}" y="{y}" width="64" height="32" rx="10" fill="#ffffff" stroke="#ccfbf1"/>'
        f'<text x="{x + 10}" y="{y + 21}" fill="#0f766e" font-size="{chip_font}" font-weight="800">{label}</text>'
        for label, x, y in core_chips
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450" viewBox="0 0 800 450">
<defs>
  <linearGradient id="top" x1="0" x2="1">
    <stop offset="0" stop-color="#0f172a"/>
    <stop offset="1" stop-color="#115e59"/>
  </linearGradient>
  <filter id="shadow" x="-20%" y="-25%" width="140%" height="150%">
    <feDropShadow dx="0" dy="10" stdDeviation="10" flood-color="#0f172a" flood-opacity=".12"/>
  </filter>
</defs>
<rect width="800" height="450" fill="#f8fafc"/>
<rect x="0" y="0" width="800" height="96" fill="url(#top)"/>
<text x="34" y="38" fill="#ffffff" font-family="{font}" font-size="{30 if locale == 'en' else 28}" font-weight="850">{title}</text>
<text x="36" y="67" fill="#cdece8" font-family="{font}" font-size="{16 if locale == 'en' else 15}" font-weight="650">{subtitle}</text>
<rect x="678" y="23" width="74" height="32" rx="16" fill="#ffffff" opacity=".14"/>
<text x="695" y="44" fill="#ffffff" font-family="{font}" font-size="14" font-weight="850">{step_badge}</text>
{progress_dots}
<rect x="34" y="118" width="732" height="270" rx="30" fill="#ffffff" stroke="#d8e0ea" filter="url(#shadow)"/>
<g font-family="{font}">
  <rect x="58" y="150" width="210" height="200" rx="22" fill="#f8fafc" stroke="#d8e0ea"/>
  <text x="78" y="184" fill="#334155" font-size="15" font-weight="850">{input_caption}</text>
  {left_content}
  <path d="M284 250 H310" stroke="#94a3b8" stroke-width="5" stroke-linecap="round"/>
  <path d="M310 240 L330 250 L310 260" fill="#94a3b8"/>
  <rect x="328" y="150" width="166" height="200" rx="24" fill="#f0fdfa" stroke="#99f6e4"/>
  <text x="360" y="184" fill="#134e4a" font-size="{17 if locale == 'en' else 19}" font-weight="850">{core_caption}</text>
  {core_svg}
  <path d="M510 250 H530" stroke="#94a3b8" stroke-width="5" stroke-linecap="round"/>
  <path d="M530 240 L550 250 L530 260" fill="#94a3b8"/>
  <rect x="548" y="150" width="194" height="200" rx="24" fill="#eff6ff" stroke="#bfdbfe"/>
  <text x="552" y="184" fill="#2563eb" font-size="{15 if locale == 'en' else 16}" font-weight="850">{output_caption}</text>
  {output_text}
  <rect x="552" y="292" width="136" height="30" rx="15" fill="#ffffff" stroke="#bfdbfe"/>
  <text x="572" y="312" fill="#64748b" font-size="{12 if locale == 'en' else 13}" font-weight="800">{ready_caption}</text>
  <text x="38" y="420" fill="#64748b" font-size="16" font-weight="700">{footer}</text>
  <text x="650" y="420" fill="#64748b" font-size="14" font-weight="700">Xin Liu</text>
</g>
</svg>
"""


def workflow_gif_from_svg(path: Path, steps: list[tuple[str, str, list[str], str]], footer: str, locale: str) -> bool:
    sips = shutil.which("sips")
    if not sips:
        return False
    pixel_frames: list[list[tuple[int, int, int]]] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        total_steps = len(steps)
        for index, (title, subtitle, left_labels, right_label) in enumerate(steps):
            svg_path = tmp_path / f"frame_{index:02d}.svg"
            png_path = tmp_path / f"frame_{index:02d}.png"
            svg_path.write_text(
                workflow_frame_svg(
                    title,
                    subtitle,
                    left_labels,
                    right_label,
                    footer,
                    locale,
                    step_number=index + 1,
                    total_steps=total_steps,
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [sips, "-s", "format", "png", str(svg_path), "--out", str(png_path)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            frame_width, frame_height, pixels = read_png_rgb(png_path)
            if index == 0:
                width, height = frame_width, frame_height
            elif (frame_width, frame_height) != (width, height):
                raise ValueError("Workflow GIF frames do not have consistent dimensions")
            pixel_frames.append(pixels)
    palette = gif_palette(pixel_frames)
    indexed_frames = [indexed_frame(pixels, palette) for pixels in pixel_frames]
    write_gif(path, indexed_frames, width, height, delay_cs=125, palette=palette)
    return path.exists()


def gif_assets() -> None:
    english_steps = [
        ("Connect paper sources", "Gmail, Apple Mail, mbox, BibTeX/RIS, web pages, RSS, arXiv", ["Email alerts", "Bibliography", "Web / arXiv"], "New papers"),
        ("Rank by your profile", "Keywords, methods, regions, authors, exclusions, temporary boosts", ["Extract", "Dedupe", "Score"], "Ranked queue"),
        ("Learn from feedback", "Interested, archive, more-like-this, less-like-this", ["Interested", "Archive", "Feedback"], "Smarter ranking"),
        ("Build research memory", "Foundation, deep reads, Q&A, comparisons, maps, advice", ["Digest", "Foundation", "Deep reads"], "Research memory"),
        ("Export to your tools", "HTML digest, Markdown, CSV/JSON, Obsidian notes, Zotero files", ["HTML", "Obsidian", "Zotero"], "Notes + citations"),
    ]
    chinese_steps = [
        ("接入你的论文来源", "Gmail、Apple Mail、mbox、BibTeX/RIS、学术网页、RSS 和 arXiv", ["邮件提醒", "文献导出", "网页 / arXiv"], "新论文"),
        ("按研究方向排序", "关键词、方法、地区、作者、排除词和临时关注点", ["抽取", "去重", "打分"], "排序队列"),
        ("用反馈调整推荐", "感兴趣、忽略、更多类似、减少类似", ["感兴趣", "忽略", "反馈"], "推荐更准"),
        ("沉淀个人知识库", "文献底座、深读、问答、对比、图谱和建议", ["每日简报", "文献底座", "深读报告"], "研究记忆"),
        ("接到你的工作流", "HTML digest、Markdown、CSV/JSON、Obsidian 笔记、Zotero 文件", ["HTML", "Obsidian", "Zotero"], "笔记引用"),
    ]
    english_path = ASSET_DIR / "workflow.en.gif"
    if not workflow_gif_from_svg(
        english_path,
        english_steps,
        "Daily or manual digests · local-first · Obsidian/Zotero ready",
        "en",
    ):
        pixel_workflow_gif(english_path)
    shutil.copyfile(english_path, ASSET_DIR / "workflow.gif")
    workflow_gif_from_svg(
        ASSET_DIR / "workflow.zh.gif",
        chinese_steps,
        "每日或手动推送 · 本地优先 · 可接 Obsidian / Zotero",
        "zh",
    )


def main() -> int:
    svg_assets()
    png_assets()
    gif_assets()
    print(f"Generated assets in {ASSET_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
