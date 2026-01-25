# auto-tasks

功能概述
- 定时任务仓库，按语言目录分层管理任务。以 GitHub Actions 为主执行定时任务（也支持手动触发）。

## 在 GitHub 中添加 Secrets（快速步骤）
1. 打开仓库页面 → `Settings`。  
2. 侧栏选择 `Secrets and variables` → `Actions`。  
3. 点击 `New repository secret`，填写 `Name`）与 `Value`（敏感值），点击 `Add secret`。  

## 目录

- [V2EX签到](#v2ex签到)
- [Telegram签到](#telegram签到)

## V2EX签到

### 概要
- 使用登录 Cookie 在 V2EX 签到并通过 Telegram 发送通知
- 脚本位于 `v2ex_sign/`。
- 工作流存放于 `.github/workflows/v2ex-sign.yml`。
### 配置（必须）
在仓库 Settings → Secrets → Actions 中添加如下的 secret：
- `V2EX_COOKIE` — V2EX 登录 Cookie（用于签到）
- `TELEGRAM_BOT_TOKEN` — Telegram Bot Token（用于发送通知）
- `TELEGRAM_CHAT_ID` — 接收通知的 chat id
### 本地测试（可选）
简要本地调试示例：
- `cd v2ex_sign`
- `V2EX_COOKIE="..." TELEGRAM_BOT_TOKEN="..." TELEGRAM_CHAT_ID="..." cargo run --release`
### 排查要点
- 查看 GitHub Actions 日志获取错误信息和输出。
- 确认所需 Secrets 已正确设置且未过期（如 Cookie）。
- 页面结构若变更，可能需要更新解析选择器。

---

## Telegram签到

### 概要
- 一个基于 [Telethon](https://github.com/LonamiWebs/Telethon) 的通用 Telegram 任务脚本，可用于自动签到、发送消息、执行预设任务等。
- 脚本位于 `telegram-sign/`。
- 工作流存放于 `.github/workflows/telegram-sign.yaml`。

### 配置（必须）
在仓库 `Settings` → `Secrets` → `Actions` 中添加如下 secret：
- `TELEGRAM_API_ID` — 从 [my.telegram.org](https://my.telegram.org) 获取。
- `TELEGRAM_API_HASH` — 从 [my.telegram.org](https://my.telegram.org) 获取。
- `TELEGRAM_SESSION` — 脚本登录所需的会话字符串，需**首次在本地运行脚本生成**。
- `TELEGRAM_SIGN_TASKS` — JSON 格式的任务列表，定义具体要执行的操作。

### `TELEGRAM_SIGN_TASKS` 示例
```json
[
  {
    "chat_id": 12345678,
    "text": "签到"
  },
  {
    "chat_id": -10012345678,
    "type": "markdown",
    "text": "**每日签到**"
  }
]
```

### 排查要点
- **Session 失效**：如果账号退出了所有会话，`TELEGRAM_SESSION` 会失效，需要重新生成。
- **Chat ID 错误**：确保 `chat_id` 正确。个人 ID 为正数，群组/频道 ID 通常以 `-100` 开头。
