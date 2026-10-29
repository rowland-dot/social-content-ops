# meta.json Schema

`meta.json` 是每篇文章目录下的核心元数据文件。不同平台共用下面的基础字段，平台特有字段附加在各自扩展里。

## 基础字段（所有平台）

```json
{
  "title": "文章标题",
  "summary": "一句话摘要",
  "author": "",
  "platform": "公众号 | 小红书 | 头条号 | 通用",
  "created_at": "ISO 8601 时间（Asia/Shanghai）",
  "tags": ["标签1", "标签2"],
  "word_count": 0,
  "cover_image": "封面图文件名（可选）",
  "images": ["images/下的相对路径列表"],
  "references": {
    "search_queries": ["使用的搜索关键词"],
    "source_count": 0,
    "summary_file": "reference/summary.md"
  }
}
```

## 公众号扩展字段

```json
{
  "platform": "公众号",
  "theme": "橙心",
  "cover_image_prompt": "英文生图 prompt（可选）",
  "cover_image_url": "封面图上传后的 URL（可选，发布阶段写入）",
  "wechat": {
    "draft_media_id": "",
    "published_url": ""
  }
}
```

## 小红书扩展字段

```json
{
  "platform": "小红书",
  "post_format": "image | video",
  "caption": "发布文案，目标 300 字左右，100-1000 字均可（800 字以上校验会警告）",
  "hashtags": ["#话题1", "#话题2"],
  "poster_style": "card-design 风格名（如 瑞士极简 / 杂志编辑 / 手账贴纸 / 奶油温柔 …见 card-design/references/styles.md）",

  "creation_guide": {
    "path": "profiles/<账号>/creation-guide.md",
    "date": "写帖子前读的那份创作指南的最后修改日期，YYYY-MM-DD"
  },

  "claims": [
    {
      "text": "帖子里写的那句事实声明，原话",
      "evidence_type": "brand_document | fetched_reference | team_statement | user_material",
      "source": "证据位置：文件路径 / 网址 / 引用的原话"
    },
    {
      "text": "没有证据的那句声明，原话",
      "fallback": "removed | reworded",
      "now": "reworded 时必填：改写后的新说法（必须出现在帖子里）"
    }
  ],

  "card_count": 7,
  "cards": [
    {
      "page": 1,
      "type": "cover | content | ending",
      "title": "卡片小标题（cover/content）",
      "content": "卡片正文（≤80 字中文）",
      "synthesis_strategy": "html_card | text_on_photo | collage | photo_scene",
      "material_refs": ["m001", "m002"],
      "image_prompt": "图片生成 prompt（可选）",
      "image_url": "卡片图片 URL（可选）"
    }
  ],

  "shots": [
    {
      "index": 1,
      "duration_sec": 3.0,
      "narration": "口播 ≤30 字",
      "on_screen_text": "屏幕字 ≤15 字",
      "visual": "画面描述",
      "material_ref": "m002"
    }
  ],

  "materials": [
    {
      "id": "m001",
      "path": "reference/<相对路径或原始绝对路径>",
      "kind": "text | image | video | audio",
      "caption": "画面描述",
      "usage": "cover | content-N | ending | reference-only | discard",
      "strategy": "html_card | text_on_photo | collage | photo_scene | use_original"
    }
  ]
}
```

字段使用规则：

- `post_format` = `image` 时，`cards[]` 必填、`shots[]` 省略
- `post_format` = `video` 时，`shots[]` 必填；`cards[]` 只需一张 `cover` 作为封面
- `materials[]` 仅在用户提供了素材时出现；详细工作流见 `material-intake.md`
- `synthesis_strategy` 为每张卡选择合成路径；`material_refs` 指向 `materials[].id`
- `photo_scene`：用户在开场提问里选了照片场景帖时才用，该卡的图由 xhs-reference-visual 出

## 创作指南记录 `creation_guide`（小红书，必填，issue 125）

写帖子之前先读这个账号的创作指南（`python3 skills/shared/scripts/creation_guide.py check --brand <账号>`），`creation_guide` 记下读的是哪一份：`path` 是命令打印的路径，`date` 是它打印的最后修改日期。`validate_meta.py` 拒绝缺了它、路径为空或日期格式不对的新帖子。

## 声明记录 `claims`（小红书，必填，issue 102）

记录帖子**自己写的**每一句事实声明：功能、功效、参数、规格、含量、成分、工艺名、认证、专业术语。范围是长文原稿、caption、每张卡的标题和正文（所有出图路径，含 `photo_scene`）、视频每个分镜的口播和屏幕字。帖子没有任何事实声明时写 `"claims": []`，"没有"也是一个明确的结果。

- 每条要么有证据（`evidence_type` + `source`），要么有兜底（`fallback`），二选一：
  - `brand_document`：客户知识库里的品牌文件（档案、详情页、证书等），`source` 写文件位置
  - `fetched_reference`：存在本篇 `reference/` 里的抓取原文，`source` 写相对路径（如 `reference/ref_001.md`），文件必须存在
  - `team_statement`：负责人或团队说过的话，`source` 写引用的原话
  - `user_material`：用户自己的照片或视频（按画面内容判断），`source` 写位置；相对路径必须存在于本篇目录
  - `removed`：证据找不到，把这句从帖子里删掉（`text` 不能再出现在帖子里）
  - `reworded`：证据找不到，改写成不构成事实声明的说法（比如读者看到什么、做什么），`now` 写新说法，且必须出现在帖子里
- 兜底**不得**把声明改成编造的亲身体验或用户反馈（"自用、回购、亲测"需要真实素材；见 `skill-quality-gate/references/general-rules.md` 禁止伪造用户反馈或案例）
- 商品包装上印的文字不算声明，也不算证据：不写进 `claims`，也不能拿来当 `source`
- `validate_meta.py` 会拒绝：缺少 `claims`；条目既无证据也无兜底、或证据类型/兜底不在上表；有证据的 `text` 或 `reworded` 的 `now` 没有一字不差出现在帖子里（这样没写进帖子的包装文字进不来）；`removed` 的 `text` 仍在帖子里；本篇目录内的证据文件不存在。知识库路径、网址、引用原话只要求非空。

## 字段规则

- **title**：≤30 字，公众号 ≤64 字符会被微信截断；小红书建议 10-20 字带 emoji
- **summary**：公众号 ≤20 字（微信摘要字段 ≤120 字符）；小红书无 summary，用 caption
- **created_at**：ISO 8601 带时区，例 `"2026-04-24T15:00:00+08:00"`
- **word_count**：正文字数（不含标题、摘要、caption）
- **images**：只列 `images/` 下的相对路径，不含外链
- **references.source_count**：去重后的来源数

## 完整示例

### 公众号

```json
{
  "title": "AI 冲击就业？Anthropic 最新研究揭示劳动力市场的真相",
  "summary": "失业率在下降，新岗位在增加。数据比标题党更有说服力。",
  "author": "",
  "platform": "公众号",
  "created_at": "2026-04-24T15:00:00+08:00",
  "theme": "橙心",
  "tags": ["AI", "就业", "劳动力市场"],
  "word_count": 3040,
  "cover_image": "cover.jpg",
  "cover_image_prompt": "A professional workspace, clean desk, soft natural light",
  "images": ["images/img_001.jpg", "images/img_002.jpg"],
  "references": {
    "search_queries": ["AI 失业 2026", "Anthropic economic index"],
    "source_count": 6,
    "summary_file": "reference/summary.md"
  }
}
```

### 小红书

```json
{
  "title": "💼 AI 失业危机？数据告诉你真实情况",
  "platform": "小红书",
  "created_at": "2026-04-24T15:00:00+08:00",
  "caption": "媒体说危机，数据说增长。Anthropic 调研 5000 人，83% 说 AI 提高效率而非取代……",
  "hashtags": ["#AI对工作的影响", "#失业危机是假的"],
  "poster_style": "杂志编辑",
  "creation_guide": {"path": "profiles/example/creation-guide.md", "date": "2026-10-29"},
  "claims": [
    {
      "text": "Anthropic 调研 5000 人",
      "evidence_type": "fetched_reference",
      "source": "reference/ref_001.md"
    }
  ],
  "card_count": 7,
  "cards": [
    {
      "page": 1,
      "type": "cover",
      "title": "💼 AI 失业危机？",
      "content": "媒体说危机，数据说增长\n美国失业率：4.2%→3.8%"
    }
  ],
  "images": [],
  "references": {
    "search_queries": ["AI 就业影响 2026"],
    "source_count": 4,
    "summary_file": "reference/summary.md"
  }
}
```
