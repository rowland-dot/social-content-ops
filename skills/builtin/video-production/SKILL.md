---
name: video-production
description: >-
  整片视频产线（原片 → 包装级成片）：九步流程 + 八件质量门 + 两道人工确认门，产出成片与全套交付物。
  当用户说"用视频产线做一支整片""把这条原片做成片""整片包装""走视频产线"时使用。
  全程经独立接口驱动：每步可核验、门不过不交付。
  与兄弟技能分界：本 SKILL 的**输入是已有的整条原片**，做的是重包装（分场/动效/字幕/调色 + 质量门），
  过程重、需两次人工点头；从一句话主题**无中生有**出片用 auto-short-video；
  手上只有一组图片用 slideshow-video；把长片**切成多条**短视频用 clipify 或 video-highlights。
layer: produce
---

# 整片视频产线（video-production）

> 把一支原片（口播 / 独白）做成**包装级成片**：摸底 → 转录 → 分场 → 设计表 → 脚手架 → 写码
> → 验证 → 预览 → 渲染 → 交付。质量不靠自觉，靠可执行的门。
>
> 产线 SDK 已**内置**在本技能 `vendor/video-pipeline-sdk/`（随 Easel 进仓、可复现、可在其基础上改）。
> 首次使用先跑一次依赖还原：`bash <ROOT>/skills/builtin/video-production/vendor/video-pipeline-sdk/deps/bootstrap.sh`
> （装 Remotion 渲染引擎，`--ignore-scripts`；node_modules 不入库）。

## 什么时候用

用户说「用视频产线做一支整片 / 把这段素材做成片 / 整片包装」时使用。

### 开工前检查（缺源片不要动工）

- **源片必需**：必须有可读的本地路径。用户没给 → **先向用户要**（要路径，或提示他把文件拖进聊天 / 拷到内容库收件箱）；严禁用占位素材开工
- 主题与基调（`--brief`）建议要一句；现成材料（转录稿 / 分场 / 设计表）有就给、没有就按流程走（流程会在需要时停下）

### 转录三级策略（选一个，优先级从上到下）

产线第二步要把口播里说的话转成带时间轴的文字稿。三级降级，越靠前越省：

1. **tier1 现成稿（最优）**：源片自带字幕/台词就用它——`start --transcript 路径`。`.srt`/`.vtt` 会自动转成段级 `transcript.json`（保留时间轴）；`.json`（segments 结构）直接用。**Easel 做的口播剧一般自带 SRT，走这条即可，不下模型。**
2. **tier2 云端 ASR API**：没现成稿但配了 `SILICONFLOW_API_KEY`（env）→ 自动调硅基流动（默认 `XingChenAGI/XingChenGSR-V1.0`，可用 `SILICONFLOW_ASR_MODEL` / `SILICONFLOW_BASE_URL` 覆盖）。key 只从环境变量读，勿写进命令/仓库。
3. **tier3 本地 whisper（兜底）**：都没有才用本地 large-v3（首次下约 3GB）。需 `faster-whisper`。

### 让用户看得见（产物贴进对话 · 免上传）

对话消息**直接支持图片与视频**（站内媒体通道 `/api/media/`，零上传、零改前端）。产物落盘后，把它们贴进消息、再配卡片：

- 图片：Markdown 图片语法（`!` + 方括号说明文字 + 圆括号地址），地址写 `/api/media/<outputs 相对路径，逐段 URL 编码>`（示例文件名：`视频产线/<时间戳>/run/preview/f60.png`）
- 视频：`<video src="/api/media/<outputs 相对路径>" controls style="max-width:420px">` 标签
- 文件：Markdown 链接语法（方括号文字 + 圆括号地址）指向 `/api/media/<outputs 相对路径>`，或把要点直接摘进消息

三处必用：
1. **设计表确认卡之前**：先贴设计表要点摘要 + 全文链接（用户"看得见才审得动"）
2. **预览确认卡之前**：把 `run/preview/*.png` 逐张贴成图片，再出预览卡
3. **交付时**：成片贴成 video 标签（`视频产线/<时间戳>/out/final.mp4`），附门报告链接

### 素材怎么给（用户问"怎么把视频给你"时这样答）

1. **首选 · 本地路径**：文件放本机任意位置，对话里报路径即可（例：`E:/clips/raw.mp4`）。无大小限制、不复制文件
2. 小文件可直接**拖进聊天上传**（进内容库收件箱）；大文件不走上传——直接报本地路径（见第 1 条）
3. 也可先手动拷进 `outputs/_inbox/` 再报路径

## 快速开始

```bash
python <ROOT>/skills/builtin/video-production/scripts/video_pipeline.py doctor
python <ROOT>/skills/builtin/video-production/scripts/video_pipeline.py start --source "C:/path/raw.mp4" --brief "主题一句话"
```

`start` 依次做：建运行态 → 机械段（摸底 / 转录 / 分场）→ **停在需要人参与的地方**。

## 交互循环（重要）

每个命令最后一行是 `STATE: ...`：

| STATE | 含义 | 你要做的 |
|-------|------|---------|
| `awaiting-answer` | 有题待作答 | `pending` 读题 → 用 **ask_user 工具**转问用户 → `answer` + `resume` |
| `done` | 全流程完成 | 报告产物路径（见下） |
| `gate-failed` | 质量门失败 | 把失败项如实报告，**不要交付** |
| `error` | 异常 | 把错误原文报告用户 |

### 转问用户（ask_user 映射规则）

- ask_user 限制：一次 1–3 问、每题 2–4 个选项、header ≤12 字——按此裁剪，选项 label 用中文原样
- 收到回答后，把用户所选 label 对照问题 JSON 的 `options[].value` 映射回：

| 问题 id | 选项 label → value |
|---------|--------------------|
| checkpoint-1（设计表确认） | 通过，按设计表开工→`approve` ｜ 带意见修改→`revise` ｜ 打回重做→`reject` |
| checkpoint-2（预览确认） | 通过，渲全片→`approve` ｜ 有场次要改→`revise` |

- 写回答并续跑：

```bash
python <ROOT>/skills/builtin/video-production/scripts/video_pipeline.py answer --id checkpoint-1 --values approve --notes "可选备注"
python <ROOT>/skills/builtin/video-production/scripts/video_pipeline.py resume
```

### 自由输入题（如 need-design-table）

题目会写明要产出的文件与放置位置。把说明转给用户；文件就位后重新 `resume`（自动检测在档）。
开工时已有设计表的话，`start` 直接加 `--design-table <md 路径>`。

## 命令一览

| 命令 | 用途 |
|------|------|
| `doctor` | 环境自检（SDK 路径 / 依赖 / 版本） |
| `start --source ... [--brief] [--transcript] [--scenes] [--config] [--gates] [--design-table]` | 开工，跑到第一个停点 |
| `pending` | 打印待作答问题（JSON） |
| `answer --id ... --values a,b [--notes ...]` | 写入作答 |
| `resume` | 从停点续跑 |
| `status` | 进度 / 待作答 / 路径 |

所有命令支持 `--run-dir`（默认最近一次 start）、`--base`（运行态根）、`--sdk`（SDK 路径；默认用内置 `vendor/video-pipeline-sdk`，也可用 `--sdk`/环境变量 `VIDEO_PIPELINE_SDK` 覆盖）。
`--gates` 可带质量门清单 JSON；不带就用下面「质量门」一节的默认八件门。

## 质量门（必读：没有门单，产线会在验证步停下）

产线要求每次运行都有门单。SDK 自带的默认门单（`vendor/video-pipeline-sdk/gates/default-gates.json`）大多只查文件在不在，不查画面和声音。所以 `start` 不带 `--gates` 时，自动把本技能的 `default-gates.json`（八件门）写进运行目录的 `gates.json`；自己传 `--gates <文件>` 则以你的为准。**不要删门、不要改成空单。**

| 门 | 阶段 | 读什么 | 谁来备好 |
|----|------|--------|----------|
| dup 查重 | 验证（写码后） | `run/artifacts/scenes.json` | 分场步骤已产出 |
| timeline 分场时间轴 | 验证 | `run/artifacts/scenes.json` | 分场步骤已产出 |
| layout 排版网格 | 验证 | `run/artifacts/gate-inputs/layout.json` | **写码步骤写** |
| frames 帧检 | 验证 | `run/artifacts/gate-inputs/composition.json`（`comp` + `frames`），可选 `frame-checks.json` | **写码步骤写** |
| transitions 转场可感知 | 验证 | 同上 `composition.json`（`comp` + `cuts`） | **写码步骤写** |
| meta 五件套 | 渲染（成片后） | `run/artifacts/gate-inputs/meta.json` | **写码步骤写** |
| match 素材↔台词对位 | 渲染 | `run/artifacts/gate-inputs/match.json`，素材在 `run/workdir/public/stock` | **写码步骤写** |
| audio 响度 | 渲染 | `run/workdir/out/final.mp4` | 渲染产出 |

- 写码步骤要把上表标「写码步骤写」的文件放进 `run/artifacts/gate-inputs/`，再 `touch run/workdir/.build-ok`。各文件的字段看对应脚本开头的用法说明（`vendor/video-pipeline-sdk/gates/check_<门>.py`）；`composition.json` 形如 `{"comp": "合成名", "frames": [60, 120], "cuts": [120, 213]}`。
- 文件缺了，那一道门就是 **FAIL**，`gate-report.md` 会写明缺哪个文件；不会被跳过，也不会算通过。补上文件后 `resume` 重跑。
- 渲染阶段成片在 `run/workdir/out/final.mp4`；`out/`（交付目录）要到交付步才有成片，门不要指向那里。
- 每次运行默认把渲染引擎装进自己的 `workdir`（首次 `npm install` 要几分钟、占几百 MB）。不想装就给 `--config` 一个含 `{"scaffold_install": false}` 的 JSON。
- 自己写门单时，命令里用占位符：`{python}`（与产线同一个 Python，Linux 上没有裸 `python`）、`{run_dir}`、`{out_dir}`、`{skill_dir}`。

## 产物

默认运行态在 `<工作区>/outputs/视频产线/<时间戳>/`（**交付物进「视频产线」项目，内容库里可见**）：
- `run/`：run-state、questions / answers、checkpoints、gate-report、logs
- `out/`：`final.mp4`、`design-table.md`、`gate-report.md` / `gate-report.json`、`manifest.json`

## 红线

- **只转发，不复制 SDK 逻辑**；SDK 升级不改本技能
- 门不过不交付；任何 FAIL 必须如实报告
- 写长代码/大文件务必**分块写**（单次输出有上限，被截断会中断任务；分 2-4 段续写）
- 交付自动带**人审包**（`review-pack/`：每场定格帧 + 核对表）；把它贴给用户，照单核对（无视觉的执行者靠人眼兜底）
- 设计表是创作步：与用户确认后产出，机器只校验在档

## 退出码（机器语义）

`0` 完成 ｜ `2` 门失败 ｜ `3` 待作答 / 待审批 ｜ `1` 异常
