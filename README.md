# okww-axis

给 [Claude Code](https://claude.com/claude-code) 用的 skill：**OKWW（[ok-wuthering-waves](https://github.com/ok-oldking/ok-wuthering-waves)，鸣潮自动战斗框架）自定义队伍战斗轴的制作与调试手册**。

内容是 2026-08 到 2026-10 用 Claude 做了 20 多条轴（心雷穗、日月守、爱琳莫、心锁守……）之后沉淀下来的方法：怎么从攻略视频/宏截图扒轴、持宏引擎怎么写、每一格用判据还是计时、保底加到哪为止、实机报「慢了/没放出来/切早了」怎么查、定稿怎么导出分享。每条规则后面都有一次实机翻车。

> 这是社区经验整理，不是 ok-ww 官方项目。

## 装上

skill 放在 Claude Code 的用户级 skills 目录，文件夹名就叫 `okww-axis`：

```bash
git clone https://github.com/wk321425/okww-axis.git ~/.claude/skills/okww-axis
```

Windows 上 `~` 是 `C:\Users\<用户名>`。不用 git 的话点 **Code → Download ZIP**，解压后把文件夹改名成 `okww-axis` 放进 `C:\Users\<用户名>\.claude\skills\`（`SKILL.md` 要在 `okww-axis\` 下面一层，别多套一层）。

更新：在那个目录里 `git pull`，或者重新下 ZIP 覆盖。

## 用法

在 ok-ww 安装目录里打开 Claude Code，直接说要做什么就行，skill 会自己触发，例如：

- 「按这个视频做个心雷穗的轴」
- 「循环轴第二圈守岸人切早了」
- 「可以了，确认分享」

## 里面有什么

| 路径 | 内容 |
|---|---|
| `SKILL.md` | 入口：环境速查、做一条轴的七个阶段（立项→学机制→扒轴→写代码→干跑→实机迭代→定稿）、14 条核心原则 |
| `references/engine.md` | 持宏引擎结构与原语（tap / 切人 / 大招 / 长按 / HUD 看门狗 / 开关重跑） |
| `references/judgment-and-fallback.md` | 判据 vs 计时、去抖、提前量、保底的分界线 |
| `references/framework-pitfalls.md` | ok-ww 框架 API 的坑 |
| `references/video-extraction.md` | 扒攻略视频、读宏截图、对录屏 |
| `references/dryrun.md` / `judge-test.md` | 干跑工具、离线在录屏/截图上跑判据 |
| `references/axis-recorder.md` / `troubleshooting.md` | 实机排查：先读跑轴记录，再按症状找根因 |
| `references/finalize.md` | 定稿、导出、分享、备份清单 |
| `references/teams-index.md` | 哪个角色的判据去哪条轴抄 |
| `scripts/` | 帧表查询、视频工具、离线判据测试、跑轴记录读取、队伍代码静态检查、定稿导出 |
| `assets/reference_team/Hsin__Rover__Suisui/` | 参考队伍心雷穗 v1.0.0：引擎模板 + 干跑模板（见里面的 README） |

## 环境

- **ok-ww**：脚本都用 ok-ww 自带的 python 跑（`<安装目录>/data/apps/ok-ww/python/python.exe`），会自己找 working 目录：环境变量 `OKWW_WORKING` > 当前目录往上找 > `<当前目录>/data/apps/ok-ww/working`。
- 文档里的 `F:\ok-ww`、`E:\轴视频` 是作者机器上的路径，换成你自己的读；`team_backup`、其他队伍目录、每条轴的 memory 你那边没有，Claude 会先问。
- 可选：
  - ffmpeg / PySceneDetect —— `video_tool.py` 用来精确跳帧、找剪辑点，`OKWW_FFMPEG` / `OKWW_PYLIB` 指定位置，没有就退回 OpenCV。
  - 官方动作帧表 xlsx —— 不随附，`frame_data.py --xlsx <路径>` 指定。
  - [「跑轴记录」插件](https://github.com/wk321425/ok-ww-axis-recorder) —— `run_report.py` 读它的记录和反馈包，`OKWW_AXIS_RECORDER`（插件源码目录）/ `OKWW_AXIS_RUNS`（记录目录）指定位置。
  - `export_team.py` 的备份位置用 `OKWW_BACKUP_ROOT` 改。

## 相关项目

- [ok-ww-axis-recorder](https://github.com/wk321425/ok-ww-axis-recorder)：ok-ww 插件「跑轴记录」，每局记下按键/读屏/在场/画面，实机排查先看它。
- [ok-ww-f-start-combat](https://github.com/wk321425/ok-ww-f-start-combat)：ok-ww 插件「F 开始战斗」，副本里按 F 立即开打。

## 协议

[AGPL-3.0](LICENSE)，跟 ok-wuthering-waves 上游一致。
