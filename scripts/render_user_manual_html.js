#!/usr/bin/env node
/* Render the Chinese user manual into a local presentation-friendly HTML page. */

const fs = require("fs");
const path = require("path");
const { marked } = require("marked");

const root = path.resolve(__dirname, "..");
const input = path.join(root, "docs", "user_manual.zh.md");
const output = path.join(root, "docs", "user_manual.zh.html");

const markdown = fs.readFileSync(input, "utf8");

marked.setOptions({
  gfm: true,
  breaks: false,
});

function slug(value) {
  return String(value)
    .toLowerCase()
    .replace(/<[^>]+>/g, "")
    .replace(/[^\p{Letter}\p{Number}]+/gu, "-")
    .replace(/^-+|-+$/g, "");
}

const renderer = new marked.Renderer();
renderer.heading = function ({ tokens, depth }) {
  const text = this.parser.parseInline(tokens);
  const id = slug(text);
  return `<h${depth} id="${id}">${text}</h${depth}>\n`;
};

marked.use({ renderer });

const body = marked.parse(markdown);

const html = `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Scholar Alert Reader 中文用户手册</title>
  <style>
    :root {
      --bg: #f8fafc;
      --paper: #ffffff;
      --ink: #17212f;
      --muted: #64748b;
      --line: #d7e2f0;
      --teal: #0f766e;
      --blue: #2563eb;
      --amber: #d97706;
      --rose: #e11d48;
      --soft: #ecfeff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: linear-gradient(180deg, #f1f5f9 0%, var(--bg) 280px);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", "Segoe UI", sans-serif;
      line-height: 1.68;
    }
    .shell {
      width: min(1120px, calc(100vw - 42px));
      margin: 36px auto 72px;
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: 0 24px 70px rgba(15, 23, 42, 0.08);
      overflow: hidden;
    }
    header {
      padding: 44px 54px 28px;
      background: #0f172a;
      color: white;
      border-bottom: 5px solid var(--teal);
    }
    header .eyebrow {
      color: #99f6e4;
      font-size: 14px;
      font-weight: 700;
      letter-spacing: .04em;
      text-transform: uppercase;
    }
    header h1 {
      margin: 10px 0 12px;
      font-size: clamp(34px, 5vw, 58px);
      line-height: 1.05;
      letter-spacing: 0;
    }
    header p {
      margin: 0;
      max-width: 850px;
      color: #dbeafe;
      font-size: 18px;
    }
    nav {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 10px;
      padding: 22px 54px;
      background: #f8fafc;
      border-bottom: 1px solid var(--line);
    }
    nav a {
      display: block;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 12px;
      text-decoration: none;
      color: var(--teal);
      background: white;
      font-weight: 700;
      text-align: center;
      font-size: 14px;
    }
    main {
      padding: 18px 54px 56px;
    }
    h1:first-child { display: none; }
    h2 {
      margin-top: 46px;
      padding-top: 20px;
      border-top: 1px solid var(--line);
      font-size: 28px;
      line-height: 1.25;
    }
    h3 {
      margin-top: 30px;
      font-size: 21px;
    }
    p, li {
      font-size: 16px;
    }
    blockquote {
      margin: 22px 0;
      padding: 16px 20px;
      background: #ecfdf5;
      border-left: 5px solid var(--teal);
      border-radius: 12px;
      color: #134e4a;
    }
    img {
      display: block;
      max-width: 100%;
      height: auto;
      margin: 22px auto 32px;
      border-radius: 18px;
      border: 1px solid var(--line);
      box-shadow: 0 16px 44px rgba(15, 23, 42, 0.10);
      background: white;
    }
    p > img:only-child {
      width: 100%;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      margin: 20px 0 30px;
      overflow: hidden;
      border-radius: 14px;
      border: 1px solid var(--line);
    }
    th, td {
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      font-size: 15px;
    }
    th {
      background: #f1f5f9;
      color: #334155;
      font-weight: 800;
    }
    tr:last-child td { border-bottom: 0; }
    code {
      font-family: "SFMono-Regular", Menlo, Consolas, monospace;
      background: #eef2ff;
      color: #1e293b;
      padding: 2px 6px;
      border-radius: 6px;
      font-size: .92em;
    }
    pre {
      background: #0b1220;
      color: #e5e7eb;
      padding: 18px 20px;
      border-radius: 16px;
      overflow-x: auto;
      border: 1px solid #1e293b;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,.03);
    }
    pre code {
      background: transparent;
      color: inherit;
      padding: 0;
      border-radius: 0;
      font-size: 14px;
    }
    a { color: var(--blue); }
    hr { border: 0; border-top: 1px solid var(--line); margin: 44px 0; }
    .footer {
      padding: 22px 54px 36px;
      color: var(--muted);
      border-top: 1px solid var(--line);
      background: #f8fafc;
      font-size: 14px;
    }
    @media (max-width: 800px) {
      .shell { width: 100%; margin: 0; border-radius: 0; border-left: 0; border-right: 0; }
      header, main, nav, .footer { padding-left: 24px; padding-right: 24px; }
      nav { grid-template-columns: 1fr 1fr; }
      h2 { font-size: 24px; }
    }
    @media print {
      body { background: white; }
      .shell { box-shadow: none; border: 0; width: 100%; margin: 0; }
      nav { display: none; }
      img { box-shadow: none; page-break-inside: avoid; }
      h2 { page-break-after: avoid; }
      pre { white-space: pre-wrap; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div class="eyebrow">Local literature triage manual</div>
      <h1>Scholar Alert Reader 中文用户手册</h1>
      <p>从 Scholar Alert、RSS/arXiv、BibTeX/RIS 到 Review Workspace、foundation、本地知识库、Obsidian clean export 和 Zotero handoff。</p>
    </header>
    <nav>
      <a href="#3-三分钟-demo-不接-gmail-也能先跑通">三分钟 demo</a>
      <a href="#7-第一次真实运行-建立-foundation">Gmail foundation</a>
      <a href="#9-review-workspace-怎么用">Review Workspace</a>
      <a href="#13-obsidian-推荐-clean-export">Obsidian / Zotero</a>
    </nav>
    <main>${body}</main>
    <div class="footer">Generated from <code>docs/user_manual.zh.md</code>. Keep the repository folder structure so relative images display correctly.</div>
  </div>
</body>
</html>
`;

fs.writeFileSync(output, html, "utf8");
console.log(`Wrote ${output}`);
