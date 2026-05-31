#!/usr/bin/env python3
"""Generate sanitized product screenshots for README and marketing."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_DIR = ROOT / "docs" / "screenshots"
WIDTH = 1440
HEIGHT = 960

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - optional local marketing dependency
    Image = None
    ImageDraw = None
    ImageFont = None


def chrome_path() -> str | None:
    candidates = [
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chrome"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


def page(title: str, subtitle: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{
  --bg: #f6f8fb;
  --ink: #111827;
  --muted: #64748b;
  --line: #d8e0ea;
  --panel: #ffffff;
  --blue: #2563eb;
  --blue-soft: #dbeafe;
  --green: #059669;
  --green-soft: #d1fae5;
  --amber: #b45309;
  --amber-soft: #fef3c7;
  --violet: #6d28d9;
  --violet-soft: #ede9fe;
  --red: #b91c1c;
  --red-soft: #fee2e2;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
  line-height: 1.45;
}}
.browser {{
  width: 1280px;
  height: 820px;
  margin: 44px auto;
  background: var(--panel);
  border: 1px solid #cfd8e3;
  border-radius: 18px;
  overflow: hidden;
  box-shadow: 0 28px 80px rgba(15, 23, 42, .18);
}}
.bar {{
  height: 50px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 18px;
  background: #eef2f7;
  border-bottom: 1px solid #d6dee9;
}}
.dot {{ width: 12px; height: 12px; border-radius: 50%; }}
.red {{ background: #ff5f57; }} .yellow {{ background: #ffbd2e; }} .green {{ background: #28c840; }}
.address {{
  flex: 1;
  height: 28px;
  margin-left: 12px;
  border-radius: 999px;
  background: #fff;
  color: #64748b;
  display: flex;
  align-items: center;
  padding: 0 14px;
  font-size: 13px;
}}
.content {{ height: 770px; overflow: hidden; background: var(--bg); }}
.hero {{
  background: #fff;
  border-bottom: 1px solid var(--line);
  padding: 26px 34px 22px;
}}
h1 {{ margin: 0 0 6px; font-size: 32px; letter-spacing: 0; }}
h2 {{ margin: 0 0 12px; font-size: 22px; letter-spacing: 0; }}
h3 {{ margin: 0 0 8px; font-size: 17px; letter-spacing: 0; }}
p {{ margin: 0 0 10px; }}
.subtitle {{ color: var(--muted); font-size: 17px; }}
.metrics {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }}
.metric, .pill {{
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #fff;
  color: #334155;
  padding: 8px 12px;
  font-weight: 650;
  font-size: 13px;
}}
.main {{ padding: 24px 34px; }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
.three {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 18px; }}
.panel {{
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 18px;
  min-width: 0;
}}
.paper {{
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 12px;
}}
.paper.featured {{ border-color: #34d399; box-shadow: inset 4px 0 0 #10b981; }}
.muted {{ color: var(--muted); }}
.tiny {{ color: var(--muted); font-size: 12px; }}
.badges {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0; }}
.badge {{
  border-radius: 999px;
  padding: 4px 8px;
  font-size: 12px;
  font-weight: 750;
  background: #eef2f7;
  color: #334155;
}}
.must {{ background: var(--green-soft); color: #047857; }}
.skim {{ background: var(--blue-soft); color: #1d4ed8; }}
.archive {{ background: var(--amber-soft); color: #92400e; }}
.deep {{ background: var(--violet-soft); color: var(--violet); }}
.button-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }}
.button {{
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
  padding: 8px 10px;
  font-size: 13px;
  font-weight: 650;
}}
.button.primary {{ background: #0f766e; color: #fff; border-color: #0f766e; }}
.button.danger {{ background: #fff7ed; color: #9a3412; border-color: #fed7aa; }}
.toolbar {{ display: grid; grid-template-columns: 1fr 180px; gap: 10px; margin-top: 16px; max-width: 760px; }}
.input {{ border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; color: #64748b; background: #fff; }}
.split {{ display: grid; grid-template-columns: 310px 1fr; gap: 18px; }}
.sidebar {{ background: #0f172a; color: #e5e7eb; border-radius: 12px; padding: 18px; min-height: 520px; }}
.tree {{ list-style: none; padding: 0; margin: 12px 0 0; }}
.tree li {{ padding: 7px 0; color: #cbd5e1; font-size: 14px; }}
.tree .active {{ color: #fff; font-weight: 800; }}
.panel .tree li {{ color: #475569; }}
.panel .tree .active {{ color: #111827; }}
.note-list {{ display: grid; gap: 12px; }}
.note {{ border: 1px solid var(--line); border-radius: 10px; background: #fff; padding: 14px; }}
.callout {{ background: #ecfeff; border: 1px solid #bae6fd; border-radius: 12px; padding: 14px; }}
.code {{ background: #0f172a; color: #e5e7eb; border-radius: 10px; padding: 14px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; white-space: pre-wrap; }}
.map {{ height: 430px; position: relative; background: linear-gradient(180deg, #fff, #f8fafc); border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }}
.node {{ position: absolute; border-radius: 999px; padding: 10px 14px; font-weight: 800; font-size: 13px; border: 1px solid var(--line); background: #fff; box-shadow: 0 10px 24px rgba(15,23,42,.08); }}
.line {{ position: absolute; height: 2px; background: #94a3b8; transform-origin: left center; opacity: .65; }}
.kpi {{ font-size: 34px; font-weight: 850; margin-bottom: 4px; }}
</style>
</head>
<body>
<div class="browser">
  <div class="bar">
    <div class="dot red"></div><div class="dot yellow"></div><div class="dot green"></div>
    <div class="address">localhost / Scholar Alert Reader</div>
  </div>
  <div class="content">
    <section class="hero">
      <h1>{title}</h1>
      <div class="subtitle">{subtitle}</div>
    </section>
    {body}
  </div>
</div>
</body>
</html>
"""


def digest() -> str:
    return page(
        "Daily Literature Digest",
        "Sanitized demo run across alerts, feeds, bibliography exports, and web sources",
        """
<main class="main">
  <div class="metrics">
    <div class="metric">Papers: 18</div><div class="metric">Must read: 4</div><div class="metric">Skim: 7</div>
    <div class="metric">Archived: 7</div><div class="metric">Sources: Gmail + RSS + arXiv</div>
  </div>
  <div class="grid" style="margin-top:22px">
    <section>
      <h2>Must read</h2>
      <article class="paper featured">
        <h3>Receiver function imaging beneath the eastern Tibetan Plateau</h3>
        <div class="badges"><span class="badge must">Must read</span><span class="badge">score 42</span><span class="badge deep">metadata-enriched</span><span class="badge">receiver function</span></div>
        <p class="muted">A. Researcher, B. Collaborator - Earth and Planetary Science Letters, 2026</p>
        <p>Constrains crustal anisotropy and Moho complexity using dense temporary arrays.</p>
      </article>
      <article class="paper">
        <h3>Ambient noise tomography of the Taiwan collision zone</h3>
        <div class="badges"><span class="badge must">Must read</span><span class="badge">score 38</span><span class="badge">tomography</span></div>
        <p class="muted">Journal of Geophysical Research, 2026</p>
      </article>
    </section>
    <section>
      <h2>Skim and archive</h2>
      <article class="paper">
        <h3>Benchmarking DAS arrays for near-surface velocity monitoring</h3>
        <div class="badges"><span class="badge skim">Skim</span><span class="badge">score 25</span><span class="badge">DAS</span></div>
        <p class="muted">Useful method reference, not central this week.</p>
      </article>
      <article class="paper">
        <h3>Generic earthquake prediction with black-box image models</h3>
        <div class="badges"><span class="badge archive">Archive</span><span class="badge">score 6</span></div>
        <p class="muted">Low methodological overlap with the profile.</p>
      </article>
    </section>
  </div>
</main>
""",
    )


def feedback_ui() -> str:
    return page(
        "Review Workspace",
        "Batch-save decisions, notes, reading status, and report requests",
        """
<main class="main">
  <div class="toolbar" style="grid-template-columns: 1fr 170px 170px">
    <div class="input">Search title, venue, abstract, term, source</div>
    <div class="input">Active queue</div>
    <div class="input">Must read</div>
  </div>
  <div style="margin-top:20px">
    <article class="paper featured" style="margin-bottom:16px">
      <h3>Total generalized variation regularization closes the gap between neural-field and classical tomography</h3>
      <div class="badges"><span class="badge">id 868e160</span><span class="badge must">Must read</span><span class="badge">score 61</span><span class="badge deep">metadata-enriched</span></div>
      <p class="muted">Computers &amp; Geosciences, 2026 · open paper · source workspace</p>
      <p>Full abstract is shown when available; Scholar snippets are marked when the source itself ends with an ellipsis.</p>
      <div class="three" style="gap:12px; margin-top:14px">
        <div>
          <h3>Decision</h3>
          <div class="input">Interested</div>
          <p class="tiny">Keep/archive decision.</p>
        </div>
        <div>
          <h3>Priority</h3>
          <div class="input">Must read</div>
          <p class="tiny">Manual tier override.</p>
        </div>
        <div>
          <h3>Reading status</h3>
          <div class="input">Reading</div>
          <p class="tiny">Progress state.</p>
        </div>
      </div>
      <div class="panel" style="margin-top:12px; padding:12px">
        <h3>Learning signal</h3>
        <div class="button-row"><span class="button primary">More like this</span><span class="button">Less like this</span><span class="button">Clear signal</span></div>
      </div>
      <div class="panel" style="margin-top:12px; padding:12px">
        <h3>Generate report on save</h3>
        <div class="button-row"><span class="button">Deep read</span><span class="button primary">Full review</span><span class="button">Workup</span><span class="button">Review pack</span></div>
      </div>
      <div class="input" style="margin-top:12px; height:56px">Personal note: useful regularizer comparison for neural-field inversion.</div>
    </article>
  </div>
  <div class="callout">
    Click many cards, then press <b>Save selected changes</b>. Saved feedback updates <b>feedback.json</b>, refreshes the retained library, and changes the next daily ranking.
  </div>
  <div class="button-row" style="justify-content:flex-end; margin-top:14px">
    <span class="button">Clear pending changes</span><span class="button primary">Save selected changes</span>
  </div>
</main>
""",
    )


def foundation_interested() -> str:
    return page(
        "Foundation and Interested Library",
        "Retained papers become a cumulative, queryable research memory",
        """
<main class="main split">
  <aside class="sidebar">
    <h2>Knowledge base</h2>
    <ul class="tree">
      <li class="active">foundation.md</li>
      <li class="active">interested.md</li>
      <li>daily_additions.md</li>
      <li>papers/p7a42.md</li>
      <li>directions/receiver-functions.md</li>
      <li>directions/ambient-noise.md</li>
      <li>weekly_review.md</li>
    </ul>
  </aside>
  <section class="note-list">
    <div class="note">
      <h2>Interested queue</h2>
      <p><b>Next deep reads:</b> receiver functions in Tibet, ambient noise tomography, DAS monitoring.</p>
      <div class="badges"><span class="badge must">4 must read</span><span class="badge deep">2 queued for deep read</span></div>
    </div>
    <div class="note">
      <h2>Foundation by direction</h2>
      <p><b>Receiver functions:</b> 18 retained papers, strong overlap with crustal anisotropy and Moho imaging.</p>
      <p><b>Ambient noise:</b> 12 retained papers, emerging methods for joint inversion and uncertainty.</p>
    </div>
    <div class="note">
      <h2>What stays out</h2>
      <p>Archived alert items remain in daily outputs and seen state, but do not enter the retained knowledge base by default.</p>
    </div>
  </section>
</main>
""",
    )


def deep_read() -> str:
    return page(
        "Evidence and Review Workflow",
        "Inspect what a selected-paper report can support before citing it",
        """
<main class="main">
  <div class="grid">
    <section class="panel">
      <h2>Selected paper</h2>
      <h3>Joint receiver-function and surface-wave constraints on plateau crust</h3>
      <p class="muted">Why it matters: connects two active directions in the retained library.</p>
      <div class="badges"><span class="badge must">Must read</span><span class="badge deep">full-text-backed</span><span class="badge">method bridge</span></div>
    </section>
    <section class="panel">
      <h2>Evidence status</h2>
      <p><b>Can support:</b> closer workup, section coverage, figure/table caption inspection, and assistant-ready review pack.</p>
      <p><b>Boundary:</b> final citation claims still require checking the original PDF.</p>
    </section>
  </div>
  <div class="three" style="margin-top:18px">
    <section class="panel"><div class="kpi">1</div><p class="muted">local text cache</p></section>
    <section class="panel"><div class="kpi">8</div><p class="muted">figure/table captions</p></section>
    <section class="panel"><div class="kpi">5</div><p class="muted">foundation links</p></section>
  </div>
  <section class="panel" style="margin-top:18px">
    <h2>Next commands</h2>
    <div class="code">./evidence_reader.sh --paper-id p7a42
./review_workflow.sh --paper-id p7a42 --open
./review_paper.sh --paper-id p7a42</div>
  </section>
</main>
""",
    )


def research_map() -> str:
    return page(
        "Research Map and Advice",
        "Cluster retained papers, expose gaps, and turn alerts into research strategy",
        """
<main class="main">
  <div class="grid">
    <section class="map">
      <div class="line" style="left:235px; top:210px; width:210px; transform: rotate(-20deg)"></div>
      <div class="line" style="left:450px; top:160px; width:150px; transform: rotate(46deg)"></div>
      <div class="line" style="left:248px; top:230px; width:205px; transform: rotate(31deg)"></div>
      <div class="node" style="left:70px; top:190px; background:#dbeafe; color:#1d4ed8">Receiver functions</div>
      <div class="node" style="left:390px; top:105px; background:#d1fae5; color:#047857">Ambient noise</div>
      <div class="node" style="left:405px; top:265px; background:#ede9fe; color:#6d28d9">Joint inversion</div>
      <div class="node" style="left:310px; top:340px; background:#fef3c7; color:#92400e">DAS monitoring</div>
    </section>
    <section class="panel">
      <h2>Advice</h2>
      <p><b>Opportunity:</b> connect receiver-function discontinuity constraints with ambient-noise velocity models.</p>
      <p><b>Gap:</b> few retained papers quantify uncertainty consistently across methods.</p>
      <p><b>Next search:</b> add alerts for "joint inversion uncertainty", "crustal anisotropy", and target regions.</p>
      <div class="badges"><span class="badge deep">Q&amp;A ready</span><span class="badge must">weekly review</span></div>
    </section>
  </div>
</main>
""",
    )


def integrations() -> str:
    return page(
        "Clean Obsidian and Zotero Handoff",
        "Keep the machine workspace local; export only selected notes and citation files",
        """
<main class="main grid">
  <section class="panel">
    <h2>Obsidian clean export</h2>
    <ul class="tree" style="margin-top:0">
      <li class="active">01_Literatures/10_Scholar_Alert_Reader</li>
      <li class="active">01_Papers / selected-paper.md</li>
      <li>type: paper</li>
      <li>generated: true</li>
      <li>source_tool: scholar-alert-reader</li>
      <li>obsidian_import: clean</li>
      <li>No automatic [[wikilinks]]</li>
    </ul>
    <div class="callout" style="margin-top:16px">Dashboard, search index, runs, analysis reports, and full workspace files stay outside the Obsidian graph by default.</div>
  </section>
  <section class="panel">
    <h2>Zotero-ready Must-read files</h2>
    <div class="code">@article{{p7a42,
  title = {{Neural-field travel-time tomography}},
  author = {{A. Researcher and B. Collaborator}},
  year = {{2026}},
  journal = {{Computers &amp; Geosciences}},
  keywords = {{tomography, uncertainty, method}}
}}</div>
    <div class="badges" style="margin-top:14px"><span class="badge">scholar_alert_reader.bib</span><span class="badge">scholar_alert_reader.ris</span><span class="badge">filtered tags</span></div>
    <p class="muted" style="margin-top:14px">Internal learning signals such as similar:, user:, feedback, and semantic are hidden from downstream tags.</p>
  </section>
</main>
""",
    )


SCREENSHOTS = [
    ("01-daily-digest", "Daily digest dashboard", digest),
    ("02-feedback-triage", "Review Workspace for batch feedback and notes", feedback_ui),
    ("03-foundation-interested", "Foundation and interested knowledge base", foundation_interested),
    ("04-deep-read-copilot", "Evidence-aware selected-paper review workflow", deep_read),
    ("05-research-map-advice", "Research map and advice", research_map),
    ("06-obsidian-zotero", "Clean Obsidian and Zotero handoff", integrations),
]


def write_index() -> None:
    lines = [
        "# Marketing Screenshots",
        "",
        "Sanitized demo screenshots for README, GitHub sharing, and social posts.",
        "They do not contain personal mailbox data, OAuth tokens, or a real knowledge base.",
        "Images are linked instead of embedded so GitHub pages stay readable on networks that block raw image delivery.",
        "",
        "| Screenshot | File |",
        "|---|---|",
    ]
    for slug, caption, _ in SCREENSHOTS:
        lines.append(f"| {caption} | [{slug}.png]({slug}.png) |")
    (SCREENSHOT_DIR / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_with_chrome(html_file: Path, out_file: Path, chrome: str) -> None:
    with tempfile.TemporaryDirectory() as profile:
        base_args = [
            chrome,
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-dev-shm-usage",
            f"--user-data-dir={profile}",
            f"--window-size={WIDTH},{HEIGHT}",
            f"--screenshot={out_file}",
            html_file.as_uri(),
        ]
        last_error: subprocess.CalledProcessError | None = None
        for headless_flag in ["--headless=new", "--headless"]:
            try:
                subprocess.run(
                    [base_args[0], headless_flag, *base_args[1:]],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except subprocess.CalledProcessError as exc:
                last_error = exc
        if last_error:
            raise last_error


@lru_cache(maxsize=None)
def pil_font(size: int, bold: bool = False) -> object:
    if ImageFont is None:
        raise RuntimeError("Pillow is not available")
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Helvetica.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default(size=size)


def draw_text(
    draw: object,
    xy: tuple[int, int],
    text_value: str,
    size: int,
    fill: str,
    bold: bool = False,
) -> None:
    draw.text(xy, text_value, font=pil_font(size, bold=bold), fill=fill)


def text_size(draw: object, text_value: str, size: int, bold: bool = False) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text_value, font=pil_font(size, bold=bold))
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def wrap_text(draw: object, text_value: str, max_width: int, size: int, bold: bool = False) -> list[str]:
    words = text_value.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or text_size(draw, candidate, size, bold=bold)[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def rounded(draw: object, xy: tuple[int, int, int, int], radius: int, fill: str, outline: str | None = None, width: int = 1) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def pill(draw: object, x: int, y: int, label: str, fill: str = "#eef2f7", fg: str = "#334155") -> int:
    w, h = text_size(draw, label, 17, bold=True)
    width = w + 26
    rounded(draw, (x, y, x + width, y + 34), 17, fill)
    draw_text(draw, (x + 13, y + 8), label, 17, fg, bold=True)
    return width


def browser_canvas(title: str, subtitle: str) -> tuple[object, object]:
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow is not available")
    img = Image.new("RGB", (WIDTH, HEIGHT), "#f6f8fb")
    draw = ImageDraw.Draw(img)
    rounded(draw, (80, 44, 1360, 862), 18, "#ffffff", "#cfd8e3")
    draw.rectangle((80, 94, 1360, 220), fill="#ffffff", outline="#d8e0ea")
    rounded(draw, (171, 56, 1342, 84), 14, "#ffffff")
    for x, color in [(99, "#ff5f57"), (119, "#ffbd2e"), (139, "#28c840")]:
        draw.ellipse((x, 64, x + 12, 76), fill=color)
    draw_text(draw, (186, 63), "localhost / Scholar Alert Reader", 14, "#475569")
    draw_text(draw, (115, 132), title, 36, "#111827", bold=True)
    draw_text(draw, (115, 179), subtitle, 19, "#526684")
    return img, draw


def draw_card(draw: object, x: int, y: int, w: int, h: int, title: str, body: list[str], accent: str | None = None) -> None:
    rounded(draw, (x, y, x + w, y + h), 12, "#ffffff", "#d8e0ea")
    if accent:
        draw.rounded_rectangle((x, y, x + 6, y + h), radius=6, fill=accent)
    draw_text(draw, (x + 18, y + 18), title, 22, "#111827", bold=True)
    yy = y + 58
    for line in body:
        for wrapped in wrap_text(draw, line, w - 36, 19):
            draw_text(draw, (x + 18, yy), wrapped, 19, "#475569")
            yy += 28
        yy += 5


def draw_pillow_digest(out_file: Path) -> None:
    img, draw = browser_canvas("Daily Literature Digest", "Ranked papers with evidence levels, source metadata, and next-reading priority")
    x, y = 115, 246
    for label, color, fg in [
        ("Papers 18", "#eef2f7", "#334155"),
        ("Must read 4", "#d1fae5", "#047857"),
        ("Skim 7", "#dbeafe", "#1d4ed8"),
        ("Archive 7", "#fef3c7", "#92400e"),
        ("Gmail + RSS + arXiv", "#ede9fe", "#6d28d9"),
    ]:
        x += pill(draw, x, y, label, color, fg) + 10
    draw_card(
        draw,
        115,
        315,
        590,
        220,
        "Receiver function imaging beneath the eastern Tibetan Plateau",
        [
            "Earth and Planetary Science Letters, 2026",
            "Must read · score 42 · metadata-enriched",
            "Constrains crustal anisotropy and Moho complexity using dense temporary arrays.",
        ],
        accent="#10b981",
    )
    draw_card(
        draw,
        735,
        315,
        590,
        220,
        "Ambient noise tomography of the Taiwan collision zone",
        [
            "Journal of Geophysical Research, 2026",
            "Must read · score 38 · PDF-link-ready",
            "Useful for joint inversion and uncertainty-aware velocity models.",
        ],
    )
    draw_card(
        draw,
        115,
        570,
        590,
        185,
        "Why selected",
        [
            "Topic fit + method fit + domain/region fit are shown separately.",
            "Evidence badges make metadata-only triage visibly different from full-text-backed analysis.",
        ],
    )
    draw_card(
        draw,
        735,
        570,
        590,
        185,
        "Daily behavior",
        [
            "Foundation remembers what has already been seen.",
            "Daily digest focuses on new/unread candidates after the first run.",
        ],
    )
    img.save(out_file)


def draw_pillow_review(out_file: Path) -> None:
    img, draw = browser_canvas("Review Workspace", "Batch-save decisions, notes, reading status, and report requests")
    pill(draw, 115, 248, "Active queue", "#dbeafe", "#1d4ed8")
    pill(draw, 250, 248, "Must read", "#d1fae5", "#047857")
    pill(draw, 370, 248, "Search title / venue / abstract", "#eef2f7", "#334155")
    draw_card(
        draw,
        115,
        310,
        1210,
        345,
        "Total generalized variation regularization closes the gap between neural-field and classical tomography",
        [
            "Computers & Geosciences, 2026 · Open paper · Source workspace",
            "Full abstract is shown when available; truncated Scholar snippets are labeled as source-limited.",
            "Decision: Interested     Priority: Must read     Reading status: Reading",
            "Learning signal: More like this     Report on save: Full review",
            "Personal note: useful regularizer comparison for neural-field inversion.",
        ],
        accent="#0f766e",
    )
    for x, label, fill, fg in [
        (150, "Interested", "#d1fae5", "#047857"),
        (285, "Must read", "#dbeafe", "#1d4ed8"),
        (410, "More like this", "#ecfeff", "#0f766e"),
        (570, "Full review", "#ede9fe", "#6d28d9"),
        (710, "Fetch abstract", "#fef3c7", "#92400e"),
    ]:
        pill(draw, x, 565, label, fill, fg)
    rounded(draw, (858, 704, 1070, 756), 9, "#ffffff", "#d8e0ea")
    draw_text(draw, (880, 720), "Clear pending", 19, "#334155", bold=True)
    rounded(draw, (1090, 704, 1325, 756), 9, "#0f766e")
    draw_text(draw, (1124, 720), "Save changes", 19, "#ffffff", bold=True)
    rounded(draw, (115, 690, 800, 790), 12, "#ecfeff", "#bae6fd")
    draw_text(draw, (140, 715), "One save writes feedback.json, refreshes the retained library,", 20, "#0f172a")
    draw_text(draw, (140, 746), "and changes the next ranking run.", 20, "#0f172a")
    img.save(out_file)


def draw_pillow_library(out_file: Path) -> None:
    img, draw = browser_canvas("Foundation and Interested Library", "Retained papers become a cumulative, queryable research memory")
    rounded(draw, (115, 250, 400, 770), 12, "#0f172a")
    for i, item in enumerate(["foundation.md", "interested.md", "daily_additions.md", "papers/*.md", "directions/*.md", "weekly_review.md"]):
        draw_text(draw, (145, 300 + i * 58), item, 21, "#ffffff" if i < 2 else "#cbd5e1", bold=i < 2)
    draw_card(draw, 430, 250, 895, 160, "Interested queue", ["58 selected notes · 23 interested · 38 Must read", "The queue is small enough to review and export."])
    draw_card(draw, 430, 435, 895, 160, "Foundation by direction", ["AI seismology, tomography, phase picking, dense arrays, induced seismicity.", "Archive-tier papers stay out unless explicitly marked interested."])
    draw_card(draw, 430, 620, 895, 150, "Local-first library", ["index.html, search_index.json, per-paper Markdown notes, and score breakdowns remain in the tool workspace."])
    img.save(out_file)


def draw_pillow_evidence(out_file: Path) -> None:
    img, draw = browser_canvas("Evidence and Review Workflow", "Inspect what a selected-paper report can support before citing it")
    draw_card(draw, 115, 255, 590, 210, "Selected paper", ["Neural-field travel-time tomography", "Must read · full-text-ready · method bridge", "Related to regularization, inversion, and uncertainty tracking."], accent="#6d28d9")
    draw_card(draw, 735, 255, 590, 210, "Evidence boundary", ["Can support: reading plan, section coverage, workup, review pack.", "Cannot replace checking the original paper for final citation claims."])
    for x, big, small in [(150, "1", "local text cache"), (470, "8", "figure/table captions"), (790, "5", "foundation links")]:
        rounded(draw, (x, 510, x + 255, 635), 12, "#ffffff", "#d8e0ea")
        draw_text(draw, (x + 30, 535), big, 48, "#111827", bold=True)
        draw_text(draw, (x + 82, 555), small, 22, "#64748b")
    rounded(draw, (115, 690, 1325, 785), 12, "#0f172a")
    draw_text(draw, (145, 715), "./evidence_reader.sh --paper-id 868e160", 21, "#e5e7eb")
    draw_text(draw, (145, 748), "./review_workflow.sh --paper-id 868e160 --open", 21, "#e5e7eb")
    img.save(out_file)


def draw_pillow_map(out_file: Path) -> None:
    img, draw = browser_canvas("Research Map and Advice", "Cluster retained papers, expose gaps, and turn alerts into research strategy")
    rounded(draw, (115, 250, 765, 760), 14, "#ffffff", "#d8e0ea")
    nodes = [
        (190, 430, "Receiver functions", "#dbeafe", "#1d4ed8"),
        (490, 330, "Ambient noise", "#d1fae5", "#047857"),
        (510, 520, "Joint inversion", "#ede9fe", "#6d28d9"),
        (350, 650, "DAS monitoring", "#fef3c7", "#92400e"),
    ]
    for a, b in [(0, 1), (1, 2), (0, 2), (2, 3)]:
        x1, y1, *_ = nodes[a]
        x2, y2, *_ = nodes[b]
        draw.line((x1 + 70, y1 + 18, x2 + 70, y2 + 18), fill="#94a3b8", width=3)
    for x, y, label, fill, fg in nodes:
        rounded(draw, (x, y, x + 190, y + 48), 24, fill, "#d8e0ea")
        draw_text(draw, (x + 18, y + 13), label, 18, fg, bold=True)
    draw_card(draw, 795, 250, 530, 510, "Advice", ["Opportunity: connect receiver-function discontinuity constraints with ambient-noise velocity models.", "Gap: few retained papers quantify uncertainty consistently across methods.", "Next alerts: joint inversion uncertainty, crustal anisotropy, dense array monitoring."])
    img.save(out_file)


def draw_pillow_integrations(out_file: Path) -> None:
    img, draw = browser_canvas("Clean Obsidian and Zotero Handoff", "Keep the machine workspace local; export only selected notes and citation files")
    draw_card(draw, 115, 250, 590, 430, "Obsidian clean export", ["01_Literatures/10_Scholar_Alert_Reader", "01_Papers / selected-paper.md", "type: paper · generated: true", "source_tool: scholar-alert-reader", "obsidian_import: clean", "No automatic wikilinks"], accent="#0f766e")
    rounded(draw, (735, 250, 1325, 505), 12, "#ffffff", "#d8e0ea")
    draw_text(draw, (760, 280), "Zotero-ready Must-read files", 28, "#111827", bold=True)
    rounded(draw, (760, 325, 1300, 455), 10, "#0f172a")
    for i, line in enumerate(["@article{tomography2026,", "  title = {Neural-field travel-time tomography},", "  journal = {Computers & Geosciences},", "  keywords = {tomography, uncertainty, method}", "}"]):
        draw_text(draw, (782, 345 + i * 22), line, 17, "#e5e7eb")
    pill(draw, 760, 475, "scholar_alert_reader.bib")
    pill(draw, 980, 475, "scholar_alert_reader.ris")
    rounded(draw, (735, 555, 1325, 680), 12, "#ecfeff", "#bae6fd")
    draw_text(draw, (760, 585), "Internal learning signals are hidden from downstream tags:", 22, "#0f172a", bold=True)
    draw_text(draw, (760, 625), "similar:, user:, feedback, semantic, watchlist", 21, "#475569")
    img.save(out_file)


PILLOW_BUILDERS: dict[str, Callable[[Path], None]] = {
    "01-daily-digest": draw_pillow_digest,
    "02-feedback-triage": draw_pillow_review,
    "03-foundation-interested": draw_pillow_library,
    "04-deep-read-copilot": draw_pillow_evidence,
    "05-research-map-advice": draw_pillow_map,
    "06-obsidian-zotero": draw_pillow_integrations,
}


def render_with_pillow(slug: str, out_file: Path) -> bool:
    if Image is None:
        return False
    PILLOW_BUILDERS[slug](out_file)
    return True


def main() -> int:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    if Image is not None:
        for slug, _, _ in SCREENSHOTS:
            render_with_pillow(slug, SCREENSHOT_DIR / f"{slug}.png")
        write_index()
        print(f"Generated screenshots in {SCREENSHOT_DIR}")
        return 0

    chrome = chrome_path()
    if not chrome:
        raise SystemExit("Google Chrome or Chromium is required to render screenshots.")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for slug, _, builder in SCREENSHOTS:
            html_file = tmp_dir / f"{slug}.html"
            html_file.write_text(builder(), encoding="utf-8")
            render_with_chrome(html_file, SCREENSHOT_DIR / f"{slug}.png", chrome)

    write_index()
    print(f"Generated screenshots in {SCREENSHOT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
