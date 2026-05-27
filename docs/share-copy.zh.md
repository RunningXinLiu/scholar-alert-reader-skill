# 朋友圈文案

## 短版

我做了一个 Codex skill：Scholar Alert Reader。它可以每天从 Google Scholar Alert 邮件里自动筛论文，生成阅读 digest，维护自己的文献 foundation，还能对重点论文做 deep-read、问答、比较和研究建议。Obsidian/Zotero 都是可选增强，不装也能用。

## 稍长版

最近做了一个自动文献阅读/筛选工具：Scholar Alert Reader。

它会读取 Google Scholar Alert 邮件，把重复和低相关的论文先过滤掉，再根据自己的研究方向排序，生成每日 HTML digest 和一个持续更新的个人文献库。后面还可以让 Codex 基于这个 foundation 做单篇论文 deep-read、文献库问答、论文对比和研究方向建议。

设计上是 local-first：核心功能只需要 Codex + 本地文件。Obsidian 可以用来沉淀长期笔记，Zotero 可以用来管引用和 PDF，但它们都不是必须的。

## 一句话定位

把 Google Scholar Alert 从“每天一堆邮件”变成“每天一份个人化文献情报”。

## 配图建议

- `docs/assets/social-card.png`: 适合朋友圈首图。
- `docs/assets/workflow.gif`: 适合展示工作流。
- `docs/assets/architecture.png`: 适合解释整体架构。
