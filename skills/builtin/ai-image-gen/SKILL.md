---
name: ai-image-gen
description: "通用 AI 生图：文生图 / 图生图 / 图像变体。当用户说 AI 生图、AI 画图、文生图、图生图、生成图片、生成配图、图像生成、AI 出图、AI 作图、换图、改图、图像编辑、给我画一张、生成一张图 时使用。只走 Codex（ChatGPT 订阅），不需要 API key。"
layer: produce
---

# ai-image-gen Skill

> 通用 AI 文生图 / 图生图 / 图像变体。只走 Codex（ChatGPT 订阅）出图，不需要 API key，产物写入 `outputs/`。

调用共享脚本 `skills/shared/scripts/ai_image.py`（纯标准库，无第三方依赖）。
出图不涉及任何 API key，本 SKILL 也不索要、不回显、不写入、不提交任何 key。

## 边界（和相邻 SKILL 区分）

- **ai-image-gen（本 SKILL）**：通用 AI 生图，任意题材，文生图 / 图生图 / 变体。
- **ecom-details-image**：电商详情页 / 商品主图专用出图（25 场景模板、PDP 序列）。要做电商商品图走它；天猫 / Tmall 商品主图和商详页不走它，走 `tmall-product-content`。
- **card-\* / poster-\***：HTML+CSS 渲染截图（金句卡、小红书卡、海报），**非 AI 生成**，是确定性设计出图。
- **image-editing**：已有图片的确定性处理（改尺寸/裁剪/加水印/压缩），不生成新画面。

## 配置（执行前必读）

> **配置检查路径铁律**：先 `cd` 到运行时说明给出的 Easel 项目根，确认当前目录有 `.env` 和 `skills/shared/scripts/ai_image.py`，再运行下列命令。不得在任何执行引擎的 workspace 或共享脚本副本中检查，也不得用 `env` / `printenv` 代替读取项目 `.env`；否则会把已配置的 `IMG_PROVIDER=codex` 误判为缺失。

项目根目录 `.env` 里要有 `IMG_PROVIDER=codex`（脚本从当前目录向上自动查找 `.env`）。脚本让本机 Codex（ChatGPT 订阅）用它自带的 image_gen 工具出图，再把图复制到 `--output`。`check`、`text2img`、`img2img`、`variations` 的用法见下面的执行步骤，限制如下：

- 没有 `IMG_PROVIDER=codex` 时，所有出图命令直接停下并说明缺这一项，`check` 报"未就绪"（退出码 2）；**不会**去调任何别的出图接口。遇到这种情况，只告诉用户项目设置缺 `IMG_PROVIDER=codex`，不要去找别的出图服务，也不要索要任何 key。
- 只产出 PNG（`--format png`、文件名 `.png`）；`--size` / 比例只是给 Codex 的提示，像素不保证精确（实测 3:4 出 1086×1448）。
- 每张约 1~3 分钟、几万 token 订阅额度，`--n` 一次最多 4 张，再多请分批。
- 不支持 `--mask` 局部编辑。
- `img2img` 可重复给 `--image`，最多 3 张：第 1 张是商品图（形状、颜色、包装文字原样保留），其余至多 2 张是风格参考（只借光线、场景、构图、字体风格，不带它的商品、人物、手、文字）。提示词会逐张写明角色；只给一张时和以前完全一样。
- 品牌自己的模特图用单独的 `--identity-image`（身份参考，不算 `--image`，至多 1 张，由调用方明确写出，不看图的顺序）：提示词写明这一张是要保持的那个人（脸和身份不变），姿势、角度、服装按提示词重画，所以总数是商品 + 至多 2 张风格参考 + 1 张身份参考，共最多 4 张。不带包装的人物卡也可以单独给 `--identity-image`（不给 `--image`）：这一张是唯一的图，Codex 只收到它，不当商品图用，提示词写明不画商品和包装（除非提示词自己描述了它们）；`--image` 和 `--identity-image` 至少给一个，两个都没有、或给了第二张身份参考图，在启动 Codex 之前就报错。用法见 `xhs-reference-visual`。
- 已批准的卡用单独的 `--base-image`（底图，不算 `--image`，至多 1 张，由调用方明确写出，不看图的顺序；issue 115）：它紧跟在商品图后面当第 2 张，提示词写明它的画面（手、背景、道具、构图、色调）原样保留，只改提示词点名的地方，不当风格参考；所以总数是商品 + 底图 + 至多 2 张风格参考 + 1 张身份参考，共最多 5 张。底图要和商品图一起给（商品图，不能没有），给了第二张底图、或没有商品图，在启动 Codex 之前就报错。不给底图时，发给 Codex 的参数和提示词和以前完全一样。用法见 `xhs-reference-visual`。
- Codex 内置出图工具不可用时直接报错，**不会**回退到别的出图方式。
- 短剧（short-drama）的定妆图、关键帧也走这条路线。

## 执行步骤

### 1. 先确认配置（离线，不发请求）

```bash
python skills/shared/scripts/ai_image.py check
```

确认 `IMG_PROVIDER=codex` 在位且本机 Codex 可用。缺项时说明缺什么并以退出码 2 结束。**配置未就绪就不要往下走**，直接把缺什么告诉用户。

### 2. 文生图 text2img

先把用户诉求写成一条清晰的图像 Prompt（主体 + 风格 + 构图 + 光线 + 画质），再执行：

```bash
python skills/shared/scripts/ai_image.py text2img \
  --prompt "一只戴墨镜的柴犬，扁平插画风，明亮撞色背景，高细节" \
  --size 1024x1024 --n 1 \
  --output outputs/主题名/ai-image.png
```

- `--size`：明确写像素（`1080x1920` 等）才会缩放、裁边成刚好这个尺寸（需要 Pillow）；不写或写比例（`9:16` 等）则保存 Codex 原图。
- `--n`：生成张数，一次最多 4 张（多张时按序号自动命名）。
- `--output`：目录（多张自动编号）或含扩展名的单文件；统一放 `outputs/主题名/`。

### 3. 图生图 / 图像编辑 img2img

基于一张或多张输入图 + 指令生成新图：

```bash
python skills/shared/scripts/ai_image.py img2img \
  --prompt "把背景换成夜晚霓虹街道，保留主体" \
  --image path/to/input.png \
  --output outputs/主题名/edited.png
```

### 4. 图像变体 variations

由一张图生成多个变体：

```bash
python skills/shared/scripts/ai_image.py variations \
  --image path/to/input.png --n 3 \
  --output outputs/主题名/variations
```

### 5. 交付

告诉用户产物路径、生成参数（尺寸/张数）。如需再改尺寸/加水印/压缩，转 `image-editing`。

## 产物

统一输出到 `outputs/主题名/`。脚本会自动创建目录，多张按时间戳 + 序号命名。

## Profile 感知

有账号 Profile（`=== EASEL ACCOUNT PROFILE ===`）时，把品牌视觉风格（配色 / 调性 / 元素偏好）融入 Prompt，保持系列图统一；无 Profile 时按用户描述走通用生成。

## 常见问题

- **缺 Codex 设置**：命令停下并说明项目设置缺 `IMG_PROVIDER=codex`；报错为友好中文，不抛 traceback。把这一句告诉用户，不要换别的出图方式。
