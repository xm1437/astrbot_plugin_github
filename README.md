<div align="center">

# 🐙 astrbot_plugin_github

**让 AstrBot 机器人管理你的 GitHub**

通过经典 Token 实现 GitHub 仓库、Issue、Pull Request、搜索等全功能管理，支持自然语言与手动指令双模式调用

[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.16-blueviolet?logo=github)](https://github.com/AstrBotDevs/AstrBot)
[![Python](https://img.shields.io/badge/Python-%3E%3D3.12-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Version](https://img.shields.io/badge/version-v2.0.0-success)](#changelog)
[![License](https://img.shields.io/badge/license-MIT-green)](#license)

</div>

---

> 💬 **直接对机器人说"帮我看看我的仓库"，它就会自动调用 GitHub API。** 也支持 `/gh` 手动指令精确操作。

## ✨ 功能特性

- 🔐 **Token 认证** — 使用 GitHub Classic Token，支持管理面板配置或指令动态设置，启动时自动验证
- 📦 **仓库管理** — 列出仓库（按更新排序）、查看详情（star/fork/语言/推送时间）、创建公开或私有仓库
- 🐛 **Issue 管理** — 列出 Issue（自动过滤 PR）、创建 Issue（支持正文）、对 Issue/PR 发表评论
- 🔀 **Pull Request** — 列出 PR（含草稿标记）、查看 PR 详情（状态/分支/合并情况/评论数）
- 🔍 **搜索** — 按关键词搜索仓库（按 star 排序）或搜索代码，支持 GitHub 搜索限定符
- 🤖 **自然语言调用** — 注册 12 个 LLM 工具，说话即可操作，需支持 Function Calling 的模型
- ⌨️ **手动指令** — `/gh` 指令组，14 条子命令，精确控制每个参数，不依赖模型能力
- ⚡ **异步请求** — 基于 `aiohttp`，不阻塞机器人事件循环
- 🛡️ **完善错误处理** — 401/403/404/422/429 全覆盖，速率限制时自动显示重置时间
- 🧩 **智能补全** — 仓库名支持简写，只写仓库名时自动补全为当前用户的 `owner/repo`

## 📖 目录

- [快速开始](#-快速开始)
- [配置 Token](#-配置-token)
- [手动指令](#-手动指令)
- [自然语言调用](#-自然语言调用)
- [LLM 工具参考](#-llm-工具参考)
- [使用前提](#-使用前提)
- [配置项](#-配置项)
- [技术架构](#-技术架构)
- [API 端点说明](#-api-端点说明)
- [错误处理](#-错误处理)
- [安全提示](#-安全提示)
- [FAQ](#-faq)
- [Changelog](#changelog)
- [License](#license)

## 🚀 快速开始

三步即可用：

**1. 安装插件** — 将 `astrbot_plugin_github` 文件夹放入 AstrBot 的 `data/plugins/` 目录，重启 AstrBot

```
data/plugins/
└── astrbot_plugin_github/
    ├── main.py              # 插件主逻辑
    ├── metadata.yaml        # 插件元数据
    ├── _conf_schema.json    # 配置项定义
    ├── requirements.txt     # Python 依赖
    └── README.md            # 本文档
```

**2. 配置 Token** — 在 AstrBot 管理面板 → 插件管理 → 本插件配置中填入 GitHub Token（详见下方[配置 Token](#-配置-token)）

**3. 开始使用** — 发送 `/gh whoami` 验证，或直接对机器人说"我的 GitHub 账号信息"

## 🔑 配置 Token

插件需要一个 GitHub Classic Token（Personal Access Token, classic）才能调用 API。

### 生成 Token

1. 登录 GitHub，进入 **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)**
2. 点击 **Generate new token (classic)**
3. 填写 Note（如 `AstrBot GitHub 插件`），设置过期时间
4. 勾选以下 scope：

   | Scope | 用途 |
   |-------|------|
   | `repo` | 仓库读写、Issue、PR 操作（完整勾选） |
   | `user` | 读取账户信息（用户名、邮箱等） |

5. 点击 **Generate token**，复制生成的 Token（格式如 `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`）

### 配置方式

二选一：

| 方式 | 操作 | 适用场景 |
|------|------|---------|
| 管理面板 | AstrBot WebUI → 插件管理 → 本插件配置 → `token` 字段 | 推荐，Token 不出现在聊天记录 |
| 指令设置 | 管理员在**私聊**中发送 `/gh settoken ghp_xxxxxxxx` | 临时更换 Token |

配置后插件会在启动时自动验证 Token 有效性，日志中可见验证结果。

## ⌨️ 手动指令

所有指令在 `/gh` 指令组下。发送 `/gh` 可查看完整帮助。

### 账户

| 指令 | 说明 | 示例 |
|------|------|------|
| `/gh whoami` | 查看账户信息并验证 Token | `/gh whoami` |
| `/gh rate` | 查看 API 速率限制剩余额度 | `/gh rate` |

### 仓库

| 指令 | 说明 | 示例 |
|------|------|------|
| `/gh repos [all\|public\|private]` | 列出我的仓库，按更新时间排序 | `/gh repos private` |
| `/gh repo <owner/repo>` | 查看仓库详情 | `/gh repo octocat/Hello-World` |
| `/gh newrepo <名称> [描述]` | 创建私有仓库（自动初始化 README） | `/gh newrepo my-project 我的项目` |
| `/gh newpub <名称> [描述]` | 创建公开仓库（自动初始化 README） | `/gh newpub demo 演示项目` |

### Issue

| 指令 | 说明 | 示例 |
|------|------|------|
| `/gh issues <owner/repo> [open\|closed\|all]` | 列出仓库的 Issue | `/gh issues octocat/Hello-World open` |
| `/gh newissue <owner/repo> <标题>` | 创建 Issue | `/gh newissue octocat/Hello-World 发现一个Bug` |
| `/gh comment <owner/repo> <编号> <内容>` | 评论 Issue 或 PR | `/gh comment octocat/Hello-World 42 已修复` |

### Pull Request

| 指令 | 说明 | 示例 |
|------|------|------|
| `/gh prs <owner/repo> [open\|closed\|all]` | 列出仓库的 PR | `/gh prs octocat/Hello-World` |
| `/gh pr <owner/repo> <编号>` | 查看 PR 详情 | `/gh pr octocat/Hello-World 1` |

### 搜索

| 指令 | 说明 | 示例 |
|------|------|------|
| `/gh search repo <关键词>` | 搜索仓库（按 star 排序） | `/gh search repo python web` |
| `/gh search code <关键词>` | 搜索代码 | `/gh search code def main` |

### 配置

| 指令 | 说明 | 权限 |
|------|------|------|
| `/gh settoken <token>` | 设置 GitHub Token 并立即验证 | 仅管理员 |

> 💡 **仓库名简写**：如果是你自己的仓库，`<owner/repo>` 可只写仓库名，插件会自动补全 owner。例如你的用户名是 `alice`，`/gh repo myproject` 等价于 `/gh repo alice/myproject`。

## 🤖 自然语言调用

配置好支持 Function Calling 的模型后，直接用自然语言对话即可。LLM 会自动选择合适的工具并填充参数，拿到 API 返回后用自然语言组织回复。

### 对话示例

| 你说的话 | 机器人会做的事 |
|---------|--------------|
| "我的 GitHub 账号信息" | 调用 `github_whoami` 返回账户资料 |
| "Token 还有效吗" | 调用 `github_whoami` 验证 |
| "看看我有哪些仓库" | 调用 `github_list_repos` 列出仓库 |
| "我有哪些私有仓库" | 调用 `github_list_repos`（`repo_type=private`） |
| "API 还能调用多少次" | 调用 `github_rate_limit` 查询额度 |
| "octocat/Hello-World 有多少 star" | 调用 `github_repo_info` 返回详情 |
| "帮我创建一个叫 my-project 的私有仓库" | 调用 `github_create_repo`（`private=true`） |
| "建个公开仓库叫 demo" | 调用 `github_create_repo`（`private=false`） |
| "这个仓库有哪些 open 的 issue" | 调用 `github_list_issues` 列出 Issue |
| "给 octocat/Hello-World 提个 bug，标题是登录失败" | 调用 `github_create_issue` 创建 Issue |
| "在 42 号 issue 下评论：已修复" | 调用 `github_comment_issue` 发表评论 |
| "看看待合并的 PR" | 调用 `github_list_prs` 列出 PR |
| "octocat/Hello-World 的 1 号 PR 什么情况" | 调用 `github_pr_info` 返回详情 |
| "搜一下 GitHub 上关于 python web 的热门仓库" | 调用 `github_search` 搜索仓库 |
| "搜一下哪里用了 addClass 这个函数" | 调用 `github_search` 搜索代码 |

### 工作流程

```
用户发送自然语言消息
        ↓
LLM 分析意图 + 匹配工具
        ↓
调用 github_xxx 工具（传入参数）
        ↓
插件请求 GitHub API → 返回数据
        ↓
LLM 基于数据组织自然语言回复
        ↓
用户收到回复
```

## 📋 LLM 工具参考

插件注册了 12 个 LLM 工具，覆盖全部功能。工具描述中包含触发场景以帮助模型准确判断调用时机。

| 工具名 | 参数 | 说明 |
|--------|------|------|
| `github_whoami` | 无 | 查看账户信息，验证 Token |
| `github_rate_limit` | 无 | 查看 API 速率限制 |
| `github_list_repos` | `repo_type` (string) | 列出仓库 |
| `github_repo_info` | `repository` (string) | 查看仓库详情 |
| `github_create_repo` | `name` (string), `description` (string), `private` (boolean) | 创建仓库 |
| `github_list_issues` | `repository` (string), `state` (string) | 列出 Issue |
| `github_create_issue` | `repository` (string), `title` (string), `body` (string) | 创建 Issue |
| `github_comment_issue` | `repository` (string), `number` (number), `body` (string) | 评论 Issue/PR |
| `github_list_prs` | `repository` (string), `state` (string) | 列出 PR |
| `github_pr_info` | `repository` (string), `number` (number) | 查看 PR 详情 |
| `github_search` | `kind` (string), `query` (string) | 搜索仓库或代码 |

> 工具参数 schema 通过 docstring 的 `Args:` 块定义，AstrBot 会自动解析并传给 LLM。

## 📋 使用前提

| 项目 | 要求 |
|------|------|
| AstrBot | v4.16 及以上 |
| Python | 3.12 及以上 |
| 依赖 | `aiohttp >= 3.8.0`（自动安装） |
| GitHub Token | Classic Token，需勾选 `repo` + `user` scope |
| 模型（自然语言调用） | 需支持 Function Calling |

**推荐的 Function Calling 模型：**

- OpenAI：GPT-4o / GPT-4.1 系列
- Anthropic：Claude 3.5 Sonnet 及以上
- Deepseek：deepseek-chat（v3）
- 阿里云：Qwen 3 系列

> 模型不支持 Function Calling 时会自动降级：工具不生效，但 `/gh` 手动指令仍可正常使用。也可在 WebUI → 配置 → 函数调用中手动开关工具。

## ⚙️ 配置项

插件配置通过 `_conf_schema.json` 定义，在 AstrBot 管理面板中可视化编辑。

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `token` | string | `""` | GitHub Personal Access Token (classic) |
| `repos_per_page` | int | `5` | 列出仓库/Issue/PR 时最多显示条数（1-30） |

`repos_per_page` 控制列表类命令的返回条数。设置过大会导致消息过长，建议保持 3-10。

## 🏗️ 技术架构

插件基于 AstrBot `Star` 基类开发，采用四层架构，手动指令与 LLM 工具共享同一套业务逻辑：

```
┌──────────────────────────────────────────────────┐
│  手动指令层   /gh whoami  /gh repos  /gh search  │  @filter.command_group("gh")
│                  14 条子命令                      │  @gh.command(...)
├──────────────────────────────────────────────────┤
│  LLM 工具层   github_whoami  github_search  ...  │  @filter.llm_tool(name=...)
│                  12 个工具                        │  docstring Args 块定义参数
├──────────────────────────────────────────────────┤
│  业务逻辑层   _do_whoami()  _do_search()  ...     │  返回格式化字符串
│              手动指令与 LLM 工具共享调用            │  统一数据处理
├──────────────────────────────────────────────────┤
│  HTTP 层      aiohttp + GitHub REST API v3        │  Bearer 认证
│              _request() 统一封装                   │  错误处理 / 速率限制
└──────────────────────────────────────────────────┘
```

### 设计要点

- **业务逻辑复用**：每个功能抽取为 `_do_xxx` 内部方法，返回格式化字符串。手动指令和 LLM 工具各自调用同一方法，避免代码重复
- **异步 HTTP**：使用 `aiohttp.ClientSession`，会话复用提升性能，`terminate()` 时正确关闭
- **用户名缓存**：首次调用 `/user` 后缓存 `login`，后续仓库名简写时无需重复请求
- **docstring 驱动**：LLM 工具的参数 schema 通过 docstring 的 `Args:` 块自动解析，工具描述包含触发场景示例
- **Token 热更新**：`settoken` 后立即关闭旧 session 并验证新 Token，无需重启

## 🔌 API 端点说明

插件调用的 GitHub REST API v3 端点：

| 功能 | 方法 | 端点 |
|------|------|------|
| 验证 Token / 获取用户信息 | GET | `/user` |
| 查询速率限制 | GET | `/rate_limit` |
| 列出仓库 | GET | `/user/repos` |
| 查看仓库详情 | GET | `/repos/{owner}/{repo}` |
| 创建仓库 | POST | `/user/repos` |
| 列出 Issue | GET | `/repos/{owner}/{repo}/issues` |
| 创建 Issue | POST | `/repos/{owner}/{repo}/issues` |
| 评论 Issue/PR | POST | `/repos/{owner}/{repo}/issues/{number}/comments` |
| 列出 PR | GET | `/repos/{owner}/{repo}/pulls` |
| 查看 PR 详情 | GET | `/repos/{owner}/{repo}/pulls/{number}` |
| 搜索仓库 | GET | `/search/repositories` |
| 搜索代码 | GET | `/search/code` |

所有请求携带以下 Header：

```
Authorization: Bearer <token>
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28
```

## ⚠️ 错误处理

插件对 GitHub API 返回的错误状态码做了人性化处理：

| 状态码 | 处理方式 |
|--------|---------|
| 401 | 提示 Token 无效或已过期，建议检查配置 |
| 403（速率限制） | 提示已达限制，显示重置时间（从 `X-RateLimit-Reset` 头解析） |
| 403（权限不足） | 提示权限不足，建议检查 Token scope 是否包含 `repo` |
| 404 | 提示资源不存在或无权访问，建议检查 owner/repo |
| 422 | 提示参数有误，附上 GitHub 返回的错误信息 |
| 429 | 提示请求过于频繁被限流，建议稍后再试 |

此外，网络异常（`aiohttp.ClientError`）会被捕获并返回友好提示，不会导致机器人崩溃。

## 🛡️ 安全提示

- ⚠️ `settoken` 指令限管理员权限，但 Token 在聊天记录中可见，**务必在私聊中使用**
- 🔒 建议优先通过管理面板配置 Token，避免明文传输
- 📢 `newpub` 和 `github_create_repo`（`private=false`）会创建公开仓库，确认不含敏感信息后再创建
- 🚨 Token 泄露后请立即在 GitHub → Settings → Developer settings → Personal access tokens 中撤销并重新生成
- ⏰ 建议 Token 设置合理的过期时间，定期轮换

## ❓ FAQ

**Q: 插件加载后日志显示 "Token 验证失败" 怎么办？**

A: 检查 Token 是否正确复制（注意不要多空格），确认 Token 未过期，确认勾选了 `repo` scope。

**Q: 自然语言调用没反应，机器人不调用工具？**

A: 确认当前使用的 LLM 模型支持 Function Calling（如 GPT-4o、Claude 3.5）。在 WebUI → 配置 → 函数调用中检查 `github_*` 工具是否已启用。不支持 FC 的模型会自动降级，手动指令仍可用。

**Q: 列表只返回 5 条，怎么看更多？**

A: 在管理面板中将 `repos_per_page` 调大（最大 30）。注意条数过多会导致消息过长。

**Q: 创建仓库时报 422 错误？**

A: 通常是仓库名不合法或已存在同名仓库。仓库名不能包含空格和大写字母（GitHub 会自动转小写），确保名称唯一。

**Q: 搜索代码时报错？**

A: 代码搜索需要 Token 认证，且限制为每分钟 10 次。确认 Token 有效，搜索关键词至少包含一个搜索词（纯限定符如 `language:go` 无效）。

**Q: 可以管理组织的仓库吗？**

A: 列出仓库（`/gh repos`）仅返回个人仓库。查看/操作指定仓库时支持组织仓库，只需用 `org-name/repo-name` 格式传入即可。

**Q: Token 存储在哪里？**

A: 通过管理面板配置时存储在 `data/config/astrbot_plugin_github_config.json`。通过 `settoken` 设置时会自动持久化到同一文件。

## Changelog

### v2.0.0

- 新增 12 个 LLM 工具（`@filter.llm_tool`），支持自然语言调用
- 重构为四层架构，手动指令与 LLM 工具共享业务逻辑
- 新增 `/gh settoken` 指令动态设置 Token（仅管理员）
- 新增仓库名简写支持（只写仓库名自动补全 owner）
- 新增 `github_create_issue` 的 `body` 参数支持
- 完善错误处理，覆盖 401/403/404/422/429

### v1.0.0

- 初始版本
- 支持 `/gh` 指令组：whoami、rate、repos、repo、newrepo、newpub、issues、newissue、comment、prs、pr、search
- 基于 `aiohttp` 异步请求 GitHub REST API
- 通过 `_conf_schema.json` 管理 Token 配置

## License

MIT
