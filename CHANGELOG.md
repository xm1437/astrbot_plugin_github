# Changelog

## v2.1.0 (2026-07-07)

### 🚀 新增
- 全面支持 LLM Function Calling，所有功能均作为 `llm_tool` 暴露给 LLM 自动调用
- 新增自然语言交互方式：直接对话即可操作 GitHub（如"帮我看看我的仓库""创建一个叫 xxx 的项目"）
- 新增 `github_whoami` / `github_rate_limit` / `github_list_repos` / `github_repo_info` / `github_create_repo` 等 10 个 LLM 工具
- 新增搜索功能：`/gh search repo <关键词>` 和 `/gh search code <关键词>`
- 新增 Token 权限 scope 显示（whoami 命令返回）

### 🔧 优化
- 重构 HTTP 请求层：统一错误处理，友好的错误提示（区分 401/403/404/422/429）
- 仓库列表支持更丰富的筛选类型（all/public/private/forks/sources/member）
- 创建仓库默认初始化 README（auto_init）
- PR 详情显示草稿状态和审查评论数
- 速率限制查询显示具体重置时间
- Issue 列表自动过滤 Pull Request（仅显示真正的 Issue）
- 仓库名支持简写（只有仓库名时自动补全当前用户 owner）
- 添加 per_page 配置项，控制列表返回数量（1-30）

### 🐛 修复
- 修复 `_request` 返回非 JSON 响应时的解析异常
- 修复速率限制 403 的判断逻辑，区分 Token 权限不足与 API 限流
- 修复 aiohttp session 生命周期管理问题

---

## v1.0.0 (2026-07-02)

- 首次发布
- 支持 `/gh` 手动指令组：whoami、rate、repos、repo、newrepo、newpub、issues、newissue、comment、prs、pr、settoken
- 基于经典 Personal Access Token 认证
