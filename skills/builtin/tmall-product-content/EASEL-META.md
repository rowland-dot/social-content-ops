# Easel SKILL 元数据

| 字段 | 值 |
|------|-----|
| **SKILL 名称** | tmall-product-content |
| **所属层** | produce |
| **来源类型** | 自研 |
| **原始来源** | 无。按规格 `work/docs/specs/2026-10-25-tmall-product-content-spec.md` 在 Easel 里新建；复用 Easel 自己的卡片渲染（`render_card.py`）、输出路径规则（`output_paths.py`）和已保存登录的写法（`login_state.py`） |
| **参考项目** | 无 |
| **许可** | 项目内部 |

| 文件 | 作用 | 依赖 | 含 selftest |
|------|------|------|------|
| `scripts/tmall_common.py` | 产品文件夹路径、哈希、原子写 JSON | 标准库 | 否，测试在 `tests/test_tmall_common.py` |
| `scripts/tmall_held.py`、`references/held.json` | 图片工具和质量检查的搁置，缺失一律当作搁置 | 标准库 | 否 |
| `scripts/tmall_prices.py` | 只读价格表的售价列；每日价、每份价由代码算并带依据 | openpyxl（只在读表函数里导入） | 否 |
| `scripts/tmall_facts.py` | 事实表：定矛盾、检查、生成可读版（`check`、`render`） | 标准库 | 否 |
| `scripts/tmall_rules.py`、`references/tmall-rules.md` | 天猫规则文件（说明加一个数据块）及其读取函数 | 标准库 | 否 |
| `scripts/tmall_fonts.py`、`references/fonts-licensed.json` | 从字体文件本身读授权 | fontTools | 否 |
| `scripts/tmall_plan.py` | 页面方案检查（`check`） | 标准库 | 否 |
| `scripts/tmall_copy.py` | 每屏字数预算；卖点和价格追溯 | 标准库 | 否 |
| `scripts/tmall_compose.py` | 场景 + 真实包装 + 代码排的字，生成分层文件和清单 | Pillow、Playwright | 否 |
| `scripts/tmall_layers.py`、`scripts/tmall_checks.py` | 量出来的分层检查；阶段 6 报告和重做轮次 | Pillow、numpy | 否 |
| `scripts/tmall_psd.py`、`scripts/tmall_handover.py` | 分层 PSD 和上传用文件夹 | Pillow | 否 |
| `scripts/tmall_flow.py` | 头图三选一、意见、只重做受影响的图（`status`） | 标准库 | 否 |
| `scripts/tmall_page.py` | 审批页、头图对比页、检查报告页（`approval`、`headline`、`report`） | 标准库 | 否 |
| `scripts/tmall_results.py` | 前后四周窗口和单品表读取 | openpyxl（只在读表函数里导入） | 否 |
| `scripts/tmall_scene.py` | 唯一调用 Easel 出图脚本的地方；搁置且从不付费 | 标准库 | 否 |
| `scripts/tmall_capture.py`、`scripts/tmall_note.py` | 竞品抓取、存入知识库、规律笔记检查（`run`、`deposit`、`trial-sheet`、`check`） | Playwright | 否 |
| `skills/shared/scripts/tmall_login.py` | 保存的天猫登录，一次扫码（`login`、`status`）；不改任何已有登录脚本 | Playwright | 否 |
| `skill-text.test.py` | 技能文字检查（紧贴技能的检查文件） | 标准库 | 是 |

> 来源：天猫商品内容区域（负责人 2026-10-25：；设计 2026-10-28 批准）。允许范围见项目根 `CLAUDE.md`。图片工具和质量检查在 Easel 的 issue 94 和 95 合并之前搁置。
