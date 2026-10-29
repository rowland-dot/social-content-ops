# Easel SKILL 元数据

| 字段 | 值 |
|------|-----|
| **SKILL 名称** | skill-xhs-note-reader |
| **所属层** | discover |
| **来源类型** | 自研（移植 FavSense 的抽取逻辑） |
| **原始来源** | FavSense（小红书收藏整理项目，`C:\Users\<user>\Codex\小红书收藏整理`）：取帧上限、识字、语音上限、点点的浏览器流程（FavSense 的 xhs-diandian-summarize-note 技能）和回复过滤规则。复制而来，运行时不引用 |
| **参考项目** | 无 |
| **许可** | 项目内部 |

| 文件 | 作用 | 依赖 | 含 selftest |
|------|------|------|------|
| `scripts/read_note.py` | 读一条笔记并把全部内容存进一个文件夹：图片、图里的字、视频、取帧、语音、点点总结，`record.json` 记每一项的结果。所有对小红书的请求都经 `redbook` 守卫 | 守卫（`skill-xhs-analyzer`）、ffmpeg、`rapidocr_onnxruntime`、`skills/shared/scripts/asr.py` | 否，测试在 `tests/test_read_note.py` |
| `scripts/diandian_reply.py` | 判断点点的回复能不能存成总结（拒绝、被截断、太短、带访问码都不存），去掉结尾套话。FavSense 规则的移植（commit 756ec6d、746ebca） | 标准库 | 否，测试在 `tests/test_diandian_reply.py`，用 FavSense 自己的真实回复表（`tests/fixtures/`，commit 62e8fce、756ec6d） |

| `scripts/study_topic.py` | 主题研究（issue 84）：一次搜索、按点赞加收藏取最高 N 篇图文、用 `read_note.py` 存下每套全部图片、一套一个文件夹放进品牌的 `对标笔记库/image-sets`，写索引，检查每张图；小结由 Easel 对着图写，没写全不算做完。排名公式取自 `skill-post-scorer/scripts/score.py` | `read_note.py`、守卫、`skill-post-scorer`、Pillow | 否，测试在 `tests/test_study_topic.py` |

守卫一侧的改动（下载、点点两个步骤，驱动浏览器的 `xhs-diandian-driver.mjs` 和从 FavSense 复制来的 `diandian-contract.json`）在 `skills/builtin/skill-xhs-analyzer/scripts/`。共用转写脚本 `skills/shared/scripts/asr.py` 加了 `--max-seconds`。

> 来源：issue 70（2026-10-23）。负责人的原话见项目根 `CLAUDE.md` 第八条允许的情形。
