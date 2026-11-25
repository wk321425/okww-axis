# okww-axis

一份 AI 编程助手通用的 skill（`SKILL.md` + 参考文档 + 脚本）：**OKWW（[ok-wuthering-waves](https://github.com/ok-oldking/ok-wuthering-waves)，鸣潮自动战斗框架）自定义队伍战斗轴的制作与调试手册**。

内容是 2026-08 到 2026-11 跟 AI 一起做了 20 多条轴（心雷穗、日月守、爱琳莫、心锁守……）之后沉淀下来的方法：怎么从攻略视频/宏截图扒轴、持宏引擎怎么写、每一格用判据还是计时、保底加到哪为止、实机报「慢了/没放出来/切早了」怎么查、定稿怎么导出分享。每条规则后面都有一次实机翻车。

> 这是社区经验整理，不是 ok-ww 官方项目。

## 装上

哪个 AI 都能用，不绑定某一家。文件夹名就叫 `okww-axis`，`SKILL.md` 要在 `okww-axis\` 下面一层（别多套一层）：

```bash
git clone https://github.com/wk321425/okww-axis.git <放 skill 的目录>/okww-axis
```

- **支持 skill（`SKILL.md` 格式）的工具**：放进它的 skills 目录，按开头的 description 自动触发。
- **不支持 skill 的工具**：放在哪都行，开工前让它先读 `okww-axis/SKILL.md`（或者写进项目的说明文件 / 系统提示："做 OKWW 的轴之前先读 <路径>/SKILL.md，按需再读 references/"）。
- 不用 git 的话点 **Code → Download ZIP**，解压后把文件夹改名成 `okww-axis`。

更新：在那个目录里 `git pull`，或者重新下 ZIP 覆盖。

文档里写的 `<skill>` 就是这个 `okww-axis` 文件夹。

## 用法

在 ok-ww / coco-ww 安装目录里打开你的 AI 编程助手，直接说要做什么就行（不会自动触发 skill 的工具，先让它读 `SKILL.md`），例如：

- 「按这个视频做个心雷穗的轴」
- 「循环轴第二圈守岸人切早了」
- 「可以了，确认分享」

## 里面有什么

| 路径 | 内容 |
|---|---|
| `SKILL.md` | 入口：环境速查、做一条轴的七个阶段（立项→学机制→扒轴→写代码→干跑→实机迭代→定稿）、16 条核心原则 |
| `references/engine.md` | 持宏引擎：继承 MacroKit、结构与原语（tap / 切人 / 大招 / 长按 / HUD 看门狗 / 开关重跑） |
| `references/judgment-and-fallback.md` | 判据 vs 计时、去抖、提前量、保底的分界线 |
| `references/framework-pitfalls.md` | ok-ww 框架 API 的坑 |
| `references/video-extraction.md` | 扒攻略视频、读宏截图、对录屏 |
| `references/dryrun.md` / `judge-test.md` | 干跑工具、离线在录屏/截图上跑判据 |
| `references/axis-recorder.md` / `troubleshooting.md` | 实机排查：先读跑轴记录，再按症状找根因 |
| `references/finalize.md` | 定稿、导出、分享、备份清单 |
| `references/teams-index.md` | 哪个角色的判据去哪条轴抄 |
| `scripts/` | 帧表查询、视频工具、离线判据测试、跑轴记录读取、队伍代码静态检查、定稿导出 |
| `assets/reference_team/Hsin__Rover__Suisui/` | 参考队伍心雷穗 v1.1.0 导出版（MacroKit 已内联，原版 OKWW 也能跑）：持宏者骨架 + 干跑模板（见里面的 README） |

## 环境

- **ok-ww / coco-ww**：脚本都用框架自带的 python 跑（原版 `<安装目录>/data/apps/ok-ww/python/python.exe`；[coco-ww](https://github.com/wk321425/coco-ww) `<安装目录>/python/python.exe -X utf8`），会自己找 working 目录（有 `src/char/CustomCharLoader.py` 的那层）：环境变量 `OKWW_WORKING` > 当前目录往上找 > `<当前目录>/data/apps/ok-ww/working`。coco-ww 是平铺结构，安装目录本身就是 working。
- 文档里的 `F:\coco-ww`、`F:\ok-ww`、`E:\轴视频` 是作者机器上的路径，换成你自己的读；`team_backup`、其他队伍目录、每条轴的历史笔记你那边没有，AI 会先问。
- 可选：
  - ffmpeg / PySceneDetect —— `video_tool.py` 用来精确跳帧、找剪辑点，`OKWW_FFMPEG` / `OKWW_PYLIB` 指定位置，没有就退回 OpenCV。
  - 官方动作帧表 xlsx —— 不随附，`frame_data.py --xlsx <路径>` 指定。
  - [「跑轴记录」插件](https://github.com/wk321425/ok-ww-axis-recorder) —— `run_report.py` 读它的记录和反馈包，`OKWW_AXIS_RECORDER`（插件源码目录）/ `OKWW_AXIS_RUNS`（记录目录）指定位置。coco-ww 已经内置（`src/recorder`），不用装也不用设。
  - `export_team.py` 的备份位置用 `OKWW_BACKUP_ROOT` 改。

## 相关项目

- [coco-ww](https://github.com/wk321425/coco-ww)：基于 ok-ww 裁剪自维护的版本，只留自动战斗和刷 4C 声骸，内置跑轴记录、F 开战和持宏公共原语 `src/combat/MacroKit.py`（导出队伍时自动内联，原版 OKWW 照样能用）。
- [ok-ww-axis-recorder](https://github.com/wk321425/ok-ww-axis-recorder)：ok-ww 插件「跑轴记录」，每局记下按键/读屏/在场/画面，实机排查先看它。
- [ok-ww-f-start-combat](https://github.com/wk321425/ok-ww-f-start-combat)：ok-ww 插件「F 开始战斗」，副本里按 F 立即开打。

## 协议

[AGPL-3.0](LICENSE)，跟 ok-wuthering-waves 上游一致。
