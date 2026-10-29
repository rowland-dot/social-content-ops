# 其余的卡一气画完，再并排给用户看（issue 90）

负责人的规则（CLAUDE.md“Photo-scene post images follow one approval process”第 4 步）

SKILL.md 只留步骤和这条规则，细则都在这里。

## 什么时候开始画

封面和字体都选定之后：套系计划里已记下选定的封面（见 [photo-scene-cover-versions.md](photo-scene-cover-versions.md)）和选定的字体与样式（见 [photo-scene-lettering-picks.md](photo-scene-lettering-picks.md)），再加上用户已批准的计划页。这就是放行，不再问用户。这条路线用 Codex，不花钱（耗的是负责人的 ChatGPT 额度），所以不需要另外要一个 yes。

## 一气画完

- 按计划里“逐张计划”表的顺序，把还没画的卡一张接一张画完，用现有的出图命令。中间不停下来问用户，也不在两张卡之间等批准。
- 每一张都跟着选定的方向：选定的封面当字体和风格参考；打字字体的整套，字由代码按 `typed-styling.json` 设（issue 81）。
- 每一张卡的检查照常做，一项不省：AI 感、手、人物和身份、真实包装（用眼看）、Easel 自己写的字逐字对、场景和道具。没通过的卡，重出，不用问用户（这张卡还没批准，重出没有次数上限）。重出之后仍不合格的卡不藏起来，照实写进它的检查文件 `checks/card-<卡>.md` 的 `## 如实` 一节，原话，一行一条。
- 最后一张画完，再做整套的检查：套系并排检查、打字字体一致检查（打字的整套）、人物检查，照旧。

## 并排页

整套检查之后，先跑 `approvals.py check`（[photo-scene-approvals.md](photo-scene-approvals.md)），再建一张页给用户看：

`python3 skills/builtin/xhs-reference-visual/scripts/plan_page.py set --plan <set-plan.md> [--images-folder <卡图所在文件夹>] [--checks-folder <检查文件所在文件夹>] [-o <页面.html>]`

- 页面默认存在这篇帖子的照片场景文件夹里（`outputs/` 下），套系计划旁边，叫 `整套并排页.html`，图片用相对路径。卡图默认在计划旁的 `images/`，每张叫 `card-<卡>.png`（或 jpg、jpeg、webp），检查文件默认在计划旁的 `checks/`。
- 页面按计划里的卡的顺序并排放出每一张卡，封面在最前，每张标上卡名，旁边是计划里它那一行，原样照抄，读者的问题也在内。命令只加固定的标题和标签，不改字。
- 检查文件的 `## 如实` 里有内容的卡，页面上标“未通过检查”，并把那几行原样列在下面。
- 退出码 0 是成功，命令打印 `OK: <页面位置>`；退出码 2 是输入有问题，什么也不写：计划里的某张卡在磁盘上没有图（或有两张）时，报错点出这张卡的名字，不猜、不跳过。
- 把页面的位置交给用户，然后停下。

## 交付仍是一张卡一个文件

页面是给用户看的。交付的图仍然每张卡一个文件，放在 `images/`，不做联系表。团队 playbook 的原话（`<资料包目录>/playbook/PLAYBOOK.md`）：“逐张独立输出”。

## 用户回复之后

- 用户批准整套页：把批准和日期记入批准记录 `approvals.json`（页上每一张卡一条，`kind` 是 `set-page`，见 [photo-scene-approvals.md](photo-scene-approvals.md)），不再写进套系计划，页上每一张卡都算已批准，这就是 issue 91 说的“他并排看过整套后批准的那一套”。之后用户要改其中一张，按 issue 91 的已批准卡规则办。
- 用户批准之前提了改动：只重画被点名的卡，重建这张页，再给用户看一次。

## 不读包装上的字

这一步的任何一行都不读、不列、不报包装上印的字，页面上、检查里都一样。真实包装是不是原样，仍然用眼看。
