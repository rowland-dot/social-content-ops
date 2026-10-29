# 阶段 2：天猫竞品阅读

来源：规格 “Stage 2 — Tmall competitor read”，以及负责人 2026-10-28 对竞品研究的选择（“Your own account”）。本页不加规格里没有的规则。

## 规格怎么说

- 目的：看领先商品怎么搭页面，让我们的页面照有效的结构来。对手的销量、价格定位、店铺策略和逛逛内容不在范围内。
- 哪些商品：天猫全站里和这件商品同品类、销量最高的 8 到 10 款商品（国内店和跨境店都算），先用中文搜索，按搜索结果上的月付款人数（`X人付款`）排序。排序只用来选出这一组，人数不写进报告。
- 谁来抓：Claude 通过 Easel 自己浏览器里保存的天猫登录抓取。登录用负责人自己的淘宝账号，用手机淘宝扫一次，过期了再扫。遇到验证码或登录墙就停下来等负责人，已抓的保留。访问有间隔、每天有上限。
- 先试：完整抓取之前先抓 2 到 3 款给负责人看。试抓要证明三件事：保存的登录能进天猫商品页；验证码或风控多久出现一次；完整详情页能抓成图片。
- 每款商品要读的：每张主图及它的分工；详情页的屏序；主打卖点；每一屏怎么证明它的观点。另外把团队 2026-10-23 的修订稿（知识库目录里标 `REVIEW FIRST`）当草稿输入读，不当设计。
- 输出：一份简短的规律笔记（领先者第一张图说什么、用什么证据、页面怎么排）。笔记给团队，让他们补充抓不到的部分。
- 存放：抓到的图片和笔记通过知识库的工具存进客户知识库，不进本仓库。只用来学结构和证明方式，对方的文案绝不重用。

## 案例优先于平台标准（负责人，2026-10-29）

读竞品之前先读 `tmall-rules.md`（平台公布的标准），但那份阅读只是后备。规则（issue 09，负责人 2026-10-29）：那份阅读只是后备（fallback only）；竞品案例证明什么好卖时，案例永远优先于阅读里的规则（case always wins；对手的数字不会说谎），包括案例用了和阅读矛盾的设计或用词。

所以读每款竞品时，要把它的主图尺寸、第一张图有没有字、用的词，和规则文件对一对，并在规律笔记里写下哪里不一样：案例与规则文件矛盾的地方，以案例为准，阶段 3 照案例来。不替负责人定的一点：案例里的用词若触到广告法的限制，是否也以案例为准，是负责人的问题（见简报的待定事项）。

## 命令

- 登录（会在负责人的屏幕上开一个窗口，停下来等他扫码）：`python skills/shared/scripts/tmall_login.py login --status-file outputs/_login/tmall.status.json`；查看：`python skills/shared/scripts/tmall_login.py status`。
- 抓取：`python skills/builtin/tmall-product-content/scripts/tmall_capture.py run --query <搜索词> --top 10 --out outputs/_scratch/tmall-capture/<date>`；试抓加 `--trial`。退出码 2 到 5 的含义见 SKILL.md 的错误表。
- 试抓页：`python skills/builtin/tmall-product-content/scripts/tmall_capture.py trial-sheet --out outputs/_scratch/tmall-capture/<date>`。
- 笔记检查：`python skills/builtin/tmall-product-content/scripts/tmall_note.py check <note> <item ids>`。
- 存入知识库：`python skills/builtin/tmall-product-content/scripts/tmall_capture.py deposit --out outputs/_scratch/tmall-capture/<date> --brand <brand> --cat 05 --note <note>`。很慢（每个文件都要重建一次地图），放后台跑；中断后重跑是安全的。
