# 不使用 Codex 或其他 AI 的手动使用流程

这份文档给只想用终端的人。Codex、Claude、Obsidian、Zotero 都不是必需品；核心就是一个本地 Python CLI，加上初始化后生成的一组脚本。

## 核心流程

```text
论文来源
  -> 解析元数据
  -> 去重
  -> 按研究画像打分
  -> 生成 Review Workspace 和静态 digest
  -> 维护本地轻量 knowledge_base
```

常用输出：

- `reader_out/foundation/`：第一次基线库。
- `reader_out/daily/`：之后每天的新论文。
- `knowledge_base/library.json`：本地保留文献库，通常是 Must read + Skim。
- `knowledge_base/index.html`：本地文献库静态首页。
- `knowledge_base/papers/*.md`：每篇论文的 Markdown 记录。
- `DASHBOARD.html`：项目静态导航和诊断。
- `./serve_reader.sh`：交互式 Review Workspace，用来点论文标题、标 interested/archive、写 note、改阅读状态。

## 1. 安装

需要：

- Python 3.10、3.11 或 3.12。
- Git。
- 如果用 Gmail：需要自己建 Google Cloud Desktop OAuth client，并启用 Gmail API。

```bash
git clone https://github.com/RunningXinLiu/scholar-alert-reader-skill.git
cd scholar-alert-reader-skill
```

建议建虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
```

如果要用 Gmail：

```bash
python3 -m pip install -r requirements-gmail.txt
```

## 2. 初始化本地项目

项目目录建议放在 repo 外面：

```bash
python3 scripts/scholar_reader.py init-project \
  --project-dir ~/scholar_alerts \
  --profile-template ai-seismology

cd ~/scholar_alerts
```

先用内置 demo 验证，不需要 Gmail、不需要私人数据：

```bash
RSS_SOURCE=examples/sample_feed.atom ./rss_import.sh
PAPERS_JSON=reader_out/rss/papers.json ./serve_reader.sh
```

如果浏览器打开 Review Workspace，说明本地流程通了。

## 3. 设置研究画像

编辑：

```text
~/scholar_alerts/profiles/research_profile.json
```

重点改这些：

- `focus_terms`：你关心的主题。
- `methods`：方法、模型、算法。
- `regions`：区域、数据集、台阵、研究区。
- `semantic_queries`：用一句话描述你真正想找的论文。
- `exclude_terms`：经常误报的噪音。
- `tier_thresholds`：Must read / Skim / Archive 的分数阈值。

也可以用向导：

```bash
./profile_wizard.sh \
  --focus "seismic foundation model, phase picking, earthquake monitoring" \
  --method "self-supervised learning, uncertainty quantification" \
  --region "Tibet, Sichuan Basin"
```

检查 profile：

```bash
./profile_doctor.sh
open profiles/profile_doctor.md
```

## 4. Gmail 配置

Gmail 是可选的，但最适合接 Google Scholar Alert。

Google Cloud 里做这些：

1. 创建或选择一个 project。
2. 启用 Gmail API。
3. 配 OAuth consent screen。
4. 如果 app 是 testing，把自己的 Gmail 加成 test user。
5. 创建 OAuth client，类型选 `Desktop app`。
6. 下载 JSON。

把 JSON 放到 repo 外面，例如：

```text
~/.codex/scholar-alert-reader/gmail_credentials.json
```

第一次授权：

```bash
python3 /path/to/scholar-alert-reader-skill/scripts/scholar_reader.py auth-gmail \
  --gmail-credentials ~/.codex/scholar-alert-reader/gmail_credentials.json \
  --gmail-token ~/.codex/scholar-alert-reader/gmail_token.json
```

然后在 `~/scholar_alerts/reader.env` 写：

```bash
SOURCE=auto
GMAIL_CREDENTIALS=$HOME/.codex/scholar-alert-reader/gmail_credentials.json
GMAIL_TOKEN=$HOME/.codex/scholar-alert-reader/gmail_token.json
```

检查 Gmail 是否可读：

```bash
./source_check.sh --source gmail --live
```

看到 `[OK] Gmail live read` 就说明 Gmail 路径通了。

## 5. 第一次真实运行：foundation

第一次应该跑 foundation。它会读已有 Scholar Alert 邮件，去重、打分、建立本地库，并写入 seen baseline。

```bash
MODE=foundation SOURCE=gmail ./run_reader.sh
```

查看 foundation：

```bash
PAPERS_JSON=reader_out/foundation/papers.json ./serve_reader.sh
open reader_out/foundation/digest.html
open knowledge_base/index.html
```

在 Review Workspace 里先给一批论文编辑状态、写 note，然后统一点一次 `Save selected changes`。note 只要不为空，也会跟这次批量保存一起写入。

常用控件：

- `Decision`：`Interested` / `Neutral` / `Archive`，决定这篇是否进入你的个人文献筛选结果。
- `Priority`：`Auto` / `Must read` / `Skim` / `Archive`，用于手动固定阅读优先级。
- `Learning signal`：`More like this` / `Less like this` / 清除信号，用来影响后续排序。
- `Reading status`：`reading` / `read` / `must-cite` / `background-only` / `not-relevant` 等阅读状态。
- `Generate report on save`：可选生成 `Deep read` / `Full review` / `Workup` / `Review pack`。

## 6. 日常 daily

foundation 之后，daily 只显示还没见过的新论文：

```bash
SOURCE=gmail ./run_reader.sh
./serve_reader.sh
```

如果显示 `Papers in digest: 0`，先看：

```bash
open reader_out/daily/digest.html
python3 -m json.tool reader_out/daily/summary.json | sed -n '1,120p'
```

如果原因是 `all_seen`，这不是坏了。意思是 Gmail 读到了论文，但这些论文已经在 foundation/seen state 里。

如果只是想重看最近邮件里的论文，不想改 foundation：

```bash
./review_recent.sh
./serve_recent.sh
```

## 7. 不用 Gmail 的来源

RSS/Atom：

```bash
RSS_SOURCE=examples/sample_feed.atom ./rss_import.sh
PAPERS_JSON=reader_out/rss/papers.json ./serve_reader.sh
```

arXiv：

```bash
ARXIV_QUERY='cat:physics.geo-ph AND all:tomography' ./arxiv_search.sh
PAPERS_JSON=reader_out/arxiv/papers.json ./serve_reader.sh
```

BibTeX/RIS：

```bash
cp ~/Downloads/library.bib import.bib
./bibtex_import.sh
PAPERS_JSON=reader_out/bibtex/papers.json ./serve_reader.sh
```

```bash
cp ~/Downloads/library.ris import.ris
./ris_import.sh
PAPERS_JSON=reader_out/ris/papers.json ./serve_reader.sh
```

## 8. 可选：导出到 Obsidian 和 Zotero

Obsidian 和 Zotero 都是可选的。建议把本工具自己的 `knowledge_base/` 当成机器工作区，然后只把精选结果导出到下游工具。

推荐的 Obsidian clean export：

```bash
./sync_obsidian_vault.sh --obsidian-mode clean
```

默认会写到：

```text
~/Documents/Obsidian Vault/01_Literatures/10_Scholar_Alert_Reader/01_Papers/
```

clean 模式只导出 `Must read` 和你手动标为 `Interested` 的论文 note。它不会导出 dashboard、search index、runs、answers、analysis reports、review packs 等机器生成工作区文件。生成的 note 默认不加自动 `[[wikilinks]]`，主要用 tags 和普通 Markdown 链接，避免污染你的 Obsidian graph。

如果第一次导入到已有目录，想完全保守不清理旧文件：

```bash
./sync_obsidian_vault.sh --obsidian-mode clean --no-prune
```

推荐的 Zotero 导出：

```bash
./zotero_export.sh
```

它会写：

```text
knowledge_base/zotero/scholar_alert_reader.bib
knowledge_base/zotero/scholar_alert_reader.ris
```

把其中一个导入 Zotero 即可。如果之后在 Zotero 里用 Better BibTeX 导出了库，可以把 citation key 和本地 PDF 路径同步回本工具：

```bash
ZOTERO_BIBTEX_PATH=~/Downloads/My_Library.bib ./zotero_sync.sh
```

## 9. 不要分享什么

repo 可以公开。真实生成的个人项目默认不能公开。

不要分享：

- Gmail credentials 或 token。
- 原始 mailbox。
- `profiles/seen_papers.json`。
- `knowledge_base/feedback.json`。
- 真实账号生成的 `knowledge_base/` 和 `reader_out/`。

分享前跑：

```bash
./privacy_check.sh
```

## 10. 推荐日常习惯

```bash
cd ~/scholar_alerts
SOURCE=gmail ./run_reader.sh
./serve_reader.sh
```

然后在 Review Workspace：

1. 直接点论文标题看原网页。
2. 每天选几个明确的 Interested / Archive。
3. 只给真正可能读的论文写简短 note。
4. 最后统一点 `Save selected changes`。
5. 想重看最近邮件时再用 `review_recent.sh`。
