# Easel SKILL 元数据

| 字段 | 值 |
|------|-----|
| **SKILL 名称** | xhs-redbook-analyzer |
| **所属层** | attribute |
| **来源仓库** | lucasygu/redbook |
| **GitHub 地址** | https://github.com/lucasygu/redbook |
| **Star 数** | ~100+ |
| **功能描述** | 小红书数据分析：13个模块（关键词矩阵/热度图/互动信号/创作者画像） |
| **SKILL.md 行数** | 1252 |
| **文件总数** | 30 |
| **自包含** | 需XHS Cookie |
| **备注** | 1252行，Claude Code+OpenClaw双兼容 |

> 收录时间: 2026-07-16
> 用途: Easel SKILL 验证测试

## Wave4 瘦身说明（2026-07-23）

- **frontmatter 补全**：新增 `layer: attribute` / `version: 0.5.0`（沿用上游 CLI 版本）/ `profile_aware: false`；`description` 已是中文，微调补上与 publisher 的边界提示。
- **name 保留 `redbook`（重要）**：frontmatter 的 `metadata.openclaw.install` 与 `clawhub install redbook` 均以 `name=redbook` 为键，改名会破坏 OpenClaw/ClawHub 安装。因此**不**改成 `skill-xhs-analyzer`，仅在 SKILL.md 顶部加注释说明目录名与 name 有意不一致的原因。
- **瘦身**：1252 → 约 105 行。13 个分析模块、研究循环、命令详解、平台信号、技术参考全部下沉 `references/`；SKILL.md 只留能力概览 + 调用方式 + references 指针 + 环境依赖 + 边界。
  - 新建 references：`platform-signals.md`（参与度比率基准）、`modules.md`（模块 A–M + 组合工作流）、`commands.md`（全命令详解）、`research-loop.md`（读操作节流全套）、`technical-reference.md`（后端/xsec_token/中文数字/错误/限制/输出格式）。
- **环境标注**：SKILL.md 顶部新增「⚠️ 环境依赖」块 —— 需 macOS + Node ≥ 22 + `redbook` binary + Chrome 登录 cookie，当前 Linux 环境不可用。
- **2026-10-12 改为 WSL/Linux 可用（本仓改动，上游仍是 macOS 专属）**：去掉 frontmatter 的 `os: [macos]` 与 `install` 块；新增 `scripts/redbook-guard.sh`（只读白名单、每日 100 次上限、串行、熔断）与 `scripts/xhs-cdp-cookies.mjs`（经 CDP 从 SOP 扫描浏览器现取 cookie，只在内存）；SKILL.md「环境依赖」块改写为「运行环境」。上游 `redbook` 程序以 `npm install --ignore-scripts` 装在 `/opt/redbook`，不运行其 postinstall。
- **2026-10-23 守卫多两个步骤（issue 70，本仓改动）**：`redbook-guard.sh` 新增 `fetch-file`（下载 xhscdn/xiaohongshu 域名下的一个文件，不带 cookie，不计入每天 100 次）和 `diandian`（点点总结，经 `scripts/xhs-diandian-driver.mjs` 在扫描浏览器里问一次，算一次读，favsense 或 SOP 扫描占用时退出码 71）；`scripts/diandian-contract.json` 复制自 FavSense 的 `runtime/browser-contract.json`。两个步骤只供 `skill-xhs-note-reader` 使用。备份见 `archive/skill-backups/skill-xhs-analyzer/2026-10-23/`（这一天第一次改动前的原样）。
- **xhs 去重**：SKILL.md 与直接引用的命令/模块文档均设为只读；发布转交 `skill-xhs-publisher`，评论回复转交 `skill-xhs-comment-reply`，避免绕过确认和出站安全闸门。
- 未删除任何脚本/源码（`src/` TypeScript 保留），仅重构 SKILL.md 文档。
