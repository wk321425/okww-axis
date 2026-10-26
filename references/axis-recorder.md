# 实机排查先读「跑轴记录」

ok-ww 插件「跑轴记录」（楽山机器上源码在 `F:\ok-ww\pr_work\axis_recorder_plugin`）把每一局自动战斗都存了下来。实机报问题时**先读它**，不够再要 DVR 录屏。
以前的做法是：录屏和日志对时，抽帧，一张张看 2K 截图（每张约 1800 token，一次排查常常十几二十张）。现在按键、读数、在场全是文字，脚本筛到出事那几秒，只看 1~3 张 960x540 画面（约 700 token）或者读屏原图小块（几十到几百 token），也不用对时。

## 存了什么（`working\logs\axis_runs\`）

| 文件 | 内容 |
|---|---|
| `<YYYYMMDD_HHMMSS>_<队伍>.jsonl` | 一局一个：表头（队伍、目录+版本、分辨率、键位、插件版本、开打墙钟 `wall`）+ 事件。时间 `t` = 开打后的秒数 |
| `<同名>.media` + `.media.idx` | 整局画面：每秒 4 帧，960x540 JPEG；外加读屏原图小块（读数翻转/变了才存，原分辨率 PNG）。只留最近 5 局 |
| `export\<时间>_<队伍>\` | 用户按 F8 导出的那几秒原图：原分辨率 PNG，文件名 = 这局第几秒；`info.json` 记着是哪一局。留 20 次 |
| `feedback\<这局>_反馈.zip` | 「打包反馈」打的包，别人发来的也是这种 |

事件种类（`e` 字段）：

- `in`：按键。所有交互后端和 SendInput 发出去的键鼠都记，带发起的代码行 `src`（再上一层是 `src2`）。
- `read`：队伍代码发起的读屏，包括 `find_one` / `find_feature` / 颜色占比 / `get_cd` / `get_current_con`。连读、读数差不多的合成一段，带 `n` 次数、`lo~hi`、`last`、`t2`、框 `box`、认没认到 `ok`。
- `field`：`in_team()` 认到的在场角色。HUD 不在单独算一段；只认到一个号码的帧（`cnt` < 人数）不可信。
- `perf`：`perform()` 开始和结束。
- `log`：这局里的 ok 日志。
- `mark`：队伍代码 `axis_mark()` 打的点。

不记的：框架例行检查（判脱战、找怪、认 HUD）；队伍代码自己切 `task.frame[...]` 算的读数（除非打了 `axis_mark`）。

## 脚本：`scripts/run_report.py`

**别把 JSONL 整个读进上下文**，一局有几千行，用脚本看。

```bash
PY=F:/ok-ww/data/apps/ok-ww/python/python.exe
RR=~/.claude/skills/okww-axis/scripts/run_report.py
$PY $RR list                                  # 最近几局: 序号、队伍+版本、时长、结束原因、[画面/F8×N]
$PY $RR summary latest                        # 摘要 + 分圈逐段表(慢的段标 * 并列出起止秒) + 警告/报错日志 + 画面空档
$PY $RR around 013017 87.5 --span 1.5         # 这一刻前后的事件, 每行带在场角色和代码位置; 点按合成「点按 A ×13」
$PY $RR around latest 120 --kinds read,log --grep con   # 只看读屏和日志里带 con 的
$PY $RR frame 013017 79.3 --out <scratchpad>  # 那一帧(叠上前后 0.15s 读过的框) + 那几处读屏的原图小块
$PY $RR sheet 013017 79 83 --out <scratchpad> # 一段画面拼成一张 4 列缩略图(16 帧一张图, 看一串动作最省)
$PY $RR exports 015212                        # 这局 F8 导出的原图文件夹 + judge_test 命令
$PY $RR summary <别人发来的反馈包.zip>          # 先解压到临时目录; 包里的 反馈说明.txt / ok-script_这一局.log 也读一下
```

`<局>` 可以写 `latest`、`list` 里的序号、文件名里的一段（如 `013017`）、jsonl 路径或反馈包 zip。图片写到 `--out`（给 scratchpad），不给就写到 `%TEMP%\okww_run_report`。
解析直接借插件自己的 `runs.py` / `media.py`，结果和复盘页一致。插件源码按 `OKWW_AXIS_RECORDER` > `<安装根>\pr_work\axis_recorder_plugin\axis_recorder` > `working\ok_import\axis_recorder` 的顺序找（楽山机器上 `ok_import` 下的目录普通进程读不了，用的是 pr_work 那份）。

## 排查顺序

1. **问清哪一局、大概哪里**：第几圈、什么现象、按没按 F8。用户说「刚才那局」就用 `latest`。
2. `summary`：先看分圈表里慢的段、警告日志、结束原因。用户说的「第 2 圈慢」直接对到「慢: L2 Suoming ② 79.04~97.50s」这一行。
3. `around <那段开头或出事时刻>`：先 `--kinds log,field,in` 看流程走到哪一步、按了什么，再 `--kinds read` 看判据读数（读数一直没过阈值？一直没认到？撞了 cap？）。
   代码位置 `@Hsin.py:3608 so_ensure_intro ← Hsin.py:3583 seg_lq_so_b` 直接对到要改的那行。
4. 文字说不清时再看图：先 `frame` 一张（看框框在哪、HUD 在不在、人在不在空中），一串动作用 `sheet`。看完就下结论，别一帧帧往后翻。
5. 判据读错（「明明满了没放」「没亮就按了」），而用户按了 F8：用 `exports` 拿到原图，跑 `judge_test.py at <队伍> --image <png…> -e "<判据>"`。
   F8 原图是 WGC 直接拿的画面，**比 DVR 录屏准**（没有 h264 压缩，颜色没漂），judge_test 会自己再缩到 1080 跑一遍。
6. 还是不够才要 DVR 录屏，见下面。

## 这些情况还得要录屏

- **定新判据或新框**：轴还没读过的地方没有原图小块，960x540 的画面也不能拿来定阈值。用户出事后 4 秒内按了 F8 就用 F8 原图，没按到才要录屏。
- **轴没取帧的空档**：定时连点、等演出时轴不截图，插件那几秒就没画面（`summary` 里的「画面空档」，实机一局 18 段，每段 0.6~2.7 秒）。插件不能自己补截图：WGC 取帧锁不等待，插件占着时轴取帧拿到 None，框架会睡最多 1 秒。
- **要精确到帧的时序**：动画能不能取消、差 0.1 秒那种。插件每秒 4 帧，录屏 60 帧。
- **做解说视频**，或者对方没装这个插件。

## 跟用户说的实机测试习惯

发现不对就马上按 F8（导出按下前 4 秒的原图），然后关掉自动战斗，再说第几圈、什么现象。录屏先不用给，记录不够再要。别人用分享的轴出问题，让对方在「跑轴复盘」页点「打包反馈」，把 zip 发来。
