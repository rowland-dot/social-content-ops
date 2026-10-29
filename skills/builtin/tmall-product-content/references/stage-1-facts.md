# 阶段 1：事实与卖点表

来源：规格 “Stage 1 — Fact and claims sheet”。本页不加规格里没有的规则。

## 规格怎么说

- 输入：品牌资料；产品在澳洲官网上的当前页面（资料互相矛盾时以它为准）；品牌团队的产品工具包和现有中文文案；知识库里的 2026 价格表（只取售价，成本、利润和其他列一律不读，负责人）；店铺发货路线（国内保税仓，负责人）。
- 输出：一张表，列出每条事实（规格、用量、产地、类型、保质期、认证、售价、发货路线）和每条允许说的卖点，各带来源；还有一份禁用说法清单，来自品牌资料的红线、合规底线和天猫规则。
- 矛盾：官网不能定论的就标 “waiting on 负责人”，不进页面。两份价格表对不上的价格也一样。
- 图片清单（负责人）：品牌资料和知识库里每张真实包装照，按角度（正、背、侧、顶、打开）列出；产品已有的每个视觉（含团队 2026-10-23 的修订稿）各标 “use as is”“crop” 或 “reference only”。包装从不重画，所以这份清单决定了任何一张图能出现哪些包装角度。

## 命令

- 事实表写在产品文件夹里的 `fact-sheet.json`。
- 检查：`python skills/builtin/tmall-product-content/scripts/tmall_facts.py check outputs/<Brand>/天猫商品内容/<product>`；有问题时退出码 1 并逐条列出。
- 生成可读版：`python skills/builtin/tmall-product-content/scripts/tmall_facts.py render outputs/<Brand>/天猫商品内容/<product>` 写出 `fact-sheet.md`，等待项排在最前，每个来源的值都列出。
- 价格函数在 `tmall_prices.py`（只读售价列，其余列不读；每日价、每份价由代码算出并带依据）。
