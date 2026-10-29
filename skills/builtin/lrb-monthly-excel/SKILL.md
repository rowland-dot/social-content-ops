---
name: lrb-monthly-excel
description: 客户 LRB 月度计划和月报 Excel 的唯一做法：以团队底稿为准，调用负责人的 LRB 剧本脚本，通过 verify 和格式核对才能交付。当用户说月度计划 Excel、客户 Excel、月报 Excel、LRB Plan、LRB Report，或内容排期要做成交给客户的表格时使用。
layer: plan
---

# LRB 月度计划 / 月报 Excel

所有品牌的 LRB 月度计划和月报 Excel 只走这一条路，计划和月报同一条。**不要自己用 openpyxl、xlsx 技能或别的技能手工搭一个工作簿，也不要从别的文件复制格式**：负责人已经把外观写进剧本和脚本，手工搭出来的文件会偏离模板（有几个品牌十一月的计划就是这样偏的）。

固定依据（都在负责人的 LRB 文件夹里，WSL 里是 `/mnt/c/Users/<user>/Claude Cowork/LRB Plan & Report`）：

- 剧本 `playbooks/LRB Report and Plan Formatting Playbook.md`：动手前从头读完。
- 脚本 `playbooks/scripts/planstyle.py`、`reportstyle.py` 和它们的 `verify()`：只在原地被调用。**不要改**、不要复制、不要分叉这个文件夹里的任何东西。
- 用 Easel 自己的 Python 运行（项目根的 `.venv/bin/python`；系统自带的 python3 没有 openpyxl）。LRB 文件夹不在默认位置时加 `--lrb-dir`，或设环境变量 `LRB_DIR`。

## 1. 来源

来源只有一种：**团队的底稿**，原样用，一个字不先改（钉钉、邮件里收到的那份）。

- 团队没发底稿、由 Easel 写计划时，先把 Easel 已批准的排期写成一张"底稿形状"的表：从 A 列起，标题行、表头行、日程行、一行空行、`Work plan breakdown` 块。这是底稿，不是成品；之后一样走下面的步骤。
- 绝不用别的方式搭工作簿，绝不从别的成品复制格式或底色。

## 2. 内容改动

格式步骤只改格式，不改标题、数字、日期、链接和评论文字（剧本规则 3）。内容问题（错月份、错别字、emoji）单独列给负责人裁定：

- 只有负责人已经批准的改动才执行：写成 JSON 列表，每条 `old`（该单元格的完整原文）、`new`、`ruling`（负责人的原话），用 `--changes` 传入。`ruling` 必须把负责人的原话放在引号里（`"…"` 或 `「…」`），不要写成转述或摘要；没有引号里的原话，这条就不执行，整次运行停下。`old` 必须正好对上一个单元格，对不上就停。
- 同一段文字出现在好几个单元格时（例如 8 行都是 `产品推荐 / Product Recommendation`），在这条改动里指明是哪一格，坐标按**成品文件**算（也就是 `APPLIED` 行和报错里显示的那种）。两种写法选一种，不能同时用：
  - 按格子：`{"cell": "C10", "old": "…", "new": "…", "ruling": "负责人：\"…\""}`
  - 按日期加列：`{"date": "2026-11-27", "column": "C", "old": "…", "new": "…", "ruling": "…"}`（日期写成 `2026-11-27` 或底稿里的 `27/11/2026` 都行，只能对上一行）
  - 指明了格子，`old` 仍然要等于那一格的完整原文，对不上就停并显示那一格实际写的是什么。没指明格子、文字又对上不止一格时，报错会列出每一个对上的格子（比如 `C3, C4, …`），照着报错加上 `"cell"` 再跑。文字只对上一格时不用指明。
- 运行时单独列出：`APPLIED`（已执行的）和 `OFFERED`（建议、没执行的，例如英文行里的全角"｜"换成冒号）。加 `--changes-out` 可另存成 Markdown 清单给负责人。把这两类原样转给负责人，不要合并进成品文件里。

## 3. 整理形状（只动格式）

`build` 自动做，每做一项打印一行 `SHAPE`：

- 表从 B 列起的，移到 A 列（排版脚本要求）。
- 重复的 `Work` 标题行（只有标题、没有标签）删掉，只留真正的 `Work plan breakdown` 行。
- 日程和 Work 块之间多出的空行删到只剩一行。
- 英文行里有全角字符（"｜"、"！"、"）"）的，排版脚本会把它当中文、把两行并成一行：`build` 让它保持在第二行，文字一个字符不变，并打印 `KEPT-LINE`。
- 底稿带的任何底色（含白色底、主题色底、只有颜色没有文字的格子）全部清掉，一格不留：剧本写的是，负责人 2026-10-17 的裁定是。每清掉一种颜色打印一行 `CLEARED`（颜色、格数、位置），不改任何文字。

## 4. 排版

```bash
python skills/builtin/lrb-monthly-excel/scripts/lrb_excel.py build --kind plan \
    --source "<团队底稿>.xlsx" --out "outputs/<品牌>/YYYY-MM 月度计划/<Brand> LRB Plan Mmm YYYY.xlsx" \
    --sheet "Mmm YYYY" --logo "<LRB 文件夹>/files/Logos/<Brand> Logo.png" [--changes changes.json]
python skills/builtin/lrb-monthly-excel/scripts/lrb_excel.py build --kind report \
    --source "<团队月报>.xlsx" --out "outputs/<品牌>/YYYY-MM 月度计划/<Brand> LRB Report Mmm YYYY.xlsx" --sheet "Mmm YYYY"
```

- 文件名按剧本第 2 节：`Brand LRB Plan Mmm YYYY.xlsx` / `Brand LRB Report Mmm YYYY.xlsx`，只用字母和空格。`--out` 必须在 `outputs/<主题>/` 下。
- 底稿自带 logo 时可省 `--logo`；底稿没有时必须给。负责人审过之前不放进 `Claude outputs`。

## 5. 检查

`build` 排完版自动跑下面的检查，任何一项 `FAIL` 都让这次运行失败（退出码 1），**这份文件不能交**：

- `verify`：负责人脚本自带的 `verify()`（打开位置、冻结、缩放、标题选中、公式值）。
- `logo`：标题行有 logo，高度不超过 84 px、宽度不超过 280 px，比例不变形。
- `spacer`（只对计划）：日程和 Work 块之间正好一行空行。
- `bilingual`：每个双语单元格第一行中文、第二行英文。
- `chars`：没有 U+2010 到 U+2012、U+200D、U+00A0。
- `font`：有内容的单元格全是 Arial。
- `fills`：成品里一格底色都不能有（白色底也算）。排版脚本自己留下了颜色时，这一项会 `FAIL` 并列出颜色和位置；不要手工去改成品，回到第 3 步查原因。

已有的成品要核对时用 `check`，它不改文件：

```bash
python skills/builtin/lrb-monthly-excel/scripts/lrb_excel.py check --kind plan "<成品>.xlsx"
```

最后一行是 `RESULT OK` 才算过。向负责人交付时附上 `APPLIED`、`OFFERED`、`SHAPE`、`CLEARED` 这几类行里出现的内容。
