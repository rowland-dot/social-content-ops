---
name: auto-short-video
description: "一句话主题 → 成品短视频：自动串联 文案→配图/AI视频→配音→字幕→BGM→合成，把 Easel 制作层零件编排成一条'一键出片'流水线。**单条视频、口播/资讯向，画面默认逐句配图 + Ken Burns 缓动，需要动态时才逐段图生视频**。当用户说 一键生成视频、自动做短视频、主题生成视频、帮我做条视频、口播视频一条龙、自动出片、短视频一键生成 时使用。**有剧情/角色/对白/反转/多集的短剧改用 short-drama（每镜强制图生视频、不用静态图冒充）；只写脚本用 video-script；只生成单个片段用 ai-video-gen。**"
layer: produce
---

# 一键短视频（端到端编排）

> 输入一个主题，自动产出一条短视频。本 SKILL 是**编排层**：把已有制作零件串成流水线——
> 文案(video-script) → 逐句配图(ai-image-gen)或片段(ai-video-gen) → 配音(tts-voiceover) →
> 字幕(auto-subtitle) → BGM(ai-music) → **合成(scripts/assemble.py)**。
> 沉淀自 Pixelle-Video / MoneyPrinterTurbo 的自动短视频引擎思路。

## 输入

- 主题 / 文案（必填）
- 可选：目标时长、风格、是否要配音/字幕/BGM、配图用 AI 生图还是用户素材
- **画幅确认硬门**：用户或上游任务未明确横版/竖版（或 16:9/9:16/具体分辨率）时，制作/付费调用前必须追问并等确认；不得从平台、Profile 或默认值静默推断，已明确则不重复问

## 输出

成品短视频写入 `outputs/主题名/final.mp4`；分镜图、配音、字幕和 storyboard 写入 `outputs/主题名/assets/`。

## 执行步骤（按需裁剪，缺 API key 的环节自动降级或询问）

1. **写脚本分镜**：用 [video-script](../video-script/SKILL.md) 把主题写成口播文案，拆成 N 句（每句一个分镜），每句配一个画面描述；plan 里的分镜表按 video-script「计划里的分镜表」的固定写法写。

   **口播稿和分镜时间线每次送审（审批），都做成网页，不要在对话里贴表格**，也不要手写网页，由命令从 plan 的分镜表生成，存进视频文件夹：
   ```bash
   # 口播稿送审（分镜图还没出）
   python skills/shared/scripts/storyboard_page.py build --plan outputs/主题名/plan.md --script-only
   # 分镜图出齐、等批准每镜画面时
   python skills/shared/scripts/storyboard_page.py build --plan outputs/主题名/plan.md
   ```
   网页（`分镜脚本-审批稿.html`）每镜一行，分镜图在左，口播、画面、来源、时间和备注在右，每个待定结尾一个切换按钮，文字照 plan 原文。计划或分镜图改过再送审，重新跑一遍。命令读不懂 plan 里的哪一镜会停下并点名，照提示改 plan 再跑。

2. **生成画面**（每个分镜一张图/一段片）：
   - 有图像 API key → [ai-image-gen](../ai-image-gen/SKILL.md) 逐句 text2img（按已确认画幅）
   - 要动态 → [ai-video-gen](../ai-video-gen/SKILL.md) text2video/image2video
   - 用户自带素材 → 用 [image-editing](../image-editing/SKILL.md) `pad` 到已确认画幅
   - 都没有 → 按已确认画幅选图卡（竖版用 card-xiaohongshu/poster-hero，横版用 card-quote）再 pad，避免画幅错配。
   - 图卡渲染：已确认竖版 9:16 的视频，卡片要渲染成 1080×1920，渲染命令必须带 `--scale 1 --height 1920`（默认 2 倍像素会出 2160×3840，进成片就错了）：
     `python skills/shared/scripts/render_card.py --html outputs/主题名/assets/cards.html --selector .card --out outputs/主题名/assets/card.png --scale 1 --height 1920`

3. **配音**：[tts-voiceover](../tts-voiceover/SKILL.md) 把文案合成口播（同时出 SRT）。**配了 `VOICE_PROVIDER` 默认走闭源好嗓子**（有情感、像真人），没 key 才退 edge（机械）——想要口播不"生硬"务必配闭源 key。不需要配音才跳过。

4. **字幕与切点**：**先定配音，再按配音的真实停顿定字幕时间和切点**（对配音做静音检测 `silencedetect`；句内逗号、冒号的停顿也会被检出，有时比句间停顿还长，所以逐句对应，不要取最长的几段）。TTS 附带的 SRT：ChatGPT 路线已按配好的整段音频里的真实停顿定时，但命令打印「没有找到停顿，沿用按字数估算」警告的那一句，以及任何按字数估算的时间，都要按静音检测重排；改过配音（换句、改停顿、变速）后一律重排。也可对配音跑 [auto-subtitle](../auto-subtitle/SKILL.md)，或让 assemble 用各分镜 caption 自动生成。

5. **BGM**：[ai-music](../ai-music/SKILL.md) 生成，或用用户提供的音乐。可选。音乐直接放进 storyboard 的 `bgm`，由合成器在配音说话处压低、说完恢复（见第 6 步），不用另外先混。音乐要至少和成片一样长，短了合成器会在渲染前停下（第 6 步）；要音乐铺到片尾，生成时就多要几秒。

6. **合成成片**：把上面的素材写成 storyboard JSON，调合成器：
   ```bash
   python skills/builtin/auto-short-video/scripts/assemble.py assemble \
     --storyboard outputs/主题名/assets/storyboard.json \
     -o outputs/主题名/final.mp4
   ```
   storyboard 结构（图/片二选一，narration/bgm/subtitle 可选，缺 duration 时按配音均分）：
   ```json
   {
     "size": "<已确认尺寸，如1080x1920或1920x1080>",
     "image_motion": "ken-burns",
     "shots": [
       {"image": "outputs/主题名/assets/shot1.png", "duration": 3, "caption": "第一句", "motion": "static"},
       {"video": "outputs/主题名/assets/clip2.mp4", "caption": "第二句"}
     ],
     "narration": "outputs/主题名/assets/voice.mp3",
     "bgm": "outputs/主题名/assets/bgm.mp3",
     "subtitle": "outputs/主题名/assets/voice.srt",
     "subtitle_keep_words": ["燕麦肽"],
     "subtitle_size": 84,
     "bgm_loop": false,
     "bgm_fade_out": 2.0
   }
   ```
   背景音乐：配音说话时合成器自动把音乐（和 native 镜的原声）压低，说完恢复，所以音乐直接放进 `bgm`，不要另外先混好再当配音传入。
   音乐比视频短时**默认不循环**：合成器在渲染前停下并说差几秒，换一首更长的，或在 storyboard 写 `"bgm_loop": true` 明确要循环。
   `bgm_fade_out`（秒，可选）让音乐在最后这几秒淡出，只淡音乐，不动配音、原声和音效；不写就不淡出。
   `image_motion` 设整条图片默认运动，单镜 `motion` 可覆写：照片用 `ken-burns`，含文字的 slide/图表/界面必须用
   `static`（等比缩放 + 补边，不裁切、不平移）。
   字幕折行：每条字幕最多 2 行，只在词与词之间断，标点不放行首，两行时在停顿处断并尽量均衡；`subtitle_keep_words`
   （可选，字符串列表）里的词（品牌词、产品名）绝不拆开。有字幕放不进 2 行时合成器在渲染前停下并点名那一句：
   缩短它，或拆成两条字幕（各对应配音的一句），再重新合成。
   字幕字号：`subtitle_size`（可选，像素，正整数，如 84）；不写则按短边 ×0.05（1080×1920 是 54）。命令行 `--sub-size` 优先于它。
   `subtitle` 给的是现成的 `.ass` 文件时，字号不能用（它自带样式、原样烧录），合成器会报错：改传 SRT。
   合成器自动做：按 `image_motion` 生成静帧或 Ken Burns、补边到画幅、拼接、配音+BGM 混音（配音说话处音乐自动压低、说完恢复）、烧录字幕。

7. **成片音频自检**（交付前必跑，让脚本量，不手工量）：
   ```bash
   python skills/shared/scripts/sound_check.py check --video outputs/主题名/final.mp4 \
     --storyboard outputs/主题名/assets/storyboard.json
   ```
   脚本逐秒报告音乐和成片的音量，并逐项判定：音乐一直响到片尾；音乐一开始就是满音量（不淡入、不静音开头）；淡出只出现在允许的最后几秒里；最后一句配音不比其他句的中位数轻超过 1 dB；片尾没有静音；整条成片的响度在 -16 LUFS 上下 1 LU 以内，真峰值不高于 -1 dBTP（`loudness` 一项）。任何一项 `FAIL` 都不交付：回第 6 步改好重新合成。
   允许的淡出秒数取 storyboard 的 `bgm_fade_out`；storyboard 没写，就按 Profile `preferences.md` 的背景音乐规格用 `--fade-seconds` 传入；两处都没有时不判淡出，只报告量到的淡出位置。脚本用 storyboard 的 `bgm`（混音时的那份音乐文件）和 `subtitle`（烧录的那份字幕，按配音真实停顿重排后的）。音乐设了 `bgm_loop` 循环时，脚本只量那一份文件，会把循环补出来的部分判成没响到片尾，此时以人工量为准。

8. **交付**：产出 final.mp4，附一句制作说明（用了哪些环节、哪些降级了）。

## 改一句配音（不重做整条）

某一句配音要换（口音、读错、挑了另一条录音）时，不要重配整篇：

1. 只重录这一句；需要人挑的话，单句多录几条。
2. 裁掉新录音首尾的静音。
3. 接缝处各做 15–20 毫秒的淡入淡出（交叉淡化），不要硬切。
4. 句与句之间的停顿保持原来的长度。
5. 换完后，这一句之后的每条字幕和每个切点都按新的真实停顿重排，再重新合成。

## 编排原则

- **零件可缺**：缺图像/视频/TTS API key 的环节自动降级（图卡兜底 / 跳过配音），不阻断整体，并如实告知用户降级了什么。
- **先出 Plan**：涉及多个付费 API（生图/生视频/生乐）时，先向用户说明将调用哪些、大致耗时/花费，确认后再跑。
- **中间产物留档**：分镜图、配音、字幕和 storyboard 都写进 `outputs/主题名/assets/`，方便单独替换后重新合成。

## Profile 感知

- 有 Profile：从 `style.md` 取调性/视觉风格贯穿文案与配图 prompt；`platforms.md` 只用于给出画幅/时长建议，画幅仍须确认；`preferences.md` 红线过滤。
- `preferences.md` 的「字幕规格」点名不许拆开的词（如品牌词、产品名）时，把它们逐个写进 storyboard 的 `subtitle_keep_words`；合成器不读 Profile 文件，只认 storyboard。
- `preferences.md` 的「字幕规格」给了字号时，把它写进 storyboard 的 `subtitle_size`（正整数，像素）；不写就是默认 54，字幕会偏小。
- 无 Profile：先确认横版/竖版，再用通用口播风格。
