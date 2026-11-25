# 参考队伍：心雷穗（Hsin__Rover__Suisui）v1.1.0 导出版

skill 自带的一份完整队伍代码，作为**持宏者骨架**、**干跑模板**和（原版 OKWW 上的）**自包含引擎**。别人的机器上不一定有作者那 20 多个队伍目录，所以模板放在这里，不依赖本机文件。

这是 coco-ww 用 `export_custom_team` 导出的那份（2026-11-26）：coco-ww 里的 `Hsin.py` 开头是一行 `from src.combat.MacroKit import MacroKit, MacroBroken, send_input_left`，
导出时框架把它换成了 MacroKit 的源码（`# >>>>>>>> coco-ww 分享时把 src/combat/MacroKit.py 内联在这里` 到 `# <<<<<<<< 内联的 src/combat/MacroKit.py 到此为止`）。
所以它**原版 OKWW 和 coco-ww 都能直接跑**：在 coco-ww 里经「导入」放进去时，内联段跟本地 MacroKit 一字不差就会收回成那行 import。

| 文件 | 用途 |
|---|---|
| `Hsin.py` | 持宏者（心）：模块顶部的 F 键监视 / 开关监视（`try: from src.combat.AxisWatch import ...` + 自带兜底），内联的 MacroKit 原语（tap / quick_switch / handoff / switch_retry / fire_r / ensure_r / wait_hud_* / read_con / press_key_until_cd …），`class Hsin(MacroKit, NativeHsin)` 里的常量、状态、判据和三个人的段落 |
| `Rover.py` / `Suisui.py` | 不驱动轴的两个人：只转发到持宏者的 `drive()` |
| `team.json` | 导出分享时用的清单（name / description / author / version / team） |
| `dryrun.py.tool` | 干跑工具：假 task + 假游戏，真跑启动轴和几圈循环；`DRY_FAIL` 逐条测保底分支。`FakeExecutor` 带了 `exit_event` 等字段（coco-ww 里 `macro_wait` 走 `BaseChar.precise_wait` 要用） |

## 怎么用

- **当模板（coco-ww）**：新队伍继承 MacroKit，照 `Hsin.py` 里 `class Hsin` 那部分写骨架（常量块、`__init__` / `reset_state`、`drive` / `opener_blocked_by`、段落）；内联段不用看，那就是 coco-ww 的 `src/combat/MacroKit.py`。从 `dryrun.py.tool` 抄假 task / 假游戏的骨架，改成新队伍的资源模型。
- **当模板（原版 OKWW，没有 MacroKit）**：整份 `Hsin.py` 当底子，内联段原样留着。
- **跑一遍看看**：把这 5 个文件复制进 `<working>/configs/custom_teams/Hsin__Rover__Suisui/`
  （coco-ww 的 working 就是安装目录本身；原版是 `<安装目录>/data/apps/ok-ww/working`。**把文件复制进文件夹**，别整个文件夹搬），然后在那个目录里用自带的 python 跑：
  ```
  <自带 python> dryrun.py.tool
  ```
  它会从自己所在的位置往上找 working 目录；放在别处跑就设环境变量 `OKWW_WORKING=<working>`。
  干跑会真的按墙钟跑（两圈约两分半），最后打印 `OK` / `FAILED`。
- 复制进 `custom_teams` 之后，这三个 .py 就是心雷穗那队的自定义代码，游戏里凑齐心 + 雷主 + 穗穗就会生效（心要用电磁模态）。**本机已经有这队代码的别覆盖**；不想启用就别复制 .py，只看代码。

`dryrun.py.tool` 不在分享用的 zip 里：框架导入时要求 zip 里只有 `team.json` 和三个 `.py`，多一个文件就拒收。所以导入队伍的人手里本来就没有它，要从这里拿。

验证过（2026-11-26）：coco-ww 里干跑 2 圈 `OK`；原版 OKWW 的 python 能加载 `Hsin.py`，`MacroKit` 和 `start_f_watch` 都来自文件自己。
