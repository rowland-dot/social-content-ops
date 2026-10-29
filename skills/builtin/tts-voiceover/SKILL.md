---
name: tts-voiceover
description: "文字转语音配音：把文案/脚本合成为 AI 语音口播、旁白、朗读音频。**配了 VOICE_PROVIDER 默认走闭源云 TTS（CosyVoice2 等，有情感、像真人），edge 仅无 key 时兜底**（edge 偏机械/AI 味）；同步输出分句 SRT 字幕、mp3/wav/m4a。合成后可与 BGM 混音或加到视频作旁白。当用户说“配音”“文字转语音”“TTS”“AI 配音”“口播语音”“旁白”“朗读”“把这段文字读出来”“生成语音”“语音合成”时使用。"
layer: produce
---

# 文字转语音配音（TTS Voiceover）

> **配置检查路径铁律**：先 `cd` 到运行时说明给出的 Easel 项目根，确认当前目录有 `.env` 和 `skills/shared/scripts/`。云 TTS 配置只能用项目根的 `skills/shared/scripts/model_registry.py configured --group voice --env-file .env` 和 `skills/shared/scripts/voice_clone.py check ... --env-file .env` 判断；不得在 workspace 跑共享脚本副本，也不得用 `env` / `printenv` 推断 Key/URL 缺失。

把文案 / 脚本合成为 AI 语音（口播、旁白、朗读）。共享脚本 `skills/shared/scripts/tts.py speak`：
**默认闭源优先**——配了 `.env` 的 `VOICE_PROVIDER`(+ VOICE_API_KEY) 就走闭源云 TTS（voice_clone，
按句合成+拼接+分句 SRT，有情感、像真人），**没 key 才退 edge**（AI 味、生硬，仅兜底）。
`--engine closed/edge` 可强制；闭源音色用 `--voice` 传 voice-id（如 `FunAudioLLM/CosyVoice2-0.5B:alex`），
旁白默认 alex，可用 `VOICE_NARRATOR_VOICE_ID` 覆盖。合成后语音可交 `audio_ops.py`/`video_ops.py` 混音或加到视频。

## 走 ChatGPT 订阅（没有 key，不按次计费）

`.env` 写 `VOICE_PROVIDER=chatgpt`，配音走负责人的 ChatGPT 订阅里网页版的「朗读」，不需要任何 key。

- **前提**：专用 Chrome（资料夹 `C:\Users\<user>\.easel-browser\chatgpt`，调试端口 9230）开着，并且 ChatGPT 已登录。
  先跑 `python skills/shared/scripts/voice_clone.py check --provider chatgpt` 看是否就绪；没就绪就停下来告诉负责人，
  不要换成别的 provider。
- **做法**：整篇文案交给 `tts.py speak`，它自己按约 160 字一块切好，每块在 ChatGPT 新开一个普通对话、
  要求逐字重复，回复与原文不一致就整条作废（什么都不保存），一致才取它的朗读音频，最后拼成 mp3 并写分句 SRT。
  所以不要自己逐句调用；每块是一整趟浏览器往返（约 20 秒），长文案要等。每次配音会在负责人的 ChatGPT 历史里留下对话。
- **声线**：ChatGPT 设置页上的九个声线都能用，`--voice` 传设置页上的名字（任意大小写）或朗读用的 id；不给 `--voice` 就是 Cove。
  名字和 id 不总是一样，下表是 2026-10-15 从 ChatGPT 自己读到的声线表（它设置页用的 `/backend-api/settings/voices`），
  九个都录过试音（同一句话各读一遍，在 `outputs/chatgpt-voice-samples/`；选哪个声线由人听了定，各品牌的选角写在各自的 Profile 里，不写在这里）：

  | 设置页名字 | 朗读用的 id | OpenAI 的描述 |
  |---|---|---|
  | Sol | `glimmer` | Savvy and relaxed |
  | Cove（默认） | `cove` | Composed and direct |
  | Vale | `vale` | Bright and inquisitive |
  | Spruce | `orbit` | Calm and affirming |
  | Arbor | `fathom` | Easygoing and versatile |
  | Juniper | `juniper` | Open and upbeat |
  | Breeze | `breeze` | Animated and earnest |
  | Ember | `ember` | Confident and optimistic |
  | Maple | `maple` | Cheerful and candid |

  不认识的声线名会直接报错并列出这九个，不会悄悄换成 Cove，也不会退回 edge-tts（`marin` 和 edge 的音色名都不是 ChatGPT 的声线）。
  不能克隆声音，没有情绪参数。多角色配音（multi-voice-dubbing）每句台词也是一趟往返，九个声线可以任意分给不同角色
  （cast 里 `voice_id` 写设置页名字或 id，`cast check` 会先查名字对不对）。
- **失败**：浏览器没开、没登录、ChatGPT 改写了文案、音频长度对不上，都会明确报错。auto 模式会悄悄退回 edge-tts，
  **要保证走 ChatGPT 就加 `--engine closed`**。
- **口音和单句多录**：中文可能带口音，同一句每次生成的读法也不一样，没有任何设置能改。重要的句子要单句多录几条（`python skills/shared/scripts/tts.py speak --text "这一句" --engine closed -o outputs/主题名/line3_a.mp3`，每条是一趟浏览器往返），交给人挑；挑定后换进整条配音的做法见 [auto-short-video](../auto-short-video/SKILL.md) 的「改一句配音」。
- **分句时间**：整篇配完后，每一句的开口时间取自拼好的整段音频里的停顿，字幕随之对齐；某句附近没有找到停顿时，命令在 stderr 打印警告并沿用按字数估算的时间，那一句要用静音检测重新量。

## 输入

| 字段 | 必填 | 说明 |
|------|------|------|
| text / file | 是 | 待配音的文本，或文本文件路径（长文本推荐 --file） |
| voice | 否 | 音色，默认 `zh-CN-XiaoxiaoNeural`（晓晓） |
| rate/volume/pitch | 否 | 语速 / 音量 / 音调微调 |
| output | 否 | 默认 `outputs/主题名/{name}.mp3` |

## 输出

- 配音音频文件（mp3，可选 wav/m4a），放入 `outputs/主题名/`
- 可选同步输出 SRT 字幕（`--subtitle`），供视频烧字幕用
- 打印实际执行的 edge-tts 命令 + 输出文件时长/大小/音色

## 前置：外网代理

edge-tts 调微软在线服务，**必须能访问外网**。内网环境先设代理：

```bash
export https_proxy=http://<代理host>:<端口> http_proxy=http://<代理host>:<端口>
```

脚本会自动读环境变量代理并透传给 edge-tts（也可用 `--proxy` 覆盖）。

## 执行步骤

脚本路径（相对项目根）：`skills/shared/scripts/tts.py`。每个子命令支持 `-h`。

### 0. 挑音色（可选）

```bash
python skills/shared/scripts/tts.py voices          # 常用中文音色 + 简介
python skills/shared/scripts/tts.py voices --all    # 拉全量 zh- 音色（需外网）
```

### 1. 合成配音 speak

```bash
# 最简：一句话 → mp3
python skills/shared/scripts/tts.py speak --text "欢迎来到本期内容" \
  -o outputs/主题名/intro.mp3

# 长文本从文件读 + 换音色 + 加速 10%
python skills/shared/scripts/tts.py speak --file script.txt \
  -o outputs/主题名/narration.mp3 --voice zh-CN-YunxiNeural --rate +10%

# 同步出 SRT 字幕（视频烧字幕用）
python skills/shared/scripts/tts.py speak --file script.txt \
  -o outputs/主题名/vo.mp3 --subtitle outputs/主题名/vo.srt

# 输出 wav（需 ffmpeg，便于后续无损处理）
python skills/shared/scripts/tts.py speak --text "……" \
  -o outputs/主题名/vo.wav --format wav
```

参数：`--rate +10%`（语速）、`--volume +20%`（音量）、`--pitch +2Hz`（音调）。

### 2. 后处理（可选，复用已有共享脚本）

配音出来后按需接下游脚本，无需在本 SKILL 重造能力：

```bash
# ① 配音 + BGM 混音（原声 1.0 / BGM 0.3）→ 用 audio_mix.py mix（输出纯音频，时长同配音；
#    BGM 过短自动循环，默认在人声出现时压低 BGM（闪避），不需要可加 --no-duck）
python skills/shared/scripts/audio_mix.py mix --voice vo.mp3 --bgm bgm.mp3 \
  --voice-volume 1.0 --bgm-volume 0.3 -o vo_bgm.mp3

# ② 配音音量归一化到社媒响度（-14 LUFS）
python skills/shared/scripts/audio_ops.py normalize vo.mp3 -o vo_norm.mp3

# ③ 把配音作为旁白加到视频（旁白只播一次、不循环：--music-loop-off 防止它比视频短时从头再播；
#    加真正的背景音乐时不要带这个选项，音乐默认循环到视频结束）
python skills/shared/scripts/video_ops.py bgm -i clip.mp4 -o clip_vo.mp4 \
  --music vo.mp3 --voice-volume 0.4 --music-volume 1.0 --music-loop-off
```

## 常用中文音色

| 音色 | 特点 |
|------|------|
| `zh-CN-XiaoxiaoNeural` | 晓晓 · 女声，温暖亲和，通用首选（默认） |
| `zh-CN-XiaoyiNeural` | 晓伊 · 女声，活泼年轻，口播/种草 |
| `zh-CN-YunxiNeural` | 云希 · 男声，清朗自然，旁白/解说 |
| `zh-CN-YunyangNeural` | 云扬 · 男声，专业沉稳，新闻/播报 |
| `zh-CN-YunjianNeural` | 云健 · 男声，浑厚有力，激情内容 |

粤语用 `zh-HK-HiuMaanNeural`（曉曼），台式用 `zh-TW-HsiaoChenNeural`（曉臻）。

## 规则

1. **绝不覆盖原始素材** — 只写新文件到 `outputs/主题名/`。
2. **长文本走 --file** — 避免命令行过长 / 换行转义问题。
3. **先设代理** — edge-tts 需外网，网络失败脚本会给明确提示。
4. **不重造能力** — 配音+BGM 混音用 audio_mix.py，归一化用 audio_ops.py，加视频旁白用 video_ops.py。
5. **无 Profile 也能用** — 无画像时用默认音色晓晓。

## Profile 感知

有 Profile 时可读取账号偏好音色 / 语速 / 平台调性（如口播偏活泼晓伊、
知识类偏沉稳云扬）作为默认参数；无 Profile 退到通用默认（晓晓、正常语速）。
