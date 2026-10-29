# 阶段 7：审批页

来源：规格 “Stage 7 — Approval page”，行为 3、4。本页不加规格里没有的规则。

## 规格怎么说

- 在负责人的浏览器里打开一个网页，按手机宽度显示五张主图和完整详情页，每张旁边是它的文案和每条卖点的来源。负责人批准，或给一条意见。
- 意见要经 Easel 回到阶段 3 到 6，绝不手改（行为 4：只重做受影响的图，其余原样不动，然后重新打开页面）。

## 命令

- 页面输入是产品文件夹里的 `approval-items.json`（`{"items": [...], "reports": {...}, "not_confirmed": [...]}`，每项带 `id`、`kind`、`image`、`copy`、`sources`）。
- 生成：`python skills/builtin/tmall-product-content/scripts/tmall_page.py approval outputs/<Brand>/天猫商品内容/<product>`，在浏览器里打开 `approval.html`（读工具结果确认真的打开了）。
- 图片没检查、报告缺失，或报告是为另一版图做的：退出码 2，页面不生成，并说明原因。
- 页面里的图叫 主图1 到 主图5、详情第1屏…，负责人的意见就用这些名字。
- 受影响的图用 `tmall_flow.reject` 登记，`tmall_flow.changed_outside` 核对其余图没变。
