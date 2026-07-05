"""
AstrBot 插件：GitHub 管理助手
通过经典 Token (Personal Access Token, classic) 让机器人管理你的 GitHub。

支持功能：
- 账户：验证 Token、查看账户信息、速率限制
- 仓库：列出 / 查看详情 / 创建（公开或私有）
- Issue：列出 / 创建 / 评论
- Pull Request：列出 / 查看详情
- 搜索：仓库 / 代码
"""

from datetime import datetime

import aiohttp

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import AstrBotConfig, logger

GITHUB_API_BASE = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"


@register(
    "astrbot_plugin_github",
    "AstrBotUser",
    "通过经典 Token 管理 GitHub：仓库、Issue、Pull Request、搜索等。",
    "1.0.0",
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

    # ------------------------------------------------------------------ #
    #  HTTP / GitHub API 封装
    # ------------------------------------------------------------------ #
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
        """统一请求方法。

        返回: (success: bool, data, headers: dict)
            success 为 True 时 data 是解析后的 JSON；
            success 为 False 时 data 是人类可读的错误信息字符串。
        """
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
            # 区分速率限制与权限不足
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
        """解析 owner/repo。若只给出仓库名，则用当前认证用户作为 owner。

        返回 (owner, repo) 或 (None, None)（无法确定 owner 时）。
        """
        repo_str = repo_str.strip()
        if "/" in repo_str:
            owner, repo = repo_str.split("/", 1)
            return owner.strip(), repo.strip()
        # 只给仓库名，补全 owner
        if not self._login:
            ok, data, _ = await self._request("GET", "/user")
            if ok and isinstance(data, dict):
                self._login = data.get("login")
            else:
                return None, None
        return self._login, repo_str

    # ------------------------------------------------------------------ #
    #  生命周期
    # ------------------------------------------------------------------ #
    async def initialize(self):
        if not self.token:
            logger.warning(
                "[GitHub插件] 尚未配置 Token，请在管理面板配置或使用 /gh settoken 设置。"
            )
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

    # ------------------------------------------------------------------ #
    #  辅助
    # ------------------------------------------------------------------ #
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
            "提示：<owner/repo> 可省略 owner，只写自己的仓库名，如 /gh repo myproject"
        )

    @staticmethod
    def _fmt_time(iso: str | None) -> str:
        if not iso:
            return "无"
        try:
            return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            return iso

    # ------------------------------------------------------------------ #
    #  指令组与帮助
    # ------------------------------------------------------------------ #
    @filter.command_group("gh")
    async def gh(self, event: AstrMessageEvent):
        """GitHub 管理助手"""
        yield event.plain_result(self._help_text())

    @gh.command("help")
    async def gh_help(self, event: AstrMessageEvent):
        """查看 GitHub 插件帮助"""
        yield event.plain_result(self._help_text())

    # ------------------------------------------------------------------ #
    #  账户
    # ------------------------------------------------------------------ #
    @gh.command("whoami")
    async def whoami(self, event: AstrMessageEvent):
        """查看 GitHub 账户信息，并验证 Token 是否有效"""
        ok, data, headers = await self._request("GET", "/user")
        if not ok:
            yield event.plain_result(f"验证失败：{data}")
            return
        if isinstance(data, dict):
            self._login = data.get("login")
        scopes = headers.get("X-OAuth-Scopes") or headers.get("x-oauth-scopes") or "无"
        text = (
            "GitHub 账户信息\n"
            f"用户名：{data.get('login', '未知')}\n"
            f"昵称：{data.get('name') or '未设置'}\n"
            f"ID：{data.get('id', '未知')}\n"
            f"公开仓库：{data.get('public_repos', 0)} 个\n"
            f"关注者：{data.get('followers', 0)} | 正在关注：{data.get('following', 0)}\n"
            f"创建时间：{self._fmt_time(data.get('created_at'))}\n"
            f"Token 权限(scope)：{scopes}"
        )
        yield event.plain_result(text)

    @gh.command("rate")
    async def rate(self, event: AstrMessageEvent):
        """查看 GitHub API 速率限制"""
        ok, data, _ = await self._request("GET", "/rate_limit")
        if not ok:
            yield event.plain_result(f"查询失败：{data}")
            return
        core = data.get("resources", {}).get("core", {}) if isinstance(data, dict) else {}
        search = data.get("resources", {}).get("search", {}) if isinstance(data, dict) else {}
        reset_core = core.get("reset")
        reset_str = ""
        if reset_core:
            try:
                reset_str = datetime.fromtimestamp(int(reset_core)).strftime("%H:%M:%S")
            except (ValueError, OSError):
                reset_str = ""
        text = (
            "GitHub API 速率限制\n"
            f"核心接口：{core.get('remaining', '?')}/{core.get('limit', '?')} 次/小时"
            + (f"（{reset_str} 重置）" if reset_str else "")
            + "\n"
            f"搜索接口：{search.get('remaining', '?')}/{search.get('limit', '?')} 次/分钟"
        )
        yield event.plain_result(text)

    # ------------------------------------------------------------------ #
    #  仓库
    # ------------------------------------------------------------------ #
    @gh.command("repos")
    async def repos(self, event: AstrMessageEvent, repo_type: str = "all"):
        """列出我的仓库，可选 all/public/private/forks"""
        allowed = {"all", "public", "private", "forks", "sources", "member"}
        if repo_type not in allowed:
            repo_type = "all"
        ok, data, _ = await self._request(
            "GET",
            "/user/repos",
            params={
                "type": repo_type,
                "sort": "updated",
                "direction": "desc",
                "per_page": self.per_page,
                "page": 1,
            },
        )
        if not ok:
            yield event.plain_result(f"获取失败：{data}")
            return
        if not data:
            yield event.plain_result("没有找到符合条件的仓库。")
            return
        lines = [f"我的仓库（类型：{repo_type}，按更新时间排序，前 {len(data)} 个）\n"]
        for r in data:
            vis = "私有" if r.get("private") else "公开"
            star = r.get("stargazers_count", 0)
            lang = r.get("language") or "-"
            lines.append(
                f"• {r.get('full_name')} [{vis}] ★{star} {lang}\n"
                f"  {(r.get('description') or '无描述')}"
            )
        yield event.plain_result("\n".join(lines))

    @gh.command("repo")
    async def repo(self, event: AstrMessageEvent, repo_str: str):
        """查看仓库详情"""
        owner, repo = await self._parse_repo(repo_str)
        if not owner:
            yield event.plain_result("无法确定仓库 owner，请使用 owner/repo 格式，或先 /gh whoami 验证 Token。")
            return
        ok, data, _ = await self._request("GET", f"/repos/{owner}/{repo}")
        if not ok:
            yield event.plain_result(f"获取失败：{data}")
            return
        vis = "私有" if data.get("private") else "公开"
        text = (
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
        yield event.plain_result(text)

    async def _create_repo(self, event: AstrMessageEvent, name: str, desc: str, private: bool):
        if not name:
            yield event.plain_result("请提供仓库名称。")
            return
        body = {"name": name, "private": private, "auto_init": True}
        if desc:
            body["description"] = desc
        ok, data, _ = await self._request("POST", "/user/repos", json_body=body)
        if not ok:
            yield event.plain_result(f"创建失败：{data}")
            return
        vis = "私有" if private else "公开"
        yield event.plain_result(
            f"仓库创建成功（{vis}）\n"
            f"名称：{data.get('full_name')}\n"
            f"链接：{data.get('html_url', '')}\n"
            f"已自动初始化 README。"
        )

    @gh.command("newrepo")
    async def newrepo(self, event: AstrMessageEvent, name: str, desc: str = ""):
        """创建私有仓库"""
        async for msg in self._create_repo(event, name, desc, private=True):
            yield msg

    @gh.command("newpub")
    async def newpub(self, event: AstrMessageEvent, name: str, desc: str = ""):
        """创建公开仓库"""
        async for msg in self._create_repo(event, name, desc, private=False):
            yield msg

    # ------------------------------------------------------------------ #
    #  Issue
    # ------------------------------------------------------------------ #
    @gh.command("issues")
    async def issues(self, event: AstrMessageEvent, repo_str: str, state: str = "open"):
        """列出仓库的 Issue"""
        owner, repo = await self._parse_repo(repo_str)
        if not owner:
            yield event.plain_result("无法确定仓库 owner，请使用 owner/repo 格式。")
            return
        if state not in ("open", "closed", "all"):
            state = "open"
        ok, data, _ = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/issues",
            params={"state": state, "sort": "created", "direction": "desc", "per_page": self.per_page},
        )
        if not ok:
            yield event.plain_result(f"获取失败：{data}")
            return
        # 过滤掉 PR（issues 端点会同时返回 PR）
        real_issues = [i for i in data if "pull_request" not in i]
        if not real_issues:
            yield event.plain_result(f"{owner}/{repo} 没有 {state} 状态的 Issue。")
            return
        lines = [f"{owner}/{repo} 的 Issue（状态：{state}，前 {len(real_issues)} 个）\n"]
        for i in real_issues:
            labels = ",".join(l.get("name", "") for l in i.get("labels", [])) or "无"
            lines.append(
                f"#{i.get('number')} {i.get('title')}\n"
                f"  by {i.get('user', {}).get('login', '?')} | 标签：{labels} | "
                f"{self._fmt_time(i.get('created_at'))}"
            )
        yield event.plain_result("\n".join(lines))

    @gh.command("newissue")
    async def newissue(self, event: AstrMessageEvent, repo_str: str, title: str):
        """在指定仓库创建 Issue"""
        owner, repo = await self._parse_repo(repo_str)
        if not owner:
            yield event.plain_result("无法确定仓库 owner，请使用 owner/repo 格式。")
            return
        if not title:
            yield event.plain_result("请提供 Issue 标题。")
            return
        ok, data, _ = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/issues",
            json_body={"title": title},
        )
        if not ok:
            yield event.plain_result(f"创建失败：{data}")
            return
        yield event.plain_result(
            f"Issue 创建成功\n"
            f"#{data.get('number')} {data.get('title')}\n"
            f"链接：{data.get('html_url', '')}"
        )

    @gh.command("comment")
    async def comment(self, event: AstrMessageEvent, repo_str: str, number: int, body: str):
        """对指定 Issue/PR 发表评论"""
        owner, repo = await self._parse_repo(repo_str)
        if not owner:
            yield event.plain_result("无法确定仓库 owner，请使用 owner/repo 格式。")
            return
        if not body:
            yield event.plain_result("请提供评论内容。")
            return
        ok, data, _ = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/issues/{number}/comments",
            json_body={"body": body},
        )
        if not ok:
            yield event.plain_result(f"评论失败：{data}")
            return
        yield event.plain_result(
            f"评论成功（#{number}）\n"
            f"链接：{data.get('html_url', '')}"
        )

    # ------------------------------------------------------------------ #
    #  Pull Request
    # ------------------------------------------------------------------ #
    @gh.command("prs")
    async def prs(self, event: AstrMessageEvent, repo_str: str, state: str = "open"):
        """列出仓库的 Pull Request"""
        owner, repo = await self._parse_repo(repo_str)
        if not owner:
            yield event.plain_result("无法确定仓库 owner，请使用 owner/repo 格式。")
            return
        if state not in ("open", "closed", "all"):
            state = "open"
        ok, data, _ = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/pulls",
            params={"state": state, "sort": "created", "direction": "desc", "per_page": self.per_page},
        )
        if not ok:
            yield event.plain_result(f"获取失败：{data}")
            return
        if not data:
            yield event.plain_result(f"{owner}/{repo} 没有 {state} 状态的 PR。")
            return
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
        yield event.plain_result("\n".join(lines))

    @gh.command("pr")
    async def pr(self, event: AstrMessageEvent, repo_str: str, number: int):
        """查看某个 Pull Request 详情"""
        owner, repo = await self._parse_repo(repo_str)
        if not owner:
            yield event.plain_result("无法确定仓库 owner，请使用 owner/repo 格式。")
            return
        ok, data, _ = await self._request("GET", f"/repos/{owner}/{repo}/pulls/{number}")
        if not ok:
            yield event.plain_result(f"获取失败：{data}")
            return
        merged = data.get("merged_at")
        state = data.get("state", "?")
        if merged:
            state = "merged"
        head = data.get("head", {}).get("ref", "?")
        base = data.get("base", {}).get("ref", "?")
        draft = " [草稿]" if data.get("draft") else ""
        text = (
            f"PR #{data.get('number')} {data.get('title')}\n"
            f"状态：{state}{draft} | {head} → {base}\n"
            f"作者：{data.get('user', {}).get('login', '?')} | "
            f"评论数：{data.get('comments', 0)} + {data.get('review_comments', 0)} 审查评论\n"
            f"创建：{self._fmt_time(data.get('created_at'))} | "
            f"合并：{self._fmt_time(merged) if merged else '未合并'}\n"
            f"描述：{data.get('body') or '无'}\n"
            f"链接：{data.get('html_url', '')}"
        )
        yield event.plain_result(text)

    # ------------------------------------------------------------------ #
    #  搜索
    # ------------------------------------------------------------------ #
    @gh.command("search")
    async def search(self, event: AstrMessageEvent, kind: str, query: str):
        """搜索 GitHub 仓库或代码"""
        if not query:
            yield event.plain_result("请提供搜索关键词。")
            return
        if kind in ("repo", "仓库"):
            ok, data, _ = await self._request(
                "GET",
                "/search/repositories",
                params={"q": query, "sort": "stars", "order": "desc", "per_page": self.per_page},
            )
            if not ok:
                yield event.plain_result(f"搜索失败：{data}")
                return
            items = data.get("items", []) if isinstance(data, dict) else []
            total = data.get("total_count", 0) if isinstance(data, dict) else 0
            if not items:
                yield event.plain_result(f"未找到匹配「{query}」的仓库（共 {total} 条结果）。")
                return
            lines = [f"搜索仓库「{query}」（共 {total} 条，显示前 {len(items)} 个）\n"]
            for it in items:
                lines.append(
                    f"• {it.get('full_name')} ★{it.get('stargazers_count', 0)}\n"
                    f"  {(it.get('description') or '无描述')}\n"
                    f"  {it.get('html_url', '')}"
                )
            yield event.plain_result("\n".join(lines))
        elif kind in ("code", "代码"):
            ok, data, _ = await self._request(
                "GET",
                "/search/code",
                params={"q": query, "per_page": self.per_page},
            )
            if not ok:
                yield event.plain_result(f"搜索失败：{data}")
                return
            items = data.get("items", []) if isinstance(data, dict) else []
            total = data.get("total_count", 0) if isinstance(data, dict) else 0
            if not items:
                yield event.plain_result(f"未找到匹配「{query}」的代码（共 {total} 条结果）。")
                return
            lines = [f"搜索代码「{query}」（共 {total} 条，显示前 {len(items)} 个）\n"]
            for it in items:
                repo_name = it.get("repository", {}).get("full_name", "?")
                path = it.get("path", "?")
                lines.append(f"• {repo_name} : {path}\n  {it.get('html_url', '')}")
            yield event.plain_result("\n".join(lines))
        else:
            yield event.plain_result("搜索类型仅支持 repo（仓库）或 code（代码），如：/gh search repo python web")

    # ------------------------------------------------------------------ #
    #  配置
    # ------------------------------------------------------------------ #
    @gh.command("settoken")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def settoken(self, event: AstrMessageEvent, token: str):
        """设置 GitHub Token（仅管理员）"""
        if not token:
            yield event.plain_result("请提供 Token，如：/gh settoken ghp_xxxxxxxx")
            return
        self.token = token.strip()
        # 关闭旧 session 以便用新 header 重建
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        # 持久化到配置文件
        try:
            self.config["token"] = self.token
            if hasattr(self.config, "save_config"):
                self.config.save_config()
        except Exception as e:
            logger.warning(f"[GitHub插件] 保存配置失败：{e}")
        # 立即验证
        ok, data, headers = await self._request("GET", "/user")
        if ok and isinstance(data, dict):
            self._login = data.get("login")
            yield event.plain_result(f"Token 设置成功，已验证通过，当前用户：{self._login}")
        else:
            yield event.plain_result(f"Token 已保存，但验证失败：{data}")
