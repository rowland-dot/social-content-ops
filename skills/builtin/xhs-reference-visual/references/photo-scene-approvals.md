# 照片场景帖：批准记录（issue 111）

每篇帖子一份批准记录，叫 `approvals.json`，放在这篇帖子的照片场景文件夹里，套系计划 `set-plan.md` 旁边。用户的批准不再写进套系计划，只写进这一份（issue 87 到 90 的“批准连同日期记在套系计划里”都改记到这里）。

来源：Lovart 技能包评审里的两句，原文照录。video-remake：“确认结果逐资产记录；修改或重生成会使旧确认失效。”design-brand-catalogs：“Invalidate dependent approvals when content, dimensions, page count, references, layout DNA, palette, typography, imagery, or output route changes.”

## 谁能让它多一条

只有用户自己的回复：计划页的批准（issue 87）、封面的选定（issue 88）、字体和样式的选定（issue 89）、整套页的批准（issue 90）、已批准卡改过之后的批准（issue 91）。Easel 自己的检查合格，从来不记成一条；沉默、没有反对、猜他会点头，都不算。

## 一条记录的字段

`id`；`card`（计划里的卡，或 `set` 表示整套）；`kind`（`plan-page`、`cover-pick`、`lettering-pick`、`set-page`、`card-change` 之一）；`file`（批准的那张图，相对这个文件夹；整套的计划页和字体选定也要给一张图，用选定的封面）；`base_file`（打字字体的整套才有：这张图设字之前的底图）；`date`；`words`（用户的原话，一字不改）；`deps`（依赖名对指纹）；`valid`；`voided`（没失效是空，失效是 `{dependency, found_on}`）。记录只加不删。

## 一张卡的批准靠什么

指纹按表、按行、按文件取，不取整个套系计划，所以记下一条批准、或改了别的卡的一行，都不会让别的卡失效。

- `row:<卡>`：这张卡在“逐张计划”表里的那一行；
- `file:layout-plan-<卡>.md`：这张卡的版面计划（有才算）；
- `table:颜色和层级`、`table:图标清单`（或“这套不用图标”那一句）；
- `file:typed-styling.json`：打字字体的整套才有；手绘的整套，字体选定就是选定封面的文件，见下一条；
- 封面以外的每一张卡：`file:<选定封面的文件>`；
- 提示词文件里列出的传入图：提示词文件里每行 `image: <路径>`（相对这个文件夹）。

整套的条目（`plan-page`、`lettering-pick`）靠五张表（研究的图集、封面方向、逐张计划、颜色和层级、图标清单）和 `typed-styling.json`；`plan-page` 这一种另外依赖计划页显示的整份 `set-plan.md`、`icon-list.md`、`layout-plan-card_1-ABC.md` 和每张其余卡的 `layout-plan-card_<N>.md`（issue 123），所以改了其中任何一个，计划页的批准就作废。指纹只取文件和计划里的文字，不读、不列、不报包装上印的字。

## 命令

```
python3 skills/builtin/xhs-reference-visual/scripts/approvals.py record --plan <set-plan.md> --card <卡|set> --kind <kind> --file <图> --date <YYYY-MM-DD> --words "<用户原话>" [--base-file <图>] [--prompt-file <提示词文件>]
python3 skills/builtin/xhs-reference-visual/scripts/approvals.py check --plan <set-plan.md>
```

- `record` 加一条，并取当下的指纹；记下一条不会让别的条目失效。
- `check` 把每条的指纹和磁盘上的文件对一遍。有对不上的，那一条标成 `valid: false`，`voided` 写明哪一项变了、哪一天发现的；已失效的不会被改回有效。退出码 0 是全部有效，1 是有条目失效（逐条打印卡和依赖），2 是输入有问题（没有记录文件、记录里的卡不在计划里、批准的图不在磁盘上），2 时什么都不写。

## 谁来读

- 什么算已批准：记录里有一条有效的，就是已批准；没有，或已失效，就不是。放不上的卡，按没有批准办。
- 失效的卡要用户再点一次头才算已批准。它最后批准的那张图仍在记录里；让它失效的那处改动如果就是用户要的那一处，按 issue 91 的规则，新的一版从那张图改起。
- 重画或修改出来的新版本从不继承批准：批准的条目仍指着批准的那一版，直到用户批准新的一版，再记新的一条。
- 先跑 `check`，再用：把一张卡当已批准的图传进 `--base-image` 之前（issue 91）；建整套页之前（issue 90）；交付之前。整套里有任何一张卡没有条目或条目失效，就不能当已批准交付，交付说明里写是哪几张。
- 负责人的第 5 步：。
