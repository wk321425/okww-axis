# 参考队伍：心雷穗（Hsin__Rover__Suisui）v1.0.0

skill 自带的一份完整队伍代码，作为**引擎模板**和**干跑模板**。别人的机器上不一定有作者那 20 多个队伍目录，所以模板放在这里，不依赖本机文件。

| 文件 | 用途 |
|---|---|
| `Hsin.py` | 持宏者（心）：模块顶部的 F 键监视 / 开关监视 / SendInput，类里的引擎原语（tap / quick_switch / handoff / switch_retry / fire_r / ensure_r / wait_hud_* / read_con / press_key_until_cd / HUD 看门狗 …）和三个人的段落 |
| `Rover.py` / `Suisui.py` | 不驱动轴的两个人：只转发到持宏者的 `drive()` |
| `team.json` | 导出分享时用的清单（name / description / author / version / team） |
| `dryrun.py.tool` | 干跑工具：假 task + 假游戏，真跑启动轴和几圈循环；`DRY_FAIL` 逐条测保底分支 |

## 怎么用

- **当模板**：新队伍按方法名从 `Hsin.py` 抽引擎原语，从 `dryrun.py.tool` 抄假 task / 假游戏的骨架，改成新队伍的资源模型。
- **跑一遍看看**：把这 5 个文件复制进 `<ok-ww 安装目录>/data/apps/ok-ww/working/configs/custom_teams/Hsin__Rover__Suisui/`
  （**把文件复制进文件夹**，别整个文件夹搬），然后在那个目录里用 ok-ww 自带的 python 跑：
  ```
  <ok-ww 安装目录>/data/apps/ok-ww/python/python.exe dryrun.py.tool
  ```
  它会从自己所在的位置往上找 working 目录；放在别处跑就设环境变量 `OKWW_WORKING=<...>/data/apps/ok-ww/working`。
  干跑会真的按墙钟跑（三圈两三分钟），最后打印 `OK` / `FAILED`。
- 复制进 `custom_teams` 之后，这三个 .py 就是心雷穗那队的自定义代码，游戏里凑齐心 + 雷主 + 穗穗就会生效（心要用电磁模态）。不想启用就别复制 .py，只看代码。

`dryrun.py.tool` 不在分享用的 zip 里：框架导入时要求 zip 里只有 `team.json` 和三个 `.py`，多一个文件就拒收。所以导入队伍的人手里本来就没有它，要从这里拿。
