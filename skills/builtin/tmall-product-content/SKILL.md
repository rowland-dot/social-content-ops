---
name: tmall-product-content
description: 天猫商品主图（尺寸取天猫公布标准允许的几种）和商详页（790 宽）的整套制作：事实表、竞品阅读、页面方案、中文文案、真实包装叠图、检查、审批页、PSD 交付。当用户说天猫主图、商详页、天猫详情页时用本技能，不要用 ecom-details-image。
layer: produce
---

# 天猫商品内容（主图 + 商详页）

为一款产品做出 5 张主图（尺寸是 `references/tmall-rules.md` 里允许的几种之一，阶段 3 定）和 790 宽的详情页：每条事实和卖点有来源，场景图里没有字也没有包装，真实包装照原样叠上去，字由代码排，量出来的检查全过之后才给负责人看。规格：`work/docs/specs/2026-10-25-tmall-product-content-spec.md`。

## 什么时候用

- 要做天猫（含天猫国际）的商品主图或商详页，用本技能；`ecom-details-image` never called，天猫的请求不走它。
- 小红书、抖音等其他平台的图不在这里。

## 先记住的规则

- 包装上印的字不检查：包装照必须是真品、没被改动，这一条照查；印在包装上的字不查、不报、不拿来缩放或藏起包装（负责人常设规则）。
- 不付费：图只用 Codex 订阅；任何付费生成都不碰，更不会自己开。
- 客户的数字、价格、竞品截图和笔记只通过知识库的工具存取，不进本仓库；从 `brands/<brand>/INDEX.md` 读起。
- 品牌资料读 Easel 的品牌设置指向的位置，不另存一份。
- 做出来的页面只通过 Easel 改：负责人的意见送回 Easel 重做，不手改图、不手改文案。
- 头图先出三个版本，先看三个封面——负责人选定之后才做其余图。
- 文字卡的版式检查不用于天猫（负责人 2026-10-28：）。
- 所有成品放在 `outputs/<Brand>/天猫商品内容/<product>/`。

## 先读平台标准；竞品案例优先（负责人，2026-10-29）

动手之前先读 `references/tmall-rules.md`：天猫公布的主图和详情页设计标准、平台和广告法对用词的限制；每条规则都带来源地址、读取日期和状态。主图尺寸不是固定的一种，平台各类目公布的不止一种，规则文件把允许的全列出来。

但这份阅读只是后备。负责人的原话（未改动）：

> the reading will be served as a fallback ONLY, where a competitor's case always wins for what sells (their numbers wont lie), and if they used cretain designs or certain wording that contradicts the reading's rules, the case always wins over the reading's rules

做法：阶段 2 读竞品案例；阶段 3 用案例决定每款产品的主图尺寸（写进 `plan.json` 的 `main_size`）、设计和用词；案例没管到的地方，才用规则文件。案例的设计或用词与规则文件某条矛盾时，以案例为准。代码里还没有让案例压过阶段 6 某项检查的办法（另外立项，等竞品阅读试抓之后）；“案例是否也压过广告法限制的用词”是负责人的问题，不替他定（见简报的待定事项）。

## 阶段与命令

命令都在项目根目录运行，用 `python`（浏览器步骤要用有 Playwright 的那个 Python）。有 `main()` 的脚本才有命令；其余模块当函数调用（见下面“短脚本”）。

| 阶段 | 做什么 | 详细 |
|---|---|---|
| 1 事实表 | 每条事实、卖点带来源；价格只取价格表；矛盾标 waiting on the owner | `references/stage-1-facts.md` |
| 2 竞品阅读 | 保存的登录；先试 2 到 3 款；抓主图和详情；写规律笔记；存知识库 | `references/stage-2-competitor-read.md` |
| 3 页面方案 | 五张主图、屏序、一图一问、卖点对应图、样式锁 | `references/stage-3-page-design.md` |
| 4 文案 | 三层字数预算；价格由代码算 | `references/stage-4-copy.md` |
| 5 图片 | 头图三版；真实包装；字由代码排 | `references/stage-5-images.md` |
| 6 检查 | 量出来的检查；失败重做；到限定轮数就报告 | `references/stage-6-checks.md` |
| 7 审批页 | 手机宽度的网页，负责人批准或给意见 | `references/stage-7-approval.md` |
| 8 交付与效果 | 规则文件允许的主图尺寸、790 宽、每张一个分层 PSD、文案文件；前后四周对比 | `references/stage-8-handover.md` |

```bash
python skills/builtin/tmall-product-content/scripts/tmall_facts.py check outputs/<Brand>/天猫商品内容/<product>
python skills/builtin/tmall-product-content/scripts/tmall_facts.py render outputs/<Brand>/天猫商品内容/<product>
python skills/builtin/tmall-product-content/scripts/tmall_plan.py check outputs/<Brand>/天猫商品内容/<product>
python skills/builtin/tmall-product-content/scripts/tmall_flow.py status outputs/<Brand>/天猫商品内容/<product>
python skills/builtin/tmall-product-content/scripts/tmall_page.py report outputs/<Brand>/天猫商品内容/<product>
python skills/builtin/tmall-product-content/scripts/tmall_page.py headline outputs/<Brand>/天猫商品内容/<product>
python skills/builtin/tmall-product-content/scripts/tmall_page.py approval outputs/<Brand>/天猫商品内容/<product>
python skills/shared/scripts/tmall_login.py login --status-file outputs/_login/tmall.status.json
python skills/shared/scripts/tmall_login.py status
python skills/builtin/tmall-product-content/scripts/tmall_capture.py run --query <搜索词> --trial --out outputs/_scratch/tmall-capture/<date>
python skills/builtin/tmall-product-content/scripts/tmall_capture.py trial-sheet --out outputs/_scratch/tmall-capture/<date>
python skills/builtin/tmall-product-content/scripts/tmall_capture.py deposit --out outputs/_scratch/tmall-capture/<date> --brand <brand> --cat 05 --note <note>
python skills/builtin/tmall-product-content/scripts/tmall_note.py check <note> <item ids>
```

## 短脚本

`tmall_compose`、`tmall_checks`、`tmall_copy`、`tmall_prices`、`tmall_flow`、`tmall_handover`、`tmall_results`、`tmall_scene` 没有命令行，用一个短脚本调用函数。完整可运行的例子（装好导入路径，做一张主图，跑 `tmall_checks.gather`，写 `check-reports.json`，再运行 `tmall_page.py report`）在 `references/stage-5-images.md`。流程状态只用 `tmall_flow.load_state` 和 `save_state` 读写。

## 头图三个版本放哪里

每个版本都以名字 `M1` 做在自己的文件夹里：`headline/A/M1.png`、`headline/B/M1.png`、`headline/C/M1.png`，`gather` 在那个文件夹上跑。名字必须是 `M1`（`gather` 靠开头的 `M` 分主图和切片，靠编号找头图的卖点），文件夹分开才不会互相覆盖。负责人选定后调用 `tmall_flow.promote_pick`，把选中版本的 `M1` 原样复制到产品文件夹，审批页和交付才能在 `M2` 到 `M5` 旁边找到它。

## 关口

1. 头图三个版本都通过阶段 6 才给负责人看，并排；他选了或给了意见，才做别的（`tmall_flow.may_make`）。
2. 没检查过、没通过的图，审批页和对比页都拒绝显示。
3. 负责人的意见只通过 Easel 改：只重做受影响的图，其余原样不动。

## 重做的顺序

失败的图按规格的顺序处理：先重新排字（把字块挪离包装；放不下就先删多余的字，再把需要的事实挪到下一屏；绝不缩字号）；再重做场景，在提示词里写明失败原因；包装层一概不动。包装或字体授权失败，重做场景治不了，立即停下报告。

没有任何覆盖办法的几件事：旋转或重画包装；绕过搁置；让没过检查的图到达负责人。

## HELD：图片工具和质量检查

`skills/builtin/ai-image-gen`（出场景图）和 `skills/builtin/skill-quality-gate`（质量检查）搁置，直到 Easel 的 issue 94（质量检查会读包装上的字）和 issue 95（缺 Codex 设置时图片技能会改用付费生成）合并到 main。搁置状态记在 `references/held.json`，代码读它，缺失一律当作搁置。在那之前：这两个工具的实时步骤一律跳过，并如实告诉负责人；`tmall_scene.generate_scene` 会拒绝运行（`HeldError`）；不写质量检查结果。解除搁置只能改 `references/held.json`，且须负责人知情。

## 停止与错误

| 名字 | 退出码 | 意思 | 下一步 |
|---|---|---|---|
| `NEXT_STEP["wall"]` | 2 | 抓取遇到验证码或拦截页 | 当天不要重试，告诉负责人；已抓的保留 |
| `NEXT_STEP["login"]` | 3 | 保存的登录过期 | 运行 `tmall_login.py login`，停下等负责人扫码，再重跑 |
| `NEXT_STEP["daily_cap"]` | 4 | 今天的访问次数到上限 | 明天重跑，已完成的会跳过 |
| `NEXT_STEP["error"]` / `["incomplete"]` | 5 | 某款没加载好，或没存到图 | 重跑；反复出现就告诉负责人 |
| `tmall_page.py` | 2 | 图没检查、报告缺失或不是这张图的，或输入文件不在 | 先补检查或输入文件，按提示的原因修 |
| `tmall_facts.py` / `tmall_plan.py` / `tmall_note.py` | 1 | 查出问题（逐条列出） | 逐条修；`tmall_plan.py` 缺文件时退出码 2 |
| `HeldError` | 异常 | 工具还在搁置 | 跳过实时步骤，见上 |
| `PaidRouteRefused` | 异常 | 没设 `IMG_PROVIDER=codex` | 停止，不用任何付费路线，告诉负责人 |
| `PackNeedsCutout` | 异常 | 包装照不是透明抠图 | 停止；是否允许去背景由负责人定 |
| `FontNotLicensed` | 异常 | 字体不在授权清单，或字重不是 400 和 700 | 换授权字体，不要绕过 |

## 提醒

- 绝不手改 Easel 做出的内容；对 Easel 转述负责人的话要用他的原话。
- 登录用的是负责人自己的淘宝账号：扫码这一步停下来等他，抓取不在他的屏幕上开窗口。
