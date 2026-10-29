# Easel SKILL 元数据

| 字段 | 值 |
|------|-----|
| **SKILL 名称** | lrb-monthly-excel |
| **所属层** | plan |
| **来源类型** | 自研 |
| **原始来源** | 无。把负责人的 LRB 文件夹里的剧本和脚本（`playbooks/LRB Report and Plan Formatting Playbook.md`、`planstyle.py`、`reportstyle.py`）接成 Easel 里唯一的做法 |
| **参考项目** | 无 |
| **许可** | 项目内部 |

| 文件 | 作用 | 依赖 | 含 selftest |
|------|------|------|------|
| `scripts/lrb_excel.py` | `build`：团队底稿 → 整理形状 → 套用负责人批准的内容改动 → 调负责人的排版脚本 → 跑检查；`check`：核对已有成品。不改、不复制 LRB 文件夹里的任何脚本 | openpyxl；排版时需要 Pillow，以及 LibreOffice（WSL 里存公式值） | 否，测试在 `tests/test_lrb_monthly_excel.py` |
| `skill-text.test.py` | 技能文字检查（紧贴技能的检查文件） | 标准库 | 是 |

> 来源：issue 57（2026-10-17）。负责人的原话见项目根 `CLAUDE.md`。
