---
# ⚠️ name 保持 "redbook" —— clawhub 安装（`clawhub install redbook`）与下方 metadata.openclaw
#    install 块均以此 name 为键；改名会破坏 OpenClaw/ClawHub 安装。目录名 skill-xhs-analyzer
#    与此 name 有意不一致，勿"对齐"目录名而改动 name。
name: redbook
description: >-
  小红书内容分析：搜索笔记、拉取互动数据、分析爆款规律、创作者画像、限流检测，支持 CLI 自动化操作。
  当用户说"小红书数据分析""小红书爆款分析""笔记数据""小红书限流检测""小红书创作者画像""分析小红书账号"时使用。
  发布与日常互动运营请用 skill-xhs-publisher。
layer: attribute
metadata:
  openclaw:
    requires:
      bins:
        - redbook
    homepage: https://github.com/lucasygu/redbook
---

# Redbook — 小红书内容分析 CLI

用 `redbook` CLI 搜索笔记、读内容、分析创作者、提取爆款规律、研究选题。本环境（WSL/Linux）的 `redbook` 已装好，**不要自行安装或升级**（官方安装脚本会往 Claude Code 技能目录写入带发布/评论命令说明的副本）。

## 运行环境（WSL / Linux，只读通道）

本机的 `redbook` 是一道守卫脚本（`scripts/redbook-guard.sh`），真程序只能经它调用。这些约束由守卫执行，不靠自觉：

| 项 | 说明 |
|------|------|
| 登录态 | 每次调用现取：守卫通过 `scripts/xhs-cdp-cookies.mjs` 从 SOP 项目的小红书扫描浏览器读 cookie（该浏览器须已启动并登录），cookie 只存在于这一次调用的内存里，**不写盘**。不要用 `--cookie-string`、`--cookie-source`、`auth`，守卫会拒绝 |
| 只读 | 只放行 `search` `read` `comments` `user` `user-posts` `account-report` `topics` `feed` `health` `whoami`（另有离线的 `render`）。其余一律拒绝，包括 `favorites` `boards` `board`。一次调用里连取多页的形式也拒绝：`analyze-viral`、`viral-template`、任何 `--all`、`account-report` 的 `--file` / `--max-pages` 大于 1 / 多个账号（守卫只能给整次调用计一次数、隔一次间隔，管不到程序内部的连发）。同样的分析改成分开的 `read` `comments` `user` `user-posts` 调用，一次一篇、一页。守卫自己多了两个步骤 `fetch-file`（下载平台文件服务器上的一个文件）和 `diandian`（点点总结，算一次读），只供 `skill-xhs-note-reader` 使用，同样受锁、熔断管 |
| 额度与节奏 | 每天最多 100 次读（所有需要登录的调用都计数）；一次只跑一个；两次读之间守卫至少隔 15 秒（研究循环默认 ~20 s ± jitter 仍然适用） |
| 熔断 | 一旦出现验证码 / 访问频繁 / 300012 / 300031，守卫写入熔断标记并拒绝后续所有读取。立刻向负责人汇报，不得重试、不得自己清除标记 |
| 账号共用 | 同一个账号 favsense（收藏整理）也在用。favsense 正在运行、或 SOP 扫描占着浏览器时，守卫会报  并退出：如实告诉负责人当前不可用，**不要循环重试** |
| 依赖 | Node.js ≥ 22 · 扫描浏览器在运行且已登录 · `render` 卡片另需 puppeteer-core + marked（可选） |

## 与 skill-xhs-publisher 的分工边界

- **xhs-analyzer（本 SKILL）** = **分析**：搜索/数据/爆款规律/关键词矩阵/创作者画像/限流检测。
- **skill-xhs-publisher** = **发布 + 互动运营**：发图文/视频、日常评论/回复/点赞收藏、内容数据、通知抓取。
- 本 SKILL **只读**。不得调用 `comment`/`reply`/`like`/`collect`/`post` 等写命令；发布交给 `skill-xhs-publisher`，评论与回复交给 `skill-xhs-comment-reply`，由对应 Skill 执行确认和出站安全检查。

## Research discipline（先读这条）

XHS 风控节流的是**读取**，不只是写入。任何读超过几篇笔记的研究，都**必须**走 **[references/research-loop.md](references/research-loop.md)** 的研究循环 —— 默认 human-paced（~20 s/篇，一次一篇）。在紧循环里猛敲 `read`/`comments` 会在几十次内触发验证码/IP 封（300012），账号降级数小时。⚡ Fast 模式仅应急，需打印警告 + 用户明确 opt-in。绝不并行或零延迟发读。

## Usage

```
redbook search "AI编程" --json       # 搜索笔记
redbook read <webUrl> --json         # 读笔记（用 search 返回的 webUrl，含 xsec_token）
redbook user <profileUrl> --json     # 创作者档案
redbook comments <webUrl> --json     # 评论（一页；--all 被守卫拒绝）
redbook account-report <profileUrl> --json  # 一个账号的指标（一次一个账号）
redbook health --json              # 笔记限流检测（--all 被守卫拒绝）
```

**始终加 `--json`** 供程序解析。全部命令、选项、JSON 结构见 **[references/commands.md](references/commands.md)**。

## 能力概览

分析能力拆成 13 个可组合模块（A–M）+ 组合工作流，详见 **[references/modules.md](references/modules.md)**：

| 模块 | 能力 |
|------|------|
| A 关键词参与度矩阵 · B 跨主题热力图 · C 参与度信号 | 需求版图 |
| D 创作者画像 · D2 已知账号报告 · E 内容形态分解 | 竞争/形态 |
| F 机会评分 · G 受众推断 · H 内容头脑风暴 | 策略产出 |
| I 评论洞察 · J 爆款结构拆解 · K 互动机会识别 | 只读分析 |
| L 卡片渲染（离线） · M 笔记限流检测 | 产出/健康 |

组合示例：快速主题扫描 `A→C→F`；完整细分分析 `A→B→C→D→E→F→G→H`；单篇深挖 `read` + `comments` + `user-posts`（分开调用）。

## 关键领域知识（references/）

| 文件 | 内容 |
|------|------|
| [platform-signals.md](references/platform-signals.md) | 收藏/点赞、评论/点赞、分享/点赞比率基准；排序语义；图文 vs 视频 |
| [modules.md](references/modules.md) | 13 个分析模块 A–M + 组合工作流 |
| [commands.md](references/commands.md) | 所有 redbook 命令详解 + 选项 + JSON 结构 + 全局选项 |
| [research-loop.md](references/research-loop.md) | 读操作节流：三模式/严格规则/状态契约/tick/驱动器/熔断器/写侧阈值 |
| [technical-reference.md](references/technical-reference.md) | 大陆 vs 全球后端、xsec_token、中文数字、错误处理、API vs 浏览器限制、输出格式 |

## Requirements

- WSL / Linux · Node.js ≥ 22 · SOP 小红书扫描浏览器已启动并登录 xiaohongshu.com（见上文「运行环境」）
- 仅卡片渲染额外需 `puppeteer-core` + `marked`（用本机 Chrome，无需额外下载浏览器）
