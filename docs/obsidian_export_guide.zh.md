# Obsidian 导出指南（以 clean 为默认）

这份指南的核心边界：

- `knowledge_base/` 是机器工作区。
- Obsidian 默认只接收精选论文笔记。
- `clean` 是默认模式。
- `full` 必须显式指定，只用于调试/归档。

## 图示速览

![模式选择图](assets/obsidian-mode-decision.zh.png)

![目录边界图](assets/obsidian-boundary.zh.png)

![迁移流程图](assets/obsidian-migration.zh.png)

## 模式选择图

```mermaid
flowchart TD
  A["要把结果送进 Obsidian"] --> B{"是否只想要精选论文?"}
  B -->|是| C["用 clean (默认)"]
  B -->|否，我要完整机器产物| D["用 --obsidian-mode full"]
  C --> E{"这个目录以前跑过 full?"}
  E -->|是，先保守| F["先用 clean + --no-prune 一次"]
  E -->|否| G["直接 clean"]
  F --> H["检查无误后，再决定是否去掉 --no-prune"]
  D --> I["请用单独 FULL 目录，不要和日常 inbox 混用"]
```

## 目录边界图

```mermaid
flowchart LR
  A["Scholar Alert Reader 项目"] --> B["knowledge_base/ (机器工作区)"]
  A --> C["reader_out/ (digest 与运行输出)"]
  D["Obsidian Vault"] --> E["01_Literatures/10_Scholar_Alert_Reader/01_Papers"]
  B -. "不要整目录同步" .-> D
  C -. "不要整目录同步" .-> D
  A -->|"obsidian export (clean)"| E
```

## 旧 full 目录迁移到 clean 的流程

```mermaid
flowchart TD
  A["历史目录里有 full 产物"] --> B["先跑 clean + --no-prune"]
  B --> C["确认 paper notes 正常"]
  C --> D{"是否需要保留旧 full 产物?"}
  D -->|需要| E["继续带 --no-prune"]
  D -->|不需要| F["再跑一次 clean (不带 --no-prune)"]
  F --> G["工具只会清理 manifest 标记过的 full 产物"]
```

## 10 分钟落地步骤

1. 先把本地项目放在 Obsidian 外部：
   - 例如：`~/scholar_alerts`
2. 在 Obsidian 里给导出建独立 inbox 目录（不要放 Vault 根目录）：
   - 例如：`~/Documents/Obsidian Vault/01_Literatures/10_Scholar_Alert_Reader`
3. 在项目目录跑日常筛选：
   - `./run_reader.sh` 或各类 source import 脚本
4. 用 clean 导出（默认）：

```bash
python3 scripts/scholar_reader.py obsidian \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --vault-dir "$HOME/Documents/Obsidian Vault/01_Literatures/10_Scholar_Alert_Reader"
```

5. 如果这个目录以前用过 full，先保守跑一次：

```bash
python3 scripts/scholar_reader.py obsidian \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --vault-dir "$HOME/Documents/Obsidian Vault/01_Literatures/10_Scholar_Alert_Reader" \
  --obsidian-mode clean \
  --no-prune
```

6. 只有在你明确需要完整机器产物时才用 full：

```bash
python3 scripts/scholar_reader.py obsidian \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --obsidian-mode full \
  --vault-dir "$HOME/Documents/Obsidian Vault/01_Literatures/10_Scholar_Alert_Reader_FULL"
```

## clean 会导出什么

- 只导出 `01_Papers/*.md`。
- 只包含 `Must read` 和标记为 `interested` 的论文。
- frontmatter 包含 `source_tool`、`obsidian_import`、`tier`、`score`、`reading_status`、`tags`、`source_types`。
- 不会自动生成 `[[wikilinks]]`。

## clean 不会导出什么

- dashboard/index/search 这类机器工作区文件。
- `answers/`、`analysis/`、`runs/` 等机器报告目录。

## 建议与禁忌

建议：
- 导出到 Obsidian 的独立 inbox 目录。
- 日常固定用 `clean`。
- `full` 放在单独目录，按需使用。

不要：
- 把整个 `knowledge_base/` 同步或拷贝进 Obsidian。
- 导出到 Vault 根目录。
- 把日常 clean inbox 和 full 归档目录混在一个目录里（除非你非常确定这是你要的）。

## 命令速查

```bash
# 日常推荐导出
python3 scripts/scholar_reader.py obsidian --profile profiles/research_profile.json --kb-dir knowledge_base --vault-dir "$HOME/Documents/Obsidian Vault/01_Literatures/10_Scholar_Alert_Reader"

# 保守导出（不清理旧 full 产物）
python3 scripts/scholar_reader.py obsidian --profile profiles/research_profile.json --kb-dir knowledge_base --vault-dir "$HOME/Documents/Obsidian Vault/01_Literatures/10_Scholar_Alert_Reader" --no-prune

# 显式 full 导出
python3 scripts/scholar_reader.py obsidian --profile profiles/research_profile.json --kb-dir knowledge_base --obsidian-mode full --vault-dir "$HOME/Documents/Obsidian Vault/01_Literatures/10_Scholar_Alert_Reader_FULL"
```
