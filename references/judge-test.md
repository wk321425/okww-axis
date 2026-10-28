# 离线判据测试：在录屏/截图上跑读屏判据

`scripts/judge_test.py`。跟干跑互补：干跑用假游戏测**调用链和时序**，这个用真框架 + 真画面测**判据本身读得对不对**。

## 它做了什么

- 跟上游 `tests/TestCon.py` 一样初始化框架（`OK(config)` → `AutoCombatTask` → `after_init`），截图换成一个内存里的 capture method，喂录屏帧/png。
- **认人走框架自己的 `load_chars`**，自定义队伍代码也是框架自己加载的（输出里每个槽位标「队伍代码」/「内置代码」，内置 = 没加载到队伍目录，先查这个）。
  开头几帧 HUD 不在（大招演出/切人中）认不出来就往后每秒试一帧，最多 60 秒；`--chars-at T` 指定，`--hold-chars` 按 team.json 硬建。
  认出来的三个人要跟目录名对上才算（心雷穗 147.5s 那帧把穗穗认成了渊武）；每次认之前清空 `task.chars`，不然框架的粘性认人会一直错下去。
- 键鼠是 `DoNothingInteraction`，判据里就算调了 `send_key`/`click` 也到不了游戏。
- **配置目录用临时拷贝**（`%TEMP%\okww_judge\configs_<pid>`，只拷顶层 json + 这一个队伍目录）：初始化会把首选设备改成 image，写进真的 `devices.json` 下次开 ok-ww 就连不上游戏。
- **日志不落盘**（`disable_file_log`）：框架日志路径写死 `logs/ok-script.log`，不关会混进实机日志。控制台只剩脚本自己的输出。
- 每个采样跑两遍：原分辨率 + `cv2.resize(INTER_AREA)` 到 1920x1080；最后列出两种分辨率读数不一样的采样。片源本来就是 1080 只跑一遍；不是 16:9 整帧（排查截图常是裁过的）会提醒读数不可信。

## 用法

```bash
PY=F:/ok-ww/data/apps/ok-ww/python/python.exe
J=~/.claude/skills/okww-axis/scripts/judge_test.py
V="E:/录屏/Wuthering Waves/心雷穗完美视频.mp4"
$PY $J list hsin__rover                                    # 候选判据(只带 self、读屏、不等待不按键的方法)
$PY $J at hsin__rover --video "$V" --t 100,140 -e "Hsin.forte3_full()" -e "Hsin.con_now()"
$PY $J scan hsin__rover --video "$V" --start 136 --end 146 --step 0.1 -e "Hsin.forte3_full()" -o scan.csv
$PY $J at hsin__rover --image a.png b.png -e "task.in_team()"
```

- 队伍名写目录名或能唯一匹配的一段（大小写不敏感）。
- **录屏画面不是 16:9 就先修**：游戏区被压扁、带黑边时框架认不到人，判据全空（2026-10-28 卡夏釉的 N 卡录屏是 2560x1296 加上下黑边）。先抽一帧看游戏区，再用 ffmpeg `-vf crop=2560:1296:0:72,scale=2560:1440,fps=30` 修成 16:9，之后再 `scan`。
- 表达式里的角色名是**实例**，不是类：判在场写 `cur is Ciaccona`，写 `isinstance(cur, Ciaccona)` 会报 TypeError。
- 表达式里有 `task`、角色类名（`Hsin`、`Rover`…）、`c1 c2 c3`（槽位）、`cur`（在场的）、`np`、`cv2`。表达式随便写：`Hsin.con_now() >= 0.99`、`task.get_cd('resonance')`、`task.find_one('suisui_e1', threshold=0.7)`。
- `scan` 只打印**值变了的时刻**（判据翻转点），全部数值进 csv。`在场=(Rover)` 带括号 = 这帧没看到队伍栏，沿用上一帧的在场角色（跟实机一样）。
- 速度：框架起来约 2 秒；`scan` 每个采样 × 每种分辨率约 0.14 秒（10 秒 / 0.1 步 / 两种分辨率 ≈ 28 秒）。

## 读数怎么看

- **有 F8 导出的原图优先用它**（`run_report.py exports <局>` 列出文件夹，`--image` 传 png）：那是 WGC 直接拿的画面，没有压缩色偏，读数就是实机那一刻的。
- 录屏是 h264 压过的，颜色和边缘跟实机截图（WGC 直接拿 RGB）有出入：**贴着阈值的读数差几个百分点、翻转时刻差 1~2 帧都正常**，离阈值远的才算数。
  录屏要用 ffmpeg 后端解码（bt709，跟游戏一致）；cv2 解出来的颜色偏 2~3。
- 原分辨率和 1080 读数不一致 = 自算框/阈值在某个分辨率下有问题的线索（2026-10-16 首测：心雷穗 140s 穗穗在场时 `con_now()` 2K 读 0.000、1080 读 0.319，2K 那帧框架报 `is_con_full found multiple rings 2`；`forte3_full()` 1080 比 2K 早翻 0.1s）。先看那一帧再下结论，别直接改阈值。
- 有状态的判据（比如雕像计数要先 `reset`、看门狗记时刻）离线照样会累积状态，按时间顺序 `scan` 才对得上实机。
- 带等待循环/sleep 的方法别调：`next_frame()` 永远拿到同一张图，循环会一直等到超时（耗时 >2 秒的表达式输出里会标出来）。

## 限制

- 读不了的队伍目录（`拒绝访问`）：2026-10-16 发现 Aemeath__Linnai__Mornye / Augusta__Iuno__ShoreKeeper / Camellya__Sanhua__Verina / Cartethyia__Chisa__Ciaccona / Hiyuki__Lucilla__Verina 五个目录普通进程连 ACL 都读不了（多半是管理员身份的 ok-ww 导入/建的）。脚本会报错退出；要么管理员终端跑，要么用户给目录加 Users 读权限。
- 只测"这一帧读出什么"，不测"读到之后代码怎么走"——那是干跑的事。
- 只能用当前代码：改了判据代码直接重跑就是新版（每次都重新拷一份队伍目录）。
