# 阶段 5：图片（头图三个版本，负责人先选）

来源：规格 `work/docs/specs/2026-10-25-tmall-product-content-spec.md` 的 “Stage 5 — Images”，以及负责人 2026-10-28 的两次选择。本页不加规格里没有的规则。

## 规格怎么说

- 场景图：用 Codex 订阅出，图里没有字、没有包装。计划里给包装留出位置。模型可以看包装照片来规划空位和光线，但它画出来的包装不留。
- 包装：用品牌资料里的真实包装照，作为单独一层叠上去，只缩放、只挪位置，绝不重画、改色、变形（负责人）。
- 字和排版：用代码在场景和包装之上排好。输出：主图是规则文件 `main_image.sizes` 里的一个尺寸（阶段 3 在方案的 `main_size` 里定），详情切片 790 宽。
- 头图先做，三个版本，方向不同（角度、取景、先讲什么），各自参照阶段 2 里不同的领先商品。三个版本都过阶段 6 之后并排给负责人看。他选定之后才做其余主图和详情屏，并沿用头图的光线、配色和字体。负责人的评语会先改样式锁，再做别的。

## 命令和函数

除了 `tmall_flow.py status` 以外，本阶段的模块都当函数调用：下面的短脚本是完整可运行的例子，把版本放进 `headline/A`、`headline/B`、`headline/C` 三个文件夹。

- 每个版本都以名字 `M1` 做在自己的文件夹里：`headline/A/M1.png`、`headline/B/M1.png`、`headline/C/M1.png`。名字必须是 `M1`：`gather` 靠开头的 `M` 分主图和详情切片，靠计划里的编号找头图的卖点。叫 `A` 会被当成 790 宽的切片，尺寸不对；叫 `M1A` 找不到任何卖点，那项检查等于什么也没查。三个文件夹各放各的，三个版本才不会互相覆盖文件。
- `headline-versions.json` 里每个版本的 `image` 写成 `headline/<A|B|C>/M1.png`，`report` 是这个版本自己的 `gather` 结果。
- 负责人选定后，调用 `tmall_flow.promote_pick(product_dir, state)`：把选中版本的 `M1` 文件原样复制到产品文件夹里，这样审批页和交付都能在 `M2` 到 `M5` 旁边找到 `M1`。选中版本自己的报告就是审批页要的 `M1` 报告，因为字节没变。
- 流程状态只用 `tmall_flow.load_state` 和 `save_state` 读写，不自己写 JSON。
- `compose(...)` 和 `gather(...)` 都要带样式锁版本：`style_lock_version` 传给 `compose`，同一个数当作 `version` 放进给 `gather` 的样式锁。负责人的评语会让版本号加一，之前做的图因此检查不过（行为 9）。
- 场景图：`tmall_scene.generate_scene` 在 `references/held.json` 说放行之前会拒绝（HELD）。放行前不要生成场景；只用已有的图或负责人给的图。

## 完整例子

在项目根目录运行：`python <这个脚本> outputs/<Brand>/天猫商品内容/<product>`。

```python
import sys, json
from decimal import Decimal
from pathlib import Path
SKILL = Path("skills/builtin/tmall-product-content")
sys.path.insert(0, str(SKILL / "scripts"))
import tmall_checks, tmall_compose, tmall_flow, tmall_note, tmall_plan, tmall_rules
import tmall_common as common

PRODUCT = Path(sys.argv[1])
PACK_DIR = Path("profiles/<brand>/packs")      # 填：事实表“图片清单”里包装照所在的文件夹
NOTE = Path("pattern-note.md")                  # 填：从知识库取出来的竞品规律笔记（不进仓库）

state = tmall_flow.load_state(PRODUCT)
sheet = common.read_json(PRODUCT / "fact-sheet.json"); plan = common.read_json(PRODUCT / "plan.json")
rules = tmall_rules.load()
W, H = plan["main_size"]                        # 阶段 3 定的主图尺寸，必须是规则文件 main_image.sizes 里的一个；下面的位置都按它的比例算
TEXTS = {k: [{"id": "headline", "text": "每天一勺", "tier": "headline", "x": W // 20, "y": W // 20, "w": W * 9 // 10, "px": W * 2 // 25,
              "color": "#ffffff", "font": "Noto Sans CJK SC", "weight": 700, "claims": ["C1"]}] for k in "ABC"}   # 填：已核对的文案
lock = {**plan["style_lock"], "version": state["style_lock_version"]}
photo = next(i["file"] for i in sheet["inventory"] if i["use"] != "reference only")
prices = {Decimal(f["text"]): f["source"] for f in sheet["facts"] if f["kind"] == "price" and f["status"] == "settled"}
versions = {}
for key in "ABC":
    out = PRODUCT / "headline" / key
    m = tmall_compose.compose(out, "M1", scene=PRODUCT / "scenes" / f"M1-{key}.png", size=(W, H), texts=TEXTS[key],
                              pack={"file": PACK_DIR / photo, "height": H * 3 // 5, "cx": W // 2, "bottom": H * 9 // 10},
                              style_lock_version=state["style_lock_version"])
    report = tmall_checks.gather(out, manifest=m, rules=rules, sheet=sheet, selling_points=plan["selling_point_map"],
                                 plan_problems=tmall_plan.validate(plan, sheet, rules), allowed_prices=prices, bundle_rows=[],
                                 competitor_strings=tmall_note.competitor_strings(NOTE.read_text(encoding="utf-8")), style_lock=lock)
    versions[key] = {"image": f"headline/{key}/M1.png", "headline": "每天一勺", "direction": f"方向 {key}",
                     "listing_id": f"listing-{key}", "report": report, "checks_passed": report["passed"]}
(PRODUCT / "check-reports.json").write_text(json.dumps(
    {"reports": {f"M1-{k}": v["report"] for k, v in versions.items()}, "not_confirmed": tmall_rules.not_confirmed(rules)},
    ensure_ascii=False, indent=1), encoding="utf-8")
if all(v["checks_passed"] for v in versions.values()):
    tmall_flow.register_versions(state, versions)
    (PRODUCT / "headline-versions.json").write_text(json.dumps(versions, ensure_ascii=False, indent=1), encoding="utf-8")
tmall_flow.save_state(PRODUCT, state)
# 检查没过或还缺结果（要用眼看的三项、被搁置的质量检查）：运行 tmall_page.py report 生成 check-report.html，用文字告诉负责人哪项没过、哪项没跑
# python skills/builtin/tmall-product-content/scripts/tmall_page.py report <product_dir>
# 负责人选定之后：tmall_flow.pick(state, "B"); tmall_flow.promote_pick(PRODUCT, state); tmall_flow.save_state(PRODUCT, state)
```

## 做完之后

1. `python skills/builtin/tmall-product-content/scripts/tmall_page.py report outputs/<Brand>/天猫商品内容/<product>` 写出 `check-report.html`，打开给负责人看每张图哪项没过、哪项没跑。
2. 三个版本都通过后：`tmall_page.py headline` 写出并排对比页；没通过的版本这个页面不显示。
3. 其余主图和详情屏要等负责人选完才做（`tmall_flow.may_make`）。
