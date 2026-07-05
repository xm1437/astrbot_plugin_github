# AstrBot GitHub 管理助手

通过经典 Token (Personal Access Token, classic) 让机器人管理 GitHub 仓库。

## 功能

- 🔐 账户：验证 Token、查看账户信息、速率限制
- 📦 仓库：列出 / 查看详情 / 创建（公开或私有）/ 删除
- 🐛 Issue：列出 / 创建 / 评论
- 🔀 Pull Request：列出 / 查看详情
- 🔍 搜索：仓库 / 代码

## 安装

将插件放入 AstrBot 的 `data/plugins/` 目录即可。

## 配置

在 `data/config/` 目录下创建 `astrbot_plugin_github_config.json`：

```json
{
  "token": "ghp_xxxxxxxxxxxx",
  "repos_per_page": 5
}
```

- `token`: GitHub Personal Access Token (classic)，需要 repo 权限
- `repos_per_page`: 列出仓库时每页数量

## 依赖

```
aiohttp
```

## 使用

安装并配置好 Token 后，机器人即可通过命令管理 GitHub 仓库。

---

Made with ❤️ for AstrBot
