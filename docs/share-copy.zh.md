# 中文宣传文案

## 一句话

Scholar Alert Reader 是一个本地运行的自动文献分诊工具：把 Gmail/Apple Mail/Google Scholar Alert、BibTeX/RIS、RSS/Atom 和 arXiv 查询变成个性化论文 digest、阅读队列和个人研究知识库。

## 短版

我做了一个 Codex skill / 本地 CLI：Scholar Alert Reader。

它可以从 Gmail、Apple Mail、导出的 mbox、Zotero/Google Scholar 的 BibTeX/RIS、RSS/Atom feed 和 arXiv 查询里收集新论文；按你的研究方向、关键词、方法、地区、作者和排除词自动排序；每天或手动生成 HTML digest。

你可以把论文标成 interested / archive / more-like-this / less-like-this，后面的推荐会跟着调整。Obsidian 和 Zotero 是可选联动：Zotero 管引用和 PDF，Obsidian 沉淀笔记、方向图谱和深读报告。

项目作者：Xin Liu

GitHub: https://github.com/RunningXinLiu/scholar-alert-reader-skill

## 稍长版

每天 Google Scholar Alert、期刊 feed、arXiv 和各种文献导出都在产生新论文，但真正值得读的可能只有几篇。Scholar Alert Reader 做的事情就是把这些来源统一接进来，先去重、再按你的研究 profile 打分，然后输出一份可读的文献分诊报告。

它支持多种输入：

- Gmail API / Apple Mail / 导出的 `.mbox`
- Zotero、Google Scholar、出版社和数据库导出的 BibTeX / RIS
- RSS/Atom feed、arXiv 查询，以及其他结构化网页来源

它也支持持续学习：

- 自定义关键词、方法、地区、作者、排除词和临时 boost
- 标记 interested、archive、more-like-this、less-like-this
- 每天自动跑，或者需要时手动跑
- 输出 HTML digest、CSV/JSON、reading queue、foundation、interested library

后续还可以把保留下来的论文接到 Obsidian 和 Zotero：Obsidian 里生成 paper notes、research map、reading status、deep-read、comparison 和 Q&A；Zotero 负责引用和 PDF 管理。核心流程仍然是本地文件，不依赖 hosted service。

一句话：它不是又一个“论文收藏夹”，而是一个会按你的研究方向持续筛选、积累和反馈的个人文献入口。

## 面向用户的功能点

- **多来源接入**：Gmail、Apple Mail、mbox、BibTeX/RIS、RSS/Atom、arXiv。
- **个性化筛选**：按研究问题、关键词、方法、地区、作者、排除词打分。
- **可反馈学习**：对论文做 interested/archive/more-like-this/less-like-this，后续推荐会调整。
- **自动或手动推送**：可以每天定时生成 digest，也可以随时手动跑。
- **个人知识库**：保留重点论文，形成 foundation、interested list、方向页和每周综述。
- **深度阅读辅助**：对选中的论文生成 deep-read、对比、Q&A 和研究建议。
- **Zotero / Obsidian 联动**：导出引用文件和 Obsidian notes，但不强制安装。
- **本地优先**：邮箱授权、反馈和知识库默认留在本机。

## 配图建议

- `docs/assets/social-card.zh.png`: 适合朋友圈首图。
- `docs/assets/workflow.zh.gif`: 适合展示工作流。
- `docs/assets/architecture.zh.png`: 适合解释整体架构。
- `docs/assets/architecture-showcase.zh.png`: 适合做长图里的系统框架页。
- `docs/screenshots/`: 适合展示 digest、反馈、foundation、deep-read、Obsidian/Zotero 联动。
- `docs/assets/logo.png`: 适合头像、小图标或第二张图。

GitHub README 默认使用英文素材：`social-card.en.png`、`workflow.en.gif`、`architecture-showcase.en.png`。
