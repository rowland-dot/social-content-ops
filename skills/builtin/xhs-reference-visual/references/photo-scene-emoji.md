# 字里的表情（easel-setup-gaps issue 100）

本页的编号是 easel-setup-gaps 的 issue 100，不是 SKILL.md 里“交付前检查的顺序”用的那个 issue 100（它来自另一个 issue 文件夹）。

## 管什么

任何一张照片场景帖的卡，只要它的字（标题或正文，打字的或手绘的）里带一个或几个表情，就按本页办，不分品牌、商品和账号。没有表情的卡不受影响。本页不点任何品牌、商品或帖子：它说的是 Easel 自己的出图路线怎么画表情，对每个账号都一样；某个账号用不用表情，由那个账号的创作指南说。

## 负责人的话（原样）

2026-10-28，通过提问工具：

- 表情怎么上卡：“Let the image model draw them”（没选的另一项是“Fix the script, code sets them”）。
- 他自己的话：“Book a session for emoji, but what is the emoji front PC font? I only want the apple ios emoji looks”。
- 被告知这台电脑上的表情字体是 WSL 里的 Noto Color Emoji（谷歌的样子）和 Windows 里的 Segoe UI Emoji（微软的样子），苹果自己的字体不在机器上、许可只给苹果设备：“Image model draws iOS-style (Recommended)”。

量过的事实：`fc-list` 在 WSL 里只列出 Noto Color Emoji；`C:\Windows\Fonts` 里只有 `seguiemj.ttf`。这两个字体都不用。

## 怎么画

- 确认过的字表里的每一个表情，由出图模型（Codex）画成 Apple iOS 表情的样子，画在这张卡的版面计划给的位置，任何一张字里带表情的卡（封面和每一张卡）都这样。
- 每张卡的提示词对每个表情写明三件事：是哪个表情、在版面计划的哪个位置、画成 Apple iOS 样式。
- 打字字体的整套：blocks 文件里不放表情，代码只设没有表情的字；提示词要求出图模型在计划的位置画每个表情。
- 手绘字的整套：提示词要求每个表情以 Apple iOS 样式画在字里。

## 图标清单

字里的表情列进整套的图标清单（现成的表，列不变：图标 | 意思 | 出现的卡），每一行写明这个表情由出图模型画成 Apple iOS 样式。字里带表情的套，不能写“这套不用图标”。

## 检查

三级（字和颜色）的交付检查：确认过的字表里的每个表情都在卡上计划的位置，而且看上去是 Apple iOS 表情。出现下面任何一条，这张卡不合格：表情缺了；画成谷歌的样子；画成微软的样子；画成线条图标；画成手绘的涂鸦；画成缺字方框。没批准的卡照干净重出办，已批准的卡照“已批准卡的修改”办，或如实报告。用眼睛判断，不读、不列、不报包装上印的字。

## 不动的东西

不添加、不安装、不改任何表情字体；苹果自己的表情字体从不下载、不安装；设字的脚本 `text_on_image.py` 不为表情改。
