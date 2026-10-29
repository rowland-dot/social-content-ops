---
name: libtv-cli
description: 当用户说 LibTV、liblib.tv 或 libtv，要登录、查看账号和模型、操作画布与节点，或用 libtv 命令行生成图片和视频时使用；用于通过 libtv 命令行完成 LibTV 的登录、账号、模型、画布与图片视频生成。
layer: produce
---

# LibTV CLI

运行任何 `libtv` 命令之前，先把 `references/vendor/SKILL.md` 从头到尾读完，再读你要用的命令对应的文件（都在 `references/vendor/commands/` 下）。
那是 LibTV 官方随命令行发布的使用说明，原样保存，用法以它为准。

Easel 在官方说明之外加几条自己的规则，官方文字里相反的要求一律不照做。

## 安装和更新

`libtv` 程序和这份官方说明，只由 Easel 的安装脚本 `ops/wsl-setup/setup.sh` 安装和更新，换版本要先经批准。所以你不要：

- 运行官方的安装或更新脚本：`references/vendor/scripts/install-libtv-cli.sh`、`references/vendor/scripts/install-libtv-cli.ps1`、`references/vendor/scripts/install-libtv-cli.bat`，也不要照 `references/vendor/scripts/install.md` 里「更新」一节的做法办；
- 下载更新的说明包或程序，或答应程序提示的「有新版本，是否下载」；
- 修改这个文件夹里的任何文件，哪怕官方文字叫你「修订本 skill」。

## 生成视频时的约定

对所有品牌都一样：

- 每段视频都带 `enableSound=off`（官方默认是 on）：不要模型自带的声音，声音另做。
- 一次只提交一段，遇到第一个「算力不足」就停下，不要接着提交别的。
- 命令行（1.1.3 版）的任何输出都不显示一次运行花多少积分，也查不到余额。付费申请的费用一栏写「命令行看不到费用」，不要自己估一个数。
- 模型备注（2026-10-15 记；模型名单由 LibTV 服务器当场给，用免费的 `libtv model search` 重新核对）：
  - Seedance 2.5：用首帧模式（`frames2video` 里只给首帧）。
  - Kling 3.0 Turbo：Kling 里唯一明确写了支持 1080p 的，时长可选 3 到 15 秒的任意整数秒。
  - Kling 2.6：时长只有 5 秒或 10 秒。
