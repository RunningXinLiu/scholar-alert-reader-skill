#!/usr/bin/env python3
"""Generate sanitized product screenshots for README and marketing."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_DIR = ROOT / "docs" / "screenshots"
WIDTH = 1440
HEIGHT = 960


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
        "Sanitized demo run from Google Scholar Alert emails",
        """
<main class="main">
  <div class="metrics">
    <div class="metric">Papers: 18</div><div class="metric">Must read: 4</div><div class="metric">Skim: 7</div>
    <div class="metric">Archived: 7</div><div class="metric">Scholar emails: 28</div>
  </div>
  <div class="grid" style="margin-top:22px">
    <section>
      <h2>Must read</h2>
      <article class="paper featured">
        <h3>Receiver function imaging beneath the eastern Tibetan Plateau</h3>
        <div class="badges"><span class="badge must">Must read</span><span class="badge">score 42</span><span class="badge">Tibet</span><span class="badge">receiver function</span></div>
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
        "Feedback Triage UI",
        "Mark papers as interested, archive noise, and tune future ranking",
        """
<main class="main">
  <div class="toolbar">
    <div class="input">Search title, alert, term, source</div>
    <div class="input">All tiers</div>
  </div>
  <div class="grid" style="margin-top:20px">
    <article class="paper featured">
      <h3>Crustal discontinuities from receiver functions and ambient noise</h3>
      <div class="badges"><span class="badge">id p7a42</span><span class="badge must">Must read</span><span class="badge">score 44</span></div>
      <p class="muted">Geophysical Journal International, 2026</p>
      <p>Combines receiver functions with surface-wave constraints to image lithospheric structure.</p>
      <div class="button-row">
        <span class="button primary">Interested + more like this</span>
        <span class="button danger">Archive + less like this</span>
        <span class="button">Deep read</span>
        <span class="button">Must cite</span>
      </div>
    </article>
    <article class="paper">
      <h3>Regional stress inversion from a global earthquake catalog</h3>
      <div class="badges"><span class="badge skim">Skim</span><span class="badge">score 24</span></div>
      <p class="muted">Solid candidate for background reading.</p>
      <div class="button-row">
        <span class="button">More like this</span><span class="button">Less like this</span><span class="button">Reading</span><span class="button">Read</span>
      </div>
    </article>
  </div>
  <div class="callout" style="margin-top:12px">
    Saved feedback updates <b>feedback.json</b>, refreshes the retained library, and changes the next daily ranking.
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
        "Deep Read Copilot",
        "Analyze a selected paper against your foundation and interested papers",
        """
<main class="main">
  <div class="grid">
    <section class="panel">
      <h2>Selected paper</h2>
      <h3>Joint receiver-function and surface-wave constraints on plateau crust</h3>
      <p class="muted">Why it matters: connects two active directions in the retained library.</p>
      <div class="badges"><span class="badge must">high priority</span><span class="badge">method bridge</span><span class="badge">Tibet</span></div>
    </section>
    <section class="panel">
      <h2>Against your foundation</h2>
      <p>Extends 6 retained receiver-function papers and challenges 2 older Moho-depth interpretations.</p>
      <p>Useful for: literature review framing, method comparison, and identifying candidate figures to reproduce.</p>
    </section>
  </div>
  <div class="three" style="margin-top:18px">
    <section class="panel"><div class="kpi">3</div><p class="muted">claims to verify</p></section>
    <section class="panel"><div class="kpi">5</div><p class="muted">foundation links</p></section>
    <section class="panel"><div class="kpi">2</div><p class="muted">follow-up papers</p></section>
  </div>
  <section class="panel" style="margin-top:18px">
    <h2>Reading plan</h2>
    <p>1. Check data geometry and station spacing. 2. Compare inversion assumptions with retained method papers. 3. Extract citations for plateau anisotropy and crustal thickness.</p>
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
        "Obsidian and Zotero Handoff",
        "Optional exports turn the Codex skill into a broader academic knowledge system",
        """
<main class="main grid">
  <section class="panel">
    <h2>Obsidian export</h2>
    <ul class="tree" style="margin-top:0">
      <li class="active">01_Literatures/10_Scholar_Alert_Reader</li>
      <li>00_Dashboard / Library Index.md</li>
      <li>01_Papers / p7a42.md</li>
      <li>02_Maps / Research Map.md</li>
      <li>03_Reading / Reading Status.md</li>
      <li>04_Answers / receiver-function-qna.md</li>
      <li>06_Deep_Reads / p7a42_deep_read.md</li>
    </ul>
  </section>
  <section class="panel">
    <h2>Zotero-ready files</h2>
    <div class="code">@article{{p7a42,
  title = {{Crustal discontinuities from receiver functions}},
  author = {{A. Researcher and B. Collaborator}},
  year = {{2026}},
  doi = {{10.0000/demo}}
}}</div>
    <div class="badges" style="margin-top:14px"><span class="badge">library.bib</span><span class="badge">library.ris</span><span class="badge">markdown notes</span></div>
  </section>
</main>
""",
    )


SCREENSHOTS = [
    ("01-daily-digest", "Daily digest dashboard", digest),
    ("02-feedback-triage", "Feedback UI for selecting interested papers", feedback_ui),
    ("03-foundation-interested", "Foundation and interested knowledge base", foundation_interested),
    ("04-deep-read-copilot", "Selected-paper deep read against the foundation", deep_read),
    ("05-research-map-advice", "Research map and advice", research_map),
    ("06-obsidian-zotero", "Obsidian and Zotero handoff", integrations),
]


def write_index() -> None:
    lines = [
        "# Marketing Screenshots",
        "",
        "Sanitized demo screenshots for README, GitHub sharing, and social posts.",
        "They do not contain personal mailbox data, OAuth tokens, or a real knowledge base.",
        "",
    ]
    for slug, caption, _ in SCREENSHOTS:
        lines.extend([f"## {caption}", "", f"![{caption}]({slug}.png)", ""])
    (SCREENSHOT_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")


def render_with_chrome(html_file: Path, out_file: Path, chrome: str) -> None:
    subprocess.run(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            "--no-default-browser-check",
            f"--window-size={WIDTH},{HEIGHT}",
            f"--screenshot={out_file}",
            html_file.as_uri(),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
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
