---
name: ecom-details-image
description: >-
  生成电商商品视觉方案：主图概念、场景图、详情页视觉方向和 AI 生图 Prompt。
  当用户说"商品主图""详情页视觉""电商配图方案""商品场景图""带货视觉""产品视觉方向""详情页设计"时使用。
  本 SKILL 出视觉方案+生图 Prompt（策划）；实际抠白底图用 remove-bg，实际生成图片用 ai-image-gen。
  天猫/Tmall 商品主图和商详页请用 tmall-product-content，不要用本技能。
layer: produce
---

# ecom-details-image Skill

当用户需要视觉策略、图片 Prompt、商品主图、营销图、社媒图、广告图、电商 PDP 视觉，或要求直接 AI 生图时，使用这个 Skill。

两种模式：

1. **Brief / Prompt 模式**：只输出视觉简报和可执行图片 Prompt。
2. **Generate 模式**：当用户明确要求"生图、生成图片、出图、render image"时，先输出最终 Prompt，再调用 `scripts/generate_image.py`。

> **审美方向对齐 [card-design](../card-design/SKILL.md)**：详情页信息图 / 营销图的视觉方向遵守同一套去 AI 廉价感原则——禁蓝紫科技渐变、禁 emoji 当图标、字大字细、留白克制、填满不空。把这些写进 Prompt 的正向/否定约束里（本 SKILL 出 t2i Prompt，非 HTML 渲染，故是"审美方向"层面对齐，不走 render_card）。

出图只走 Codex（ChatGPT）订阅，不需要任何 API key，也不要索要、写入、提交或回显任何 key。

## References（按需加载，不要一次性全读）

| 文件 | 内容 | 何时读 |
|---|---|---|
| `references/templates.md` | 25 个场景模板匹配表、使用方式、风格变体速查 | 判断场景类型、匹配模板时 |
| `references/templates/*.json` | 具体场景模板（`prompt_template`/`variants`/`category_tips`/`anti_ai_tips`） | 只读匹配到的那一个 |
| `references/image-gen-rules.md` | 通用 Prompt 结构、文生图铁律、精简原则、Anti-AI 技巧、翻车点防护 | 写每一条 Prompt 时 |
| `references/campaign-style-lock.md` | 多图任务的 Campaign Style Lock 规则与默认模板 | 任务含多张图时 |
| `references/pdp-sequences.md` | 转化驱动诊断、主图/详情页序列、多角度镜头、详情页信息图结构、字体搭配 | 商品图/详情页/PDP 任务时 |

## 核心流程

1. 判断视觉任务类型和场景 → 读 `references/templates.md` 匹配模板。
2. 从 `references/templates/` 读取**匹配到的那一个** JSON，取 `prompt_template`、`variants`、`category_tips` 作为 Prompt 基础结构。
3. 只收集会实质影响图片结果的缺失信息（见下方**最小输入**）。
4. 构建视觉简报。
5. 多图任务：先按 `references/campaign-style-lock.md` 建立 **Campaign Style Lock**，锁定整套图的色板、冷暖调、字体、背景、光线、布局和图标风格。
6. 按 `references/image-gen-rules.md` 写出可执行图片 Prompt（保持简洁，逐条对照铁律）；多图任务必须把同一段 Campaign Style Lock 原样放进每张 Prompt。
7. 商品图/详情页/营销图：按 `references/pdp-sequences.md` 先做转化驱动力诊断，再排序列。
8. 用户要求电商详情页 / PDP / 主图堆栈 / 整套商品图时，默认输出 **5 张主图 + 7-9 张详情页图片** 的图片包（详情页每屏必须是电商信息图格式，见 `references/pdp-sequences.md`）。
9. 用户要求直接出图 → 调用 `scripts/generate_image.py`；用户提供参考产品图时传入 `--image`。
10. 返回 Prompt、生成文件路径和关键假设。

## 最小输入

任何视觉任务优先确认：目标、用途（主图/广告图/社媒图/Banner/PDP 模块/缩略图等）、主体、受众与语境、风格、构图与比例、是否需要图内文字、负面约束。缺少非关键字段时，明确假设后继续，不要无谓阻塞。

## 生图脚本调用（scripts/generate_image.py）

直接生图只走 Codex（ChatGPT）订阅：项目根 `.env` 里要有 `IMG_PROVIDER=codex`，不需要任何 API key。脚本让本机 Codex 用自带的 image_gen 工具出图，存成 `--output-dir` 下的 PNG。`--image` 参考产品图照常传入；`--size` 只是比例提示，像素不保证精确；每张约 1~3 分钟、几万 token 订阅额度，`--n` 一次最多 4 张，PDP 套图请按 4 张一批分批跑。没有 `IMG_PROVIDER=codex` 时脚本直接停下并说明缺这一项；Codex 内置出图工具不可用时脚本也直接报错，**不会**回退到别的出图方式。统一生图入口 skill 是 `ai-image-gen`，同样只走这条路线。

调用形状：

```bash
python3 skills/builtin/ecom-details-image/scripts/generate_image.py --prompt "..." --size 1:1
python3 skills/builtin/ecom-details-image/scripts/generate_image.py --prompt-file prompt.txt --output-dir outputs
python3 skills/builtin/ecom-details-image/scripts/generate_image.py --env-file .env --image product.jpg --prompt-file prompt.txt
```

参数：`--prompt` / `--prompt-file`；`--output-dir`（仅用户指定时用，否则 `generated-images/`）；`--size`（比例提示，如 `1:1`/`16:9`/`2:3`/`4:5`，默认 `1:1`）；`--image`（参考产品图路径，对保证产品外观准确非常有效）；`--n`（一次最多 4 张）；`--format`（只能 `png`）。

生图规则：

1. 先输出最终 Prompt，再调脚本。短 Prompt 用 `--prompt`，长 Prompt 用 `--prompt-file`。
2. 根据平台选 `--size`，没要求时默认 `1:1`。
3. `.env` 里没有 `IMG_PROVIDER=codex` 时**不要调用脚本**，只输出完整 Prompt 包，并只告诉用户项目设置缺 `IMG_PROVIDER=codex`；不要去找别的出图服务。
4. Codex 只给比例提示：要的尺寸不是 Codex 给得出的比例时，改用最接近的比例并说明。

## QA 检查（输出前逐条确认）

- Prompt 符合用户真实目标，已匹配正确场景模板并基于其 `prompt_template` 组装。
- Prompt 简洁、只含核心信息，主体/构图/风格/用途明确。
- 商品/营销任务包含转化驱动力诊断；证据缺失时不虚构效果、认证、数据、评分、销量、评价或授权。
- 已应用文生图铁律：hex 颜色、数字占比、显式留白、否定清单、平台预留空间（详见 `references/image-gen-rules.md`）。
- UGC/直播/社媒场景已应用 anti-AI 技巧（模板的 `anti_ai_tips` 字段）。
- 多图任务：每张以同一段 Campaign Style Lock 开头；已分配不同角度和景别，无连续 3 张相同角度，全景图占比 ≤ 40%。
- **详情页图片必须是电商信息图格式**（含标题、图标、标签、利益点、步骤或信任徽章），每张详情页 Prompt 以 `E-commerce infographic` 开头，不是单纯多角度产品照片。
- 图内文字短且必要；有用户参考图时已传 `--image`；负面约束覆盖常见失败点。
- 输出和文件里没有私密凭据。
- 提醒用户出图后放大 200% 逐字核对中文笔画。

## 输出格式

Brief / Prompt 模式返回：

1. **匹配模板**（模板文件名 + 场景类型）
2. **Visual Brief**
3. **Final Image Prompt**
4. **Negative Constraints**
5. **Assumptions**

商品或营销任务追加：**Conversion Driver Diagnosis**、**Campaign Style Lock**（多图时）、**Hero Image Sequence**（标注每张对应模板）、**PDP Detail Image Sequence**（涉及详情页/PDP/整套商品图时）、**Copy Lines**（需要文字时）、**Test Priorities**。

Generate 模式返回：

1. **匹配模板**（模板文件名 + 场景类型）
2. **Final Image Prompt**
3. **Campaign Style Lock**（多图任务必须返回）
4. **Image Pack Plan**（每张图的编号、用途、尺寸、对应模板和短文案）
5. **Generated Files**
6. **Assumptions / Notes**
