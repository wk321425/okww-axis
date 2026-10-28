# 干跑：假 task + 假游戏，真跑一遍

干跑验证的是**调用链、判据分支和逐格墙钟**，不是打得对不对：
- 有没有 AttributeError / 参数对不上 / 变量不在作用域（保底分支尤其）
- 每一格是等到了判据，还是撞上限出来的
- 逐格墙钟跟视频/宏表对得上吗（宏表型：`N keys in X.XXs (table says Y.YYs)`，差值就是保底总开销）
- 跨角色的时序约束（比如"穗穗第一次翾舞时在场的是不是雷主"）

模板就在 skill 里：`assets/reference_team/Hsin__Rover__Suisui/dryrun.py.tool`（心雷穗那份，配套的三个 .py 也在同一个目录，见那里的 README）。
新队伍复制过来改假游戏的资源模型。**别去 `configs/custom_teams/` 里找**：分享出去的队伍 zip 只能装 team.json + 3 个 .py（框架导入时多一个文件就拒收），导入队伍的人手里没有干跑工具。
文件名用 `.py.tool`：留在队伍目录里，框架不把它当角色代码，导出 zip 也不带。
**路径别写死**：模板开头的 `find_working()` 从文件位置往上找 working 目录（或读环境变量 `OKWW_WORKING`），抄的时候保留这一段。

## 结构

```
文档串: 验证什么 / 演出时长按视频 / 用法 / DRY_* 环境变量(每个 DRY_FAIL 名字一行说明)
stdout/stderr 改 UTF-8; WORKING = find_working(); sys.path.insert(0, WORKING); os.chdir(WORKING)
                     (框架按相对路径 configs/custom_teams 找队伍代码, 所以要 chdir)
load_team_char_class 加载队伍代码, assert 加载到的是自定义类(没加载到就是目录/类名不对)
rec(what)            记 (时刻, 事件) 到 LOG
FakeExecutor         check_enabled() 空实现; trigger_tasks / onetime_tasks 空
Game                 假游戏状态机:
  on_field / pending(切人在途) / con{} / e_cd{} / r_cd{} / 各角色资源(回路、能量、形态)
  hud_hidden[] + flickers[](演出中途 HUD 闪一两帧) + freezes[](时停) -> hud_visible(now)
  hide(dur, flick, freeze)  演出: 藏 HUD + 锁输入 + 不许切人
  lock_until / no_switch_until  入场锁、换人 CD(~1s)
  tick()               推进时间: 切人生效、资源随时间变化
  press(key, down_time) 按资源规则决定这一下出什么(被锁就丢, 不排队)
  tap()                普攻: 攒资源、推连段
  fail_once(name)      DRY_FAIL 里有这个名字且本圈没用过 -> True(每圈各触发一次)
FakeTask             send_key / send_key_down/up / mouse_down/up / jump / next_frame(调 tick) / in_team /
                     get_current_con / get_cd(没 CD 返回负数, 跟框架一样) / find_one / available / has_cd /
                     box_of_screen(_scaled) / is_pick_f / 键位 getter / find_mouse_forte ...
Logger               info/warning/debug/error 都 rec
build(cls, index, name, char_type)
                     object.__new__ 建角色(不跑 __init__), 手动挂框架字段 + 持宏者自己的字段
                     把 add_freeze_duration / time_elapsed_accounting_for_freeze / switch_out 换成简化版
读屏判据替身         xn.xn_statue_count = lambda: ...  用 Game 状态算出"屏幕上会读到什么"
主程序               drive(entry) 跑启动轴, 再循环 DRY_LOOPS 圈; 捕获异常打 traceback; 打印 LOG
```

## 要点

- **换人要在 `tick()` 里推进**（`next_frame()` 调它）：宏表型的宏里不读屏，只在 `in_team()` 里推的话整条宏跑完 on_field 都不动。
- `send_key` / `click` 要模拟按住时长，否则时序对不上。
- **按键被锁就丢，不排队**（跟游戏一样）。假游戏模拟不了预输入缓冲的精度（试过，触发时刻差几十毫秒就把后面的切人推歪），宏里靠预输入的那格干跑出不来是假游戏的事 —— 在文档串里写明。
- 演出时长、入场锁、资源规则从帧表和视频量（文档串里列出来：`雷主R 3.8 / 穗穗R 4.3 / 转相 4.3 ...`）。
- `get_cd` 没 CD 时返回负数、协奏 0.99 哨兵、切人后几帧技能栏还是上一个人 —— 框架的这些怪脾气在假 task 里也要有，不然干跑验不到对应的防线。
- 技能冷却按**游戏时间**走，大招/变身演出（HUD 消失那几秒）里是停的。假游戏的冷却要是按墙钟算，「演出多的那段之后 E 好没好」就跟实机对不上（卡夏釉：实机启动轴后第一圈 Y1 的 E 是好的，干跑里却是没好，一圈三次下落的分支干跑根本走不到）。
- **每条保底分支一个 `DRY_FAIL` 名字**，至少跑一遍：切人被拒、技能被吞、判据读不到、资源攒得慢、演出后 HUD 不回来（关卡结束）……
  `DRY_FAIL=a,b,c` 组合跑，再全开跑一遍看最坏情况一圈多长。
- **"被怪打断"按时间窗建模**，不是吞一下：这一圈这个人第一次按某键起 N 秒内的这个键全丢（嘉露莫 `swallowed(knob, key, who, dur)`），N 取得比首发上限长，才逼得出补按那一轮。
- **假游戏的"图标亮不亮"要跟着失败旋钮走**：旋钮说"没能量"，`available('liberation')` 就得返回 False。否则"图标还亮才补"的保底在干跑里每次都白补两轮（嘉露莫 10-17 干跑先抓到的是假游戏的错，不是代码的）。
- **新分支跑 `OK` 不算测过，要在 timeline 里看到它自己的日志标记**：假游戏的锁比实机严（日月守 10-18 尤诺 Q 在告终动作里按不出，实机 0.12s 就出了），
  连按 Q 就把那 1.6s 吃掉了，"跳的时候 R 亮了就放"那条路一次都没走、照样 OK。把模型对齐实机日志后，同一处还抓出旧版"补完告终马上跳两下全被丢"的老 bug。
  没走到就调旋钮的时机（让资源在那个窗口里到账），直到标记出现。
- **动作什么时候起手按实机录屏建模**，别按"派生帧"一刀切：日月守鸣铁要等后撤收招(46F)才起手、旋切补施放排到鸣铁派生(41F)才出，
  模型按 26F 就起手时，固定按住 0.80 在干跑里永远够、实机却松在起手之前。
- 其他开关：`DRY_LOOPS`（圈数）、`DRY_FULL`（变奏入场资源直接满，模拟高链数）、`DRY_BREAK`（处决可用）。
- 输出按时刻列事件 + 持宏者自己打的 timeline，最后 `OK` / `FAILED`。拿它和视频逐格对表。
- 干跑只能证明"代码按设想跑"，回复用户时把"只干跑过、未实机"的改动单独列出来。

## 运行

```bash
cd <ok-ww 安装目录>/data/apps/ok-ww/working/configs/custom_teams/<队伍>
DRY_LOOPS=2 DRY_FAIL=sw,r1 <ok-ww 安装目录>/data/apps/ok-ww/python/python.exe dryrun.py.tool > dry.txt
```
（楽山机器上安装目录是 `F:/ok-ww`。）按墙钟真跑，三圈两三分钟，用后台跑。输出写文件再 Read（中文多、行多）。
