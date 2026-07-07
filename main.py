"""
AstrBot 插件：GitHub 管理助手
通过经典 Token (Personal Access Token, classic) 让机器人管理你的 GitHub。

支持两种调用方式：
1. 手动指令：/gh whoami、/gh repos 等（适合精确操作）
2. 自然语言：直接对机器人说"帮我看看我的仓库""创建一个叫 xxx 的仓库"，
   LLM 会自动调用对应工具（需使用支持 Function Calling 的模型）

功能覆盖：
- 账户：验证 Token、查看账户信息、速率限制
- 仓库：列出 / 查看详情 / 创建（公开或私有）
- Issue：列出 / 创建 / 评论
- Pull Request：列出 / 查看详情
- 搜索：仓库 / 代码
"""

from datetime import datetime

import aiohttp

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import AstrBotConfig, logger

GITHUB_API_BASE = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"


@register(
    "astrbot_plugin_github",
    "AstrBotUser",
    "通过经典 Token 管理 GitHub：仓库、Issue、Pull Request、搜索等。支持自然语言调用。",
    "2.1.0",
)
class GitHubPlugin(Star):
    """GitHub 管理助手插件。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.token: str = config.get("token", "") or ""
        try:
            self.per_page: int = max(1, min(30, int(config.get("repos_per_page", 5))))
        except (TypeError, ValueError):
            self.per_page = 5
        self._session: aiohttp.ClientSession | None = None
        self._login: str | None = None  # 缓存当前认证用户名

    # ================================================================== #
    #  HTTP / GitHub API 封装
    # ================================================================== #
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_body: dict | None = None,
    ):
        """统一请求方法。返回 (success, data, headers)。"""
        if not self.token:
            return (
                False,
                "尚未配置 GitHub Token。请在管理面板的插件配置中填写，"
                "或由管理员使用 /gh settoken <token> 设置。",
                {},
            )
        url = f"{GITHUB_API_BASE}{path}"
        session = await self._get_session()
        try:
            async with session.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                try:
                    data = await resp.json()
                except Exception:
                    data = await resp.text()
                headers = dict(resp.headers)
                if resp.status >= 400:
                    return False, self._build_error_msg(resp.status, data, headers), headers
                return True, data, headers
        except aiohttp.ClientError as e:
            return False, f"网络请求失败：{e}", {}
        except Exception as e:
            return False, f"请求异常：{e}", {}

    def _build_error_msg(self, status: int, data, headers: dict) -> str:
        if isinstance(data, dict):
            err_msg = data.get("message", "") or str(data)
        else:
            err_msg = str(data)
        if status == 401:
            return "Token 无效或已过期（401），请检查配置的 Token 是否正确。"
        if status == 403:
            remaining = headers.get("X-RateLimit-Remaining") or headers.get("x-ratelimit-remaining")
            if remaining == "0":
                reset = headers.get("X-RateLimit-Reset") or headers.get("x-ratelimit-reset")
                tip = ""
                if reset:
                    try:
                        tip = f"，将在 {datetime.fromtimestamp(int(reset)).strftime('%H:%M:%S')} 重置"
                    except (ValueError, OSError):
                        tip = ""
                return f"已达 GitHub API 速率限制（403）{tip}，请稍后再试。"
            return f"权限不足（403）：{err_msg}\n请检查 Token 是否勾选了所需 scope（如 repo）。"
        if status == 404:
            return "资源不存在或无权访问（404），请检查 owner/repo 是否正确。"
        if status == 422:
            return f"参数有误（422）：{err_msg}"
        if status == 429:
            return "请求过于频繁被限流（429），请稍后再试。"
        return f"请求失败（{status}）：{err_msg}"

    async def _parse_repo(self, repo_str: str):
        """解析 owner/repo。只给仓库名时用当前认证用户作为 owner。"""
        repo_str = repo_str.strip()
        if "/" in repo_str:
            owner, repo = repo_str.split("/", 1)
            return owner.strip(), repo.strip()
        if not self._login:
            ok, data, _ = await self._request("GET", "/user")
            if ok and isinstance(data, dict):
                self._login = data.get("login")
            else:
                return None, None
        return self._login, repo_str

    # ================================================================== #
    #  生命周期
    # ================================================================== #
    async def initialize(self):
        if not self.token:
            logger.warning("[GitHub插件] 尚未配置 Token，请在管理面板配置或使用 /gh settoken 设置。")
            return
        ok, data, _ = await self._request("GET", "/user")
        if ok and isinstance(data, dict):
            self._login = data.get("login")
            logger.info(f"[GitHub插件] Token 验证成功，当前用户：{self._login}")
        else:
            logger.warning(f"[GitHub插件] Token 验证失败：{data}")

    async def terminate(self):
        if self._session and not self._session.closed:
            await self._session.close()
        logger.info("[GitHub插件] 已卸载。")

    # ================================================================== #
    #  辅助
    # ================================================================== #
    def _help_text(self) -> str:
        return (
            "GitHub 管理助手 · 命令列表\n"
            "━━━━━━━━━━━━━━━━\n"
            "【账户】\n"
            "/gh whoami — 查看账户信息（验证 Token）\n"
            "/gh rate — 查看 API 速率限制\n"
            "【仓库】\n"
            "/gh repos [all|public|private] — 列出我的仓库\n"
            "/gh repo <owner/repo> — 查看仓库详情\n"
            "/gh newrepo <名称> [描述] — 创建私有仓库\n"
            "/gh newpub <名称> [描述] — 创建公开仓库\n"
            "【Issue】\n"
            "/gh issues <owner/repo> [open|closed|all] — 列出 Issue\n"
            "/gh newissue <owner/repo> <标题> — 创建 Issue\n"
            "/gh comment <owner/repo> <编号> <内容> — 评论 Issue/PR\n"
            "【Pull Request】\n"
            "/gh prs <owner/repo> [open|closed|all] — 列出 PR\n"
            "/gh pr <owner/repo> <编号> — 查看 PR 详情\n"
            "【搜索】\n"
            "/gh search repo <关键词> — 搜索仓库\n"
            "/gh search code <关键词> — 搜索代码\n"
            "【配置】\n"
            "/gh settoken <token> — 设置 Token（仅管理员，建议私聊）\n"
            "━━━━━━━━━━━━━━━━\n"
            "💡 你也可以直接用自然语言，例如：\n"
            "  “帮我看看我的仓库”\n"
            "  “创建一个叫 my-project 的私有仓库”\n"
            "  “octocat/Hello-World 有哪些 open 的 issue”"
        )

    @staticmethod
    def _fmt_time(iso: str | None) -> str:
        if not iso:
            return "无"
        try:
            return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            return iso

    # ================================================================== #
    #  核心业务逻辑（返回字符串，供指令和 llm_tool 共用）
    # ================================================================== #
    async def _do_whoami(self) -> str:
        ok, data, headers = await self._request("GET", "/user")
        if not ok:
            return f"验证失败：{data}"
        if isinstance(data, dict):
            self._login = data.get("login")
        scopes = headers.get("X-OAuth-Scopes") or headers.get("x-oauth-scopes") or "无"
        return (
            "GitHub 账户信息\n"
            f"用户名：{data.get('login', '未知')}\n"
            f"昵称：{data.get('name') or '未设置'}\n"
            f"ID：{data.get('id', '未知')}\n"
            f"公开仓库：{data.get('public_repos', 0)} 个\n"
            f"关注者：{data.get('followers', 0)} | 正在关注：{data.get('following', 0)}\n"
            f"创建时间：{self._fmt_time(data.get('created_at'))}\n"
            f"Token 权限(scope)：{scopes}"
        )

    async def _do_rate_limit(self) -> str:
        ok, data, _ = await self._request("GET", "/rate_limit")
        if not ok:
            return f"查询失败：{data}"
        core = data.get("resources", {}).get("core", {}) if isinstance(data, dict) else {}
        search = data.get("resources", {}).get("search", {}) if isinstance(data, dict) else {}
        reset_core = core.get("reset")
        reset_str = ""
        if reset_core:
            try:
                reset_str = datetime.fromtimestamp(int(reset_core)).strftime("%H:%M:%S")
            except (ValueError, OSError):
                reset_str = ""
        return (
            "GitHub API 速率限制\n"
            f"核心接口：{core.get('remaining', '?')}/{core.get('limit', '?')} 次/小时"
            + (f"（{reset_str} 重置）" if reset_str else "")
            + "\n"
            f"搜索接口：{search.get('remaining', '?')}/{search.get('limit', '?')} 次/分钟"
        )

    async def _do_list_repos(self, repo_type: str = "all") -> str:
        allowed = {"all", "public", "private", "forks", "sources", "member"}
        if repo_type not in allowed:
            repo_type = "all"
        ok, data, _ = await self._request(
            "GET", "/user/repos",
            params={"type": repo_type, "sort": "updated", "direction": "desc",
                    "per_page": self.per_page, "page": 1},
        )
        if not ok:
            return f"获取失败：{data}"
        if not data:
            return "没有找到符合条件的仓库。"
        lines = [f"我的仓库（类型：{repo_type}，按更新时间排序，前 {len(data)} 个）\n"]
        for r in data:
            vis = "私有" if r.get("private") else "公开"
            star = r.get("stargazers_count", 0)
            lang = r.get("language") or "-"
            lines.append(
                f"• {r.get('full_name')} [{vis}] ★{star} {lang}\n"
                f"  {(r.get('description') or '无描述')}"
            )
        return "\n".join(lines)

    async def _do_repo_info(self, repo_str: str) -> str:
        owner, repo = await self._parse_repo(repo_str)
        if not owner:
            return "无法确定仓库 owner，请使用 owner/repo 格式，或先验证 Token。"
        ok, data, _ = await self._request("GET", f"/repos/{owner}/{repo}")
        if not ok:
            return f"获取失败：{data}"
        vis = "私有" if data.get("private") else "公开"
        return (
            f"仓库详情：{data.get('full_name')}\n"
            f"可见性：{vis} | 默认分支：{data.get('default_branch', '-')}\n"
            f"描述：{data.get('description') or '无'}\n"
            f"语言：{data.get('language') or '-'} | 主题：{', '.join(data.get('topics', [])) or '无'}\n"
            f"★ {data.get('stargazers_count', 0)} | ⑂ {data.get('forks_count', 0)} | "
            f"Issue/PR {data.get('open_issues_count', 0)}\n"
            f"创建：{self._fmt_time(data.get('created_at'))} | "
            f"最近推送：{self._fmt_time(data.get('pushed_at'))}\n"
            f"链接：{data.get('html_url', '')}"
        )

    async def _do_create_repo(self, name: str, desc: str, private: bool) -> str:
        if not name:
            return "请提供仓库名称。"
        body = {"name": name, "private": private, "auto_init": True}
        if desc:
            body["description"] = desc
        ok, data, _ = await self._request("POST", "/user/repos", json_body=body)
        if not ok:
            return f"创建失败：{data}"
        vis = "私有" if private else "公开"
        return (
            f"仓库创建成功（{vis}）\n"
            f"名称：{data.get('full_name')}\n"
            f"链接：{data.get('html_url', '')}\n"
            f"已自动初始化 README。"
        )

    async def _do_list_issues(self, repo_str: str, state: str = "open") -> str:
        owner, repo = await self._parse_repo(repo_str)
        if not owner:
            return "无法确定仓库 owner，请使用 owner/repo 格式。"
        if state not in ("open", "closed", "all"):
            state = "open"
        ok, data, _ = await self._request(
            "GET", f"/repos/{owner}/{repo}/issues",
            params={"state": state, "sort": "created", "direction": "desc", "per_page": self.per_page},
        )
        if not ok:
            return f"获取失败：{data}"
        real_issues = [i for i in data if "pull_request" not in i]
        if not real_issues:
            return f"{owner}/{repo} 没有 {state} 状态的 Issue。"
        lines = [f"{owner}/{repo} 的 Issue（状态：{state}，前 {len(real_issues)} 个）\n"]
        for i in real_issues:
            labels = ",".join(l.get("name", "") for l in i.get("labels", [])) or "无"
            lines.append(
                f"#{i.get('number')} {i.get('title')}\n"
                f"  by {i.get('user', {}).get('login', '?')} | 标签：{labels} | "
                f"{self._fmt_time(i.get('created_at'))}"
            )
        return "\n".join(lines)

    async def _do_create_issue(self, repo_str: str, title: str, body: str = "") -> str:
        owner, repo = await self._parse_repo(repo_str)
        if not owner:
            return "无法确定仓库 owner，请使用 owner/repo 格式。"
        if not title:
            return "请提供 Issue 标题。"
        payload = {"title": title}
        if body:
            payload["body"] = body
        ok, data, _ = await self._request("POST", f"/repos/{owner}/{repo}/issues", json_body=payload)
        if not ok:
            return f"创建失败：{data}"
        return (
            f"Issue 创建成功\n"
            f"#{data.get('number')} {data.get('title')}\n"
            f"链接：{data.get('html_url', '')}"
        )

    async def _do_comment(self, repo_str: str, number: int, body: str) -> str:
        owner, repo = await self._parse_repo(repo_str)
        if not owner:
            return "无法确定仓库 owner，请使用 owner/repo 格式。"
        if not body:
            return "请提供评论内容。"
        ok, data, _ = await self._request(
            "POST", f"/repos/{owner}/{repo}/issues/{number}/comments", json_body={"body": body},
        )
        if not ok:
            return f"评论失败：{data}"
        return f"评论成功（#{number}）\n链接：{data.get('html_url', '')}"

    async def _do_list_prs(self, repo_str: str, state: str = "open") -> str:
        owner, repo = await self._parse_repo(repo_str)
        if not owner:
            return "无法确定仓库 owner，请使用 owner/repo 格式。"
        if state not in ("open", "closed", "all"):
            state = "open"
        ok, data, _ = await self._request(
            "GET", f"/repos/{owner}/{repo}/pulls",
            params={"state": state, "sort": "created", "direction": "desc", "per_page": self.per_page},
        )
        if not ok:
            return f"获取失败：{data}"
        if not data:
            return f"{owner}/{repo} 没有 {state} 状态的 PR。"
        lines = [f"{owner}/{repo} 的 Pull Request（状态：{state}，前 {len(data)} 个）\n"]
        for p in data:
            draft = " [草稿]" if p.get("draft") else ""
            head = p.get("head", {}).get("ref", "?")
            base = p.get("base", {}).get("ref", "?")
            lines.append(
                f"#{p.get('number')} {p.get('title')}{draft}\n"
                f"  {head} → {base} | by {p.get('user', {}).get('login', '?')} | "
                f"{self._fmt_time(p.get('created_at'))}"
            )
        return "\n".join(lines)

    async def _do_pr_info(self, repo_str: str, number: int) -> str:
        owner, repo = await self._parse_repo(repo_str)
        if not owner:
            return "无法确定仓库 owner，请使用 owner/repo 格式。"
        ok, data, _ = await self._request("GET", f"/repos/{owner}/{repo}/pulls/{number}")
        if not ok:
            return f"获取失败：{data}"
        merged = data.get("merged_at")
        state = data.get("state", "?")
        if merged:
            state = "merged"
        head = data.get("head", {}).get("ref", "?")
        base = data.get("base", {}).get("ref", "?")
        draft = " [草稿]" if data.get("draft") else ""
        return (
            f"PR #{data.get('number')} {data.get('title')}\n"
            f"状态：{state}{draft} | {head} → {base}\n"
            f"作者：{data.get('user', {}).get('login', '?')} | "
            f"评论数：{data.get('comments', 0)} + {data.get('review_comments', 0)} 审查评论\n"
            f"创建：{self._fmt_time(data.get('created_at'))} | "
            f"合并：{self._fmt_time(merged) if merged else '未合并'}\n"
            f"描述：{data.get('body') or '无'}\n"
            f"链接：{data.get('html_url', '')}"
        )

    async def _do_search(self, kind: str, query: str) -> str:
        if not query:
            return "请提供搜索关键词。"
        if kind in ("repo", "仓库", "repository"):
            ok, data, _ = await self._request(
                "GET", "/search/repositories",
                params={"q": query, "sort": "stars", "order": "desc", "per_page": self.per_page},
            )
            if not ok:
                return f"搜索失败：{data}"
            items = data.get("items", []) if isinstance(data, dict) else []
            total = data.get("total_count", 0) if isinstance(data, dict) else 0
            if not items:
                return f"未找到匹配「{query}」的仓库（共 {total} 条结果）。"
            lines = [f"搜索仓库「{query}」（共 {total} 条，显示前 {len(items)} 个）\n"]
            for it in items:
                lines.append(
                    f"• {it.get('full_name')} ★{it.get('stargazers_count', 0)}\n"
                    f"  {(it.get('description') or '无描述')}\n"
                    f"  {it.get('html_url', '')}"
                )
            return "\n".join(lines)
        elif kind in ("code", "代码"):
            ok, data, _ = await self._request(
                "GET", "/search/code",
                params={"q": query, "per_page": self.per_page},
            )
            if not ok:
                return f"搜索失败：{data}"
            items = data.get("items", []) if isinstance(data, dict) else []
            total = data.get("total_count", 0) if isinstance(data, dict) else 0
            if not items:
                return f"未找到匹配「{query}」的代码（共 {total} 条结果）。"
            lines = [f"搜索代码「{query}」（共 {total} 条，显示前 {len(items)} 个）\n"]
            for it in items:
                repo_name = it.get("repository", {}).get("full_name", "?")
                path = it.get("path", "?")
                lines.append(f"• {repo_name} : {path}\n  {it.get('html_url', '')}")
            return "\n".join(lines)
        else:
            return "搜索类型仅支持 repo（仓库）或 code（代码）。"

    # ================================================================== #
    #  手动指令组 /gh（保留，适合精确操作）
    # ================================================================== #
    @filter.command_group("gh")
    async def gh(self, event: AstrMessageEvent):
        """GitHub 管理助手"""
        yield event.plain_result(self._help_text())

    @gh.command("help")
    async def gh_help(self, event: AstrMessageEvent):
        """查看 GitHub 插件帮助"""
        yield event.plain_result(self._help_text())

    @gh.command("whoami")
    async def cmd_whoami(self, event: AstrMessageEvent):
        """查看 GitHub 账户信息"""
        yield event.plain_result(await self._do_whoami())

    @gh.command("rate")
    async def cmd_rate(self, event: AstrMessageEvent):
        """查看 API 速率限制"""
        yield event.plain_result(await self._do_rate_limit())

    @gh.command("repos")
    async def cmd_repos(self, event: AstrMessageEvent, repo_type: str = "all"):
        """列出我的仓库"""
        yield event.plain_result(await self._do_list_repos(repo_type))

    @gh.command("repo")
    async def cmd_repo(self, event: AstrMessageEvent, repo_str: str):
        """查看仓库详情"""
        yield event.plain_result(await self._do_repo_info(repo_str))

    @gh.command("newrepo")
    async def cmd_newrepo(self, event: AstrMessageEvent, name: str, desc: str = ""):
        """创建私有仓库"""
        yield event.plain_result(await self._do_create_repo(name, desc, private=True))

    @gh.command("newpub")
    async def cmd_newpub(self, event: AstrMessageEvent, name: str, desc: str = ""):
        """创建公开仓库"""
        yield event.plain_result(await self._do_create_repo(name, desc, private=False))

    @gh.command("issues")
    async def cmd_issues(self, event: AstrMessageEvent, repo_str: str, state: str = "open"):
        """列出仓库的 Issue"""
        yield event.plain_result(await self._do_list_issues(repo_str, state))

    @gh.command("newissue")
    async def cmd_newissue(self, event: AstrMessageEvent, repo_str: str, title: str):
        """在指定仓库创建 Issue"""
        yield event.plain_result(await self._do_create_issue(repo_str, title))

    @gh.command("comment")
    async def cmd_comment(self, event: AstrMessageEvent, repo_str: str, number: int, body: str):
        """对指定 Issue/PR 发表评论"""
        yield event.plain_result(await self._do_comment(repo_str, number, body))

    @gh.command("prs")
    async def cmd_prs(self, event: AstrMessageEvent, repo_str: str, state: str = "open"):
        """列出仓库的 Pull Request"""
        yield event.plain_result(await self._do_list_prs(repo_str, state))

    @gh.command("pr")
    async def cmd_pr(self, event: AstrMessageEvent, repo_str: str, number: int):
        """查看某个 Pull Request 详情"""
        yield event.plain_result(await self._do_pr_info(repo_str, number))

    @gh.command("search")
    async def cmd_search(self, event: AstrMessageEvent, kind: str, query: str):
        """搜索 GitHub 仓库或代码"""
        yield event.plain_result(await self._do_search(kind, query))

    @gh.command("settoken")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def cmd_settoken(self, event: AstrMessageEvent, token: str):
        """设置 GitHub Token（仅管理员）"""
        if not token:
            yield event.plain_result("请提供 Token，如：/gh settoken ghp_xxxxxxxx")
            return
        self.token = token.strip()
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        try:
            self.config["token"] = self.token
            if hasattr(self.config, "save_config"):
                self.config.save_config()
        except Exception as e:
            logger.warning(f"[GitHub插件] 保存配置失败：{e}")
        ok, data, _ = await self._request("GET", "/user")
        if ok and isinstance(data, dict):
            self._login = data.get("login")
            yield event.plain_result(f"Token 设置成功，已验证通过，当前用户：{self._login}")
        else:
            yield event.plain_result(f"Token 已保存，但验证失败：{data}")

    # ================================================================== #
    #  LLM 工具（自然语言自动调用，需支持 Function Calling 的模型）
    #
    #  注意：llm_tool 必须用 return 返回字符串，不能用 yield event.plain_result()。
    #  return 的字符串会作为工具结果回传给 LLM，LLM 再基于结果生成自然语言回复。
    #  如果用 yield event.plain_result()，消息会直接发给用户但不回传给 LLM，
    #  导致 LLM 收不到工具结果、不会继续生成回复（即"获取完就不讲话了"的 bug）。
    # ================================================================== #
    @filter.llm_tool(name="github_whoami")
    async def tool_whoami(self, event: AstrMessageEvent) -> str:
        '''查看当前 GitHub 账户信息，可用于验证 Token 是否有效、了解当前登录用户。

        当用户想知道"我的 GitHub 账号信息""Token 是否有效""我是谁"时调用此工具。
        '''
        return await self._do_whoami()

    @filter.llm_tool(name="github_rate_limit")
    async def tool_rate_limit(self, event: AstrMessageEvent) -> str:
        '''查看 GitHub API 的速率限制剩余额度。

        当用户问"还能调用多少次 API""速率限制还剩多少""是否被限流"时调用此工具。
        '''
        return await self._do_rate_limit()

    @filter.llm_tool(name="github_list_repos")
    async def tool_list_repos(self, event: AstrMessageEvent, repo_type: str = "all") -> str:
        '''列出当前 GitHub 账户下的仓库。

        当用户说"看看我的仓库""我有哪些项目""列出我的仓库"时调用此工具。

        Args:
            repo_type(string): 仓库类型筛选，可选值为 all（全部）、public（公开）、private（私有）、forks（fork）。默认 all。
        '''
        return await self._do_list_repos(repo_type)

    @filter.llm_tool(name="github_repo_info")
    async def tool_repo_info(self, event: AstrMessageEvent, repository: str) -> str:
        '''查看某个 GitHub 仓库的详细信息，包括 star 数、fork 数、描述、默认分支、最近推送时间等。

        当用户说"看看 xxx 仓库的信息""xxx 仓库有多少 star""这个仓库的详情"时调用此工具。

        Args:
            repository(string): 仓库全名，格式为 owner/repo（如 octocat/Hello-World）。如果是当前用户自己的仓库，也可只写仓库名。
        '''
        return await self._do_repo_info(repository)

    @filter.llm_tool(name="github_create_repo")
    async def tool_create_repo(
        self, event: AstrMessageEvent, name: str, description: str = "", private: bool = True
    ) -> str:
        '''在当前 GitHub 账户下创建一个新仓库。

        当用户说"帮我创建一个仓库""新建一个叫 xxx 的项目""建一个私有/公开仓库"时调用此工具。

        Args:
            name(string): 新仓库的名称，不能包含空格。
            description(string): 仓库的描述说明，可选。
            private(boolean): 是否为私有仓库。true 表示私有（默认），false 表示公开。
        '''
        return await self._do_create_repo(name, description, private)

    @filter.llm_tool(name="github_list_issues")
    async def tool_list_issues(
        self, event: AstrMessageEvent, repository: str, state: str = "open"
    ) -> str:
        '''列出某个 GitHub 仓库的 Issue（议题）。

        当用户说"xxx 仓库有哪些 issue""看看这个项目的议题""列出 open 的 issue"时调用此工具。

        Args:
            repository(string): 仓库全名，格式为 owner/repo。如果是当前用户自己的仓库，也可只写仓库名。
            state(string): Issue 状态筛选，可选值为 open（开启）、closed（关闭）、all（全部）。默认 open。
        '''
        return await self._do_list_issues(repository, state)

    @filter.llm_tool(name="github_create_issue")
    async def tool_create_issue(
        self, event: AstrMessageEvent, repository: str, title: str, body: str = ""
    ) -> str:
        '''在指定的 GitHub 仓库中创建一个新 Issue（议题）。

        当用户说"帮我在这个仓库提一个 issue""给 xxx 项目报个 bug""创建一个议题"时调用此工具。

        Args:
            repository(string): 仓库全名，格式为 owner/repo。如果是当前用户自己的仓库，也可只写仓库名。
            title(string): Issue 的标题。
            body(string): Issue 的正文内容，支持 Markdown 格式，可选。
        '''
        return await self._do_create_issue(repository, title, body)

    @filter.llm_tool(name="github_comment_issue")
    async def tool_comment_issue(
        self, event: AstrMessageEvent, repository: str, number: int, body: str
    ) -> str:
        '''在指定的 GitHub Issue 或 Pull Request 下发表评论。

        当用户说"在这个 issue 下评论""给这个 PR 留言""回复一下 xxx"时调用此工具。

        Args:
            repository(string): 仓库全名，格式为 owner/repo。如果是当前用户自己的仓库，也可只写仓库名。
            number(number): Issue 或 PR 的编号。
            body(string): 评论内容，支持 Markdown 格式。
        '''
        return await self._do_comment(repository, number, body)

    @filter.llm_tool(name="github_list_prs")
    async def tool_list_prs(
        self, event: AstrMessageEvent, repository: str, state: str = "open"
    ) -> str:
        '''列出某个 GitHub 仓库的 Pull Request（合并请求）。

        当用户说"xxx 仓库有哪些 PR""看看待合并的请求""列出 pull request"时调用此工具。

        Args:
            repository(string): 仓库全名，格式为 owner/repo。如果是当前用户自己的仓库，也可只写仓库名。
            state(string): PR 状态筛选，可选值为 open（开启）、closed（关闭）、all（全部）。默认 open。
        '''
        return await self._do_list_prs(repository, state)

    @filter.llm_tool(name="github_pr_info")
    async def tool_pr_info(
        self, event: AstrMessageEvent, repository: str, number: int
    ) -> str:
        '''查看某个 GitHub Pull Request 的详细信息，包括状态、分支、是否合并、评论数等。

        当用户说"看看这个 PR 的详情""xxx 号合并请求什么情况""这个 PR 合并了吗"时调用此工具。

        Args:
            repository(string): 仓库全名，格式为 owner/repo。如果是当前用户自己的仓库，也可只写仓库名。
            number(number): Pull Request 的编号。
        '''
        return await self._do_pr_info(repository, number)

    @filter.llm_tool(name="github_search")
    async def tool_search(
        self, event: AstrMessageEvent, kind: str, query: str
    ) -> str:
        '''在 GitHub 上搜索仓库或代码。

        当用户说"帮我搜一下 GitHub 上的 xxx 仓库""搜索包含 xxx 的代码""找找相关的开源项目"时调用此工具。

        Args:
            kind(string): 搜索类型，repo 表示搜索仓库，code 表示搜索代码。
            query(string): 搜索关键词，可包含 GitHub 搜索限定符（如 language:python stars:>100）。
        '''
        return await self._do_search(kind, query)
