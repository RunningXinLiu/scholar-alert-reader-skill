# Gmail 授权中文指南

> 目标：让 Scholar Alert Reader 用 Gmail API 读取你的 Google Scholar Alert 邮件。默认只申请 Gmail read-only 权限，不会发送邮件、删除邮件或修改邮箱内容。

## 1. 先说结论

Gmail 接入分成两部分：

1. 你在 Google Cloud 里创建一个自己的 `Desktop app` OAuth client，并下载 JSON。
2. Scholar Alert Reader 在本机打开浏览器，让你登录 Gmail 并授权只读访问。

如果你用 Codex，推荐让 Codex 帮你做本地检查和授权命令。你仍然需要亲自在 Google Cloud 页面创建 OAuth client，并在浏览器里点一次授权。

可以直接对 Codex 说：

```text
使用 scholar-alert-reader skill，帮我检查 Gmail API 依赖、OAuth 凭据和 token 状态。
如果缺少 token，帮我启动 Gmail OAuth 授权。
授权成功后，帮我跑 Gmail source check。
```

授权成功后，再说：

```text
用 Gmail Scholar Alert 邮件帮我第一次建立 foundation，然后打开 Review Workspace。
```

## 2. 需要准备什么

你需要：

- 一个能登录 Gmail 的 Google 账号。
- Google Scholar Alert 已经发到这个 Gmail。
- 本地 Python 环境。
- Scholar Alert Reader repo 或已安装的 CLI。
- 一个 Google Cloud OAuth client JSON。

你不需要：

- Obsidian。
- Zotero。
- Google Cloud 付费账号。
- 把 token 或 client secret 上传给任何人。

## 3. Google Cloud 上怎么做

进入 [Google Cloud Console](https://console.cloud.google.com/) 后：

1. 创建或选择一个 project。
2. 打开 `APIs & Services`。
3. 进入 `Library`，搜索并启用 `Gmail API`。
4. 进入 `OAuth consent screen`。
5. 用户类型通常选择 `External`，测试阶段即可。
6. 填 app name、support email、developer contact email。
7. 在 test users 里加入你自己的 Gmail。
8. 进入 `Credentials`。
9. 点击 `Create credentials` -> `OAuth client ID`。
10. Application type 选择 `Desktop app`。
11. 创建后下载 JSON。

注意：这里一定要选 `Desktop app`。如果选成 Web app，后面容易出现 `redirect_uri_mismatch`。

## 4. JSON 放哪里

推荐放在 repo 外面，例如：

```text
~/.codex/scholar-alert-reader/gmail_credentials.json
```

如果你下载的文件名类似：

```text
client_secret_123456.apps.googleusercontent.com.json
```

可以改名成：

```text
gmail_credentials.json
```

不要把这个文件提交到 GitHub。

## 5. 安装 Gmail 依赖

在你使用的 Python 环境里安装：

```bash
python3 -m pip install -r requirements-gmail.txt
```

如果你在 conda 环境里，例如 `seisloc`：

```bash
conda run -n seisloc python -m pip install -r requirements-gmail.txt
```

## 6. 第一次授权

从 repo 目录运行：

```bash
python3 -m scholar_alert_reader auth-gmail \
  --gmail-credentials ~/.codex/scholar-alert-reader/gmail_credentials.json \
  --gmail-token ~/.codex/scholar-alert-reader/gmail_token.json
```

如果你还没安装 package，也可以用脚本入口：

```bash
python3 scripts/scholar_reader.py auth-gmail \
  --gmail-credentials ~/.codex/scholar-alert-reader/gmail_credentials.json \
  --gmail-token ~/.codex/scholar-alert-reader/gmail_token.json
```

命令会打开浏览器。你需要：

1. 选择 Gmail 账号。
2. 如果出现测试 app 提示，继续进入。
3. 允许 Gmail read-only 权限。
4. 看到 `The authentication flow has completed. You may close this window.` 就完成了。

授权完成后，本地会生成：

```text
~/.codex/scholar-alert-reader/gmail_token.json
```

这个 token 也不要提交到 GitHub。

## 7. 在项目里写入配置

进入你的 Scholar Alert Reader 项目目录，例如：

```bash
cd ~/scholar_alerts
```

编辑 `reader.env`，加入：

```bash
SOURCE=auto
GMAIL_CREDENTIALS=$HOME/.codex/scholar-alert-reader/gmail_credentials.json
GMAIL_TOKEN=$HOME/.codex/scholar-alert-reader/gmail_token.json
```

然后检查 Gmail 是否能读取：

```bash
./source_check.sh --source gmail --live
```

看到 Gmail live read 成功后，就可以开始正式使用。

## 8. 第一次建立 foundation

第一次使用建议从已有 Scholar Alert 邮件建立 foundation：

```bash
MODE=foundation SOURCE=gmail ./run_reader.sh
PAPERS_JSON=reader_out/foundation/papers.json ./serve_reader.sh
```

foundation 会：

- 读取已有 Scholar Alert 邮件。
- 解析论文标题、作者、来源、摘要片段和链接。
- 去重。
- 按 research profile 打分。
- 写入本地 `knowledge_base/`。
- 建立 seen state，后续 daily 不重复推旧论文。

## 9. 日常 daily

foundation 之后，日常只看新论文：

```bash
SOURCE=gmail ./run_reader.sh
./serve_reader.sh
```

如果当天没有新论文，digest 可能显示 0。先看：

```bash
open reader_out/daily/digest.html
python3 -m json.tool reader_out/daily/summary.json | sed -n '1,120p'
```

如果诊断里显示很多论文被 `seen state` 过滤，说明 Gmail 读到了邮件，只是没有新的未见过论文。

## 10. Token 过期或撤销怎么办

如果出现 `invalid_grant`、`Token has been expired or revoked` 之类错误：

1. 备份旧 token。
2. 删除旧 token。
3. 重新跑 `auth-gmail`。

命令示例：

```bash
mv ~/.codex/scholar-alert-reader/gmail_token.json \
   ~/.codex/scholar-alert-reader/gmail_token.json.bak

python3 -m scholar_alert_reader auth-gmail \
  --gmail-credentials ~/.codex/scholar-alert-reader/gmail_credentials.json \
  --gmail-token ~/.codex/scholar-alert-reader/gmail_token.json
```

## 11. 常见错误

### `redirect_uri_mismatch`

通常是 OAuth client 类型选错了。请重新创建 `Desktop app` 类型的 OAuth client。

### `access blocked` 或测试用户不能登录

检查 OAuth consent screen 里是否把你的 Gmail 加入了 test users。

### `Gmail API has not been used in project`

说明 Gmail API 没启用。进入 Google Cloud 的 API Library，启用 Gmail API。

### `ModuleNotFoundError: google...`

Gmail 依赖没装到当前 Python 环境。重新运行：

```bash
python3 -m pip install -r requirements-gmail.txt
```

### 网络或浏览器打不开授权页

先确认本机能访问 Google 登录页。授权过程需要本机浏览器打开 Google OAuth 页面，并回调到 `localhost`。

## 12. 隐私边界

Gmail 路径只需要这个 scope：

```text
https://www.googleapis.com/auth/gmail.readonly
```

不要公开：

- `gmail_credentials.json`
- `gmail_token.json`
- 原始邮件导出
- `seen_papers.json`
- `knowledge_base/feedback.json`
- 真实个人 `knowledge_base/`

公开分享 repo 前可以运行：

```bash
./privacy_check.sh --strict
```

## 13. 给 Codex 的推荐提示词

第一次配置：

```text
使用 scholar-alert-reader skill，帮我检查 Gmail API 依赖、OAuth credentials 和 token。
如果 token 不存在或过期，帮我重新启动 Gmail OAuth 授权。
```

授权后检查：

```text
帮我在当前 Scholar Alert Reader 项目里跑 Gmail source check，确认能读 Scholar Alert 邮件。
```

第一次建立文献库：

```text
假装我是第一次使用，没有 Obsidian 和 Zotero。
请从 Gmail Scholar Alert 邮件建立 foundation，生成 digest 和本地 knowledge_base，并打开 Review Workspace。
```

日常使用：

```text
从 Gmail 读取新的 Scholar Alert 邮件，生成 daily digest，并打开 Review Workspace 让我筛选。
```
