# redbook 命令详解

**始终加 `--json`** 供程序解析（否则输出人读文本）。全局选项见文末。

## 读取（reading）

### `redbook search <keyword>`
按关键词搜索笔记，返回标题/URL/点赞/作者。
```bash
redbook search "AI编程" --sort popular --json    # sort: general(默认)/popular/latest
redbook search "Cursor" --type image --json       # type: all(默认)/video/image
redbook search "MCP Server" --page 2 --json       # 分页
```

### `redbook read <url>`
读笔记全文 —— 标题/正文/图片/点赞/评论数。接受完整 URL 或短 noteId（bare noteId 常返回 `{}`，需 xsec_token）。API 返回验证码时回退 HTML 抓取。

### `redbook comments <url>`
获取评论，一次一页。`redbook comments "<url>" --json`（`--all` 被守卫拒绝）。

### `redbook user <userId|profileUrl>`
创作者档案 —— 昵称/简介/粉丝数/笔记数/获赞。bare userId 返回 `code=-1` 时用含 `xsec_token` 的完整 profile URL，或 `--xsec-token <token> --xsec-source pc_search`。

### `redbook user-posts <userId|profileUrl>`
列出创作者所有笔记（标题/URL/点赞/时间）。

### `redbook account-report <userId|profileUrl...>`
批量汇总账号发帖与参与度。
```bash
redbook account-report "<url>" --month 2026-07 --json
```
选项：`--month YYYY-MM`（默认当月）。守卫拒绝 `--file`、多个账号、`--max-pages` 大于 1 和 `--all`。KOS/KOC 报告用已知 ID，勿用关键词搜索。
每账号的 `topByLikesPlusFavourites` = 点赞 + 收藏最高的笔记（原 `topByLikes`，已改名）；`topByEngagement`（点赞 + 评论 + 收藏 + 分享）是另一个单独的量，不变。

### `redbook feed`
浏览推荐流。`redbook feed --json`

### `redbook topics <keyword>`
搜索话题标签。`redbook topics "Claude Code" --json`

### `redbook favorites [userId]`
列出收藏笔记，默认当前登录用户。`--all` 拉全页。他人收藏仅在未设私密时可见。

### `redbook analyze-viral <url>`（守卫拒绝）
程序内部一次连取笔记、评论多页、作者笔记和档案，不留间隔，守卫拒绝。下面是程序本身的说明。
分析爆款原因，返回确定性 0–100 分。`--comment-pages n`（默认 3，最大 10）。
JSON：`{ note, score, hook, content, visual, engagement, comments, relative, fetchedAt }`
- `score.overall` = hook(20)+engagement(20)+relative(20)+content(20)+comments(20)
- `hook.hookPatterns[]` · `engagement`（点赞/评论/收藏/分享 + 三比率）· `relative.viralMultiplier`（点赞/作者中位，两边都只比点赞：`relative.measure` = `"likes"`；`score.breakdown.engagement` 档位按点赞 + 收藏）· `relative.isOutlier`（>3）· `comments.themes[]`

### `redbook viral-template <url> [url2] [url3]`（守卫拒绝）
同上，守卫拒绝。下面是程序本身的说明。
从 1-3 篇爆款提取可复用模板。`--comment-pages n`（默认 3，最大 10）。
JSON：`{ dominantHookPatterns, titleStructure, bodyStructure, engagementProfile, audienceSignals, sourceNotes, generatedAt }`

### `redbook health`
检测笔记隐藏限流 level（见 modules.md Module M）。`redbook health --json`（`--all` 被守卫拒绝）

### `redbook whoami`
检查连接状态，验证 cookie 并显示登录用户。

### `redbook boards` / `redbook board <board-url>`
列出用户合集 / 列出合集内笔记。

## 写操作边界

本 Skill 只允许上面的读取与分析命令。不要调用 CLI 内置的发布、评论、回复、点赞、收藏或批量互动命令；这些路径没有 Easel 的确认与内容安全闸门。发布改用 `skill-xhs-publisher`，评论和回复改用 `skill-xhs-comment-reply`。

### `redbook render <file>`（离线，无需 cookie）
markdown → styled PNG 卡片，用本机 Chrome。
选项：`--style purple/xiaohongshu(默认)/mint/sunset/ocean/elegant/dark` · `--pagination auto(默认)/separator` · `--output-dir` · `--width`(1080) · `--height`(1440) · `--dpr`(2)。需 `puppeteer-core` + `marked`；Chrome 非标准位置设 `CHROME_PATH`。

### `redbook auth`
上游用它把 cookie 存成明文文件。**本环境禁用**：守卫拒绝 `auth`、`--cookie-string`、`--cookie-source`、`--chrome-profile`；cookie 每次现取、只在内存（见 SKILL.md「运行环境」）。`favorites`、`boards`、`board` 同样被拒绝。

## 全局选项（所有命令）
- `--cookie-source chrome(默认)/safari/firefox`
- `--chrome-profile <name>`（省略则自动发现）
- `--cookie-string "a1=...; web_session=..."`
- `--platform xhs(大陆)/rednote(全球)`（默认自动检测，见 technical-reference.md）
- `--global`（= `--platform rednote`）
- `--json`
