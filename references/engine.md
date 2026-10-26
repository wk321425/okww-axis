# 持宏引擎：结构、原语、从哪抄

最新、最完整的一份是心雷穗 v1.0（2026-10-06）的 `Hsin.py`，**skill 里自带一份**：`assets/reference_team/Hsin__Rover__Suisui/`（连同两个转发文件、team.json、干跑工具），新队伍从它抽。
别的机器上不一定有下面提到的其他队伍目录，那些只在楽山的 ok-ww 里。
宏表回放型的参考是 `Chisa__Suisui__YangYangSp/YangYangSp.py`（秧千穗 v4.1）和 `Changli__Jinhsi__Verina/Changli.py`（龙凤维）。

## 目录

1. 两种轴型怎么选
2. 持宏者文件的骨架
3. 另外两个人的转发文件
4. 入口：drive / 启动轴重跑
5. 原语清单
6. 切人
7. 大招与演出
8. 长按与 SendInput
9. 日志：时间轴是排查的唯一依据
10. 引擎怎么搬到新队伍

---

## 1. 两种轴型怎么选

| | 分段判据型 | 宏表回放型 |
|---|---|---|
| 素材 | 教学视频（步骤条 + 键盘浮层 + 字幕） | 用户给的宏截图（按键/动作/延时 ms），或作者实机宏 |
| 结构 | `run_cycle()` 依次调 `seg_xxx(tag)`，每段里用原语 + 判据 | `OPENER_MACRO` / `LOOP_MACRO` 元组表 → `run_macro()` → `play_rows()` 逐格 `macro_key()` / `macro_switch()` |
| 时间 | 每一格由判据或"锚点+固定时长"决定 | 照表回放（hold/gap 毫秒），`MACRO_SPEED` 整体缩放 |
| 保底 | 每段自己写 | `SAFETY` 总开关 + 特殊动作词（见下） |
| 例子 | 心雷穗、心卜穗、心汐守、景月守、露丽系列 | 秧千穗、龙凤维、卡夏千（`play_macro` 按绝对时刻排程、宏里不读屏） |

常见是混合：宏只覆盖一部分（"启动宏 → 手动A → 手动B → 循环宏"），宏外的手动段照视频写成判据段。

宏表的一行是 `(动作, 按住ms, 之后间隔ms, 注释)`。秧千穗那份的动作词可以直接沿用：
`A` / `E` / `Q` / `R` / `SPACE`、`>CHI` 切人（结尾 `^` = 变奏入场，切之前先把协奏打满）、
`E#` 按到进 CD 为止（带"先见过亮才认暗"）、`E+` 一格里连发（盖住入场锁刚开那一帧）、
`R!` 按一下后用这一格的演出时长盯 HUD，没消失就补按、`F?` 有处决提示才按、`WIN` 只打标记不按键。
**判据成立后要把这一格剩下的时间走完**，提前走会把后面每一格都往前挪，节奏就不是宏表的节奏了。
**例外**：大招那一格的 gap 是作者拿秒表估的演出时长，`wait_hud_back` 等到 HUD 真回来更准，演出结束就往下走，别再补足 gap。

## 2. 持宏者文件的骨架

按这个顺序排，别人（和下一个会话的自己）才找得到东西：

```
模块顶部
  F 键监视: f_settings(task) / start_f_watch(task, logger)      —— 逐字照抄, 多份拷贝保持一致
  开关监视: start_enable_watch(task, logger)                     —— 逐字照抄
  SendInput 结构体 + send_input_left(up)                          —— 需要系统级长按时才要
  class MacroBroken(Exception)                                   —— 切人失败/HUD 长时间不在 -> 整圈放弃
class <持宏者>(Native<持宏者>):
  docstring: 轴的出处 / 轴的形状(启动轴、循环轴逐格) / 为什么这么打(nanoka) / 判据 / 改之前先读
  常量块(按组): 全局节奏 / 切人 / 大招·演出 / 防重入 / 保底 / 每个角色一组(前缀区分, 循环轴专用加 L_)
  __init__ / reset_state
  队伍判定: is_in_<队> / teammate(name) / opener_pending / opener_blocked_by
  引擎原语(macro_* / spam_key / tap / quick_switch / handoff / fire_r / ensure_r / wait_hud_* / read_con ...)
  每个角色: 判据函数 + seg_* 段落
  一圈: run_cycle / macro_enter / macro_exit / perform_opener / perform_loop
  框架接口: drive / do_perform / get_switch_priority / on_combat_end
```

常量旁边写**结论和理由**：

```python
SUI_E1_THRESHOLD = 0.80      # suisui_e1 = E 图标的醒春潮图案, 亮着 = 水云息满
SU_E1_MUST_CAP = 12.0        # 启动轴醒春潮必须开出来: 10-06 实机 10 局 4 局 2.5s 没亮(开局普攻打不中怪)
```

`__init__` 里改了内置也有的字段（`check_f_on_switch` / `ring_index` …）**会被打回内置值**：
框架换类时先建自定义实例，紧接着 `replacement.__dict__.update(旧内置实例.__dict__)`。
要保住就在 `reset_state()` 里重申（`check_team.py` 会报这一类）。
新加的字段不受影响；property 打不回（釉瑚 `is_healer` 就是靠覆盖 property 改成 False 的）。

## 3. 另外两个人的转发文件

他们不驱动轴，`do_perform` 被调到说明宏散了（切人失败/脱战重进），转给持宏者的 `drive()`。
自定义角色文件之间 **import 不到对方**，用 `task.chars` 里的实例按能力找：

```python
from src.char.BaseChar import SwitchPriority
from src.char.Rover import Rover as NativeRover


class Rover(NativeRover):
    @property
    def is_in_xls(self) -> bool:
        return sum(1 for c in self.task.chars if c and c.name in {'Hsin', 'Suisui'}) == 2

    def macro(self):
        """持宏者。它那份自定义没启用时返回 None, 走原版。"""
        for char in self.task.chars:
            if char is not None and char is not self and hasattr(char, 'drive') and hasattr(char, 'quick_switch'):
                return char
        return None

    def reset_state(self):
        super().reset_state()
        self.check_f_on_switch = False   # 写在 reset_state: 写在 __init__ 会被打回内置值

    def do_perform(self):
        if not self.is_in_xls:
            return super().do_perform()
        self.check_f_on_switch = False
        macro = self.macro()
        if macro is None:
            return super().do_perform()
        macro.drive(self)

    def get_switch_priority(self, current_char=None, has_intro=False, target_low_con=False):
        if self.is_in_xls:
            macro = self.macro()
            if macro is not None and macro.opener_pending():
                return SwitchPriority.NO      # 启动轴待跑时宏自己切人
        return super().get_switch_priority(current_char, has_intro, target_low_con)
```

治疗角色在本队里不当治疗时要关 `is_healer`（否则框架按 HEALER 的 buff_time 选人）。
一个角色在两条队里就是两份拷贝，**改了一份记得同步另一份**。

## 4. 入口：drive / 启动轴重跑

```python
def drive(self, entry):
    # HUD 不在就什么都不做: 关卡结束/结算/过场时框架还会接着调进来(F 开始战斗那边撑着不脱战)
    if not self.wait_hud_up(cap=self.DRIVE_HUD_CAP, tag='drive'):
        return None
    blocked = self.opener_blocked_by()
    if blocked is None:
        # 标记要在跑之前落: 中途抛异常(脱战/任务被停)也不能让启动轴重跑
        self.opener_armed = False
        self.last_opener = time.time()
        return self.perform_opener(entry)
    return self.perform_loop(entry)
```

`opener_blocked_by()` 的放行条件（返回 None = 该跑启动轴），**顺序就是这样**：
1. 不是本队 → 不跑；
2. `opener_armed` 为 False 时，只有 `task._ww_task_restarted_at > last_opener`（开关监视线程记的"刚重开过"）才重新武装；
   **更稳的写法（2026-10-11 爱琳莫）**：把 `restarted > last_opener → return None` 提到 armed 判断之前、不管 armed 真假都放行，直到启动轴真跑了改掉 `last_opener`。
   参考实现只在 armed=False 那次放行，第二次调用（选人时三个人的 `get_switch_priority` 都会调）armed 已是 True，会撞上第 4 条的 60 秒门槛——一轮打到一半去开关必中；
3. 物理 F 键 `task._f_last_press > last_opener` → 放行（可选等界面上配置的秒数）；
4. 上次启动轴不到 `OPENER_MIN_GAP`(60s) → 不跑（防战斗判定抖动重读队伍时误判成新一局）；
5. `task.use_liberation` 关着 → 不跑。

为什么需要那两个线程：手动关自动战斗是**任务停止把战斗循环打断**，异常一路往上抛，`combat_end()` / `on_combat_end()` 整个跳过；
重开时队伍识别没变的话 `load_chars()` 也不跑（角色对象被粘性复用），`reset_state()` 里那句 `opener_armed = True` 轮不到。
`do_perform` 只在任务启用时被调到，站在里面永远看不到"刚才关过"，只有独立线程能观察到 `enabled` 的 True→False→True。
**两个地方都要启线程**：`__init__()` 和 `reset_state()`。F 监视读 `GetAsyncKeyState` 的**高位 0x8000**（低位读一次就清、全进程共享，会被别人吃掉）；
它读得到玩家、读不到宏（宏走 PostMessage 不经过硬件层）；宏跑着时 F 是玩家手动处决，不算重开（`mark_busy`）。
初值取 -1 不是 0（`last_opener` 的"没跑过"也是 -1，给 0 的话开局第一次判定恒成立）。

`macro_enter()` / `macro_exit()` 包住每一圈：进的时候 `skip_combat_check = True`、`mark_busy(True)`、关掉三个人的 `check_f_on_switch`、启 HUD 看门狗；
出的时候**松开长按**（中途抛异常的话鼠标会一直按着，这里是唯一保证松手的地方）、没跑完也把时间轴写进日志、还原 `skip_combat_check`。

## 5. 原语清单

| 原语 | 语义 | 坑 |
|---|---|---|
| `macro_wait(sec)` | 精确等待，**不点击**；0.1s 一片，片间 `check_enabled` | 用在需要持续输出的格子上就是白给 |
| `macro_mark(name)` | 打时间轴标记；顺手做 HUD 看门狗（只比时间戳，不读屏） | 每一步都要打 |
| `hud_ok()` | 读当前帧队伍 HUD 在不在，在就刷新看门狗时刻 | |
| `tap(hold=A_TAP)` | 真按住 0.05~0.06s 的一下普攻 | `task.click()` 只有 10ms 会被吞 |
| `click()` | 重写成 `tap()`（本队内） | 引擎里所有"顺手点普攻"都走它，一处重写全修好 |
| `macro_spam(window, interval)` | 连点一个窗口，段数由 window 决定 | 点完等 `interval - A_TAP`，否则周期变长；别用 `max_clicks` 封顶（会提前结束整个窗口） |
| `spam_key(send, window, poke=, presses=, stop_when=)` | 在窗口里反复发一个技能键盖住动画；发键和点普攻两条节奏互不干扰 | 必须在这个人自己的回合里跑完，别跟切人并行（技能键会被带过换人边界落到新角色身上） |
| `press_key_until_cd(send, available, cap)` | 一直按到技能进 CD；**先见过亮才认暗**，`ready_grace` 内没见过亮就当本来在 CD | 刚切进来那几帧技能栏还是上一个人的 |
| `quick_switch(target, click_during, read_con, assume_con)` | 按数字键直切指定角色，确认到场后 `handoff` 记账 | 见 §6 |
| `switch_retry(target)` | 切人超时就等 HUD 回来再切，最多 `SWITCH_RETRIES` 次 | 只花时间，默认开 |
| `handoff(from, to, con_full)` | 复刻框架 `switch_next_char()` 尾部的交接记账 | 不补的话 `get_current_char()` 返回 None 主循环当场崩 |
| `fire_r(char, tag, window)` | 先等 HUD 在场，再连发 R 到 HUD 连续消失 `LIB_GONE_CONFIRM` 帧 | 按 R 前 HUD 本来就不在会假成功 |
| `ensure_r(char, tag, window, cap, build)` | R 一定要放：亮→按，亮了没出去重按（≤R_TRIES），不亮 `build()` 攒能量、每几轮盲按一次 | 大招是能量门控：判 `liberation_available()`，别用 `has_cd('liberation')` |
| `wait_hud_back(tag, min_gone, tail)` | 等演出结束（先确认消失过、回来连读 2 帧），期间不点 | HUD 回来 ≠ 能出招，收招还有 ~0.8s，紧跟着的单发技能要留一格等待 |
| `wait_hud_up(cap)` | 等 HUD **现在**在场 | 跟 `wait_hud_back` 是两回事 |
| `watch_hud_gone(window, poke_after)` | 盯 HUD 有没有消失（= 演出开始），没消失过了 poke_after 就点普攻攒资源 | |
| `read_con(want)` / `wait_con_full(cap)` | 现读协奏，连读几帧达到 want；后者边打边等 | 0.99 是哨兵值，真满要 1.0 |
| `read_cd(name, char)` | 技能框 CD 秒数，截成 ≥0 | 框架 `get_cd()` 没 CD 时返回负数 |
| `on_field_char()` | 现在场上是谁（要 count 达标才信） | 开局 HUD 渐入时 `in_team()` 会说谎 |
| `break_prompt()` | 怪身上的处决 F 提示（屏幕中间，排除拾取 F） | 顶部谐度满比提示早好几秒，那时按 F 是空按 |
| `need(ok, what)` | 不成立就 `raise MacroBroken` | 只用在"后面的键会落在错的人身上"那种地方 |

## 6. 切人

- **按角色切，不按编队**：`slot = target.index + 1`，宏表/视频里的数字键先翻译成角色。编队顺序随意，代码不用改。
- **确认到场才记账**：发数字键 → `next_frame()` + `in_team()`，index == 目标且 count 达标（三个编号都读到）才算；
  count 不达标的命中要连续 `UNTRUSTED_CONFIRM` 次。`in_team()` 是靠"三个编号里读不到的那个就是当前角色"反推的，
  所以认"切到 3 号"要 1、2 号两个模板都命中，天生比认 1 号难。
- **超时不能假装切过去了**：超时就 `on_field_char()` 读实际是谁、按实际记账；累计失步就 `MacroBroken` 整圈放弃交回框架。
  乱着打完一整轮不如早点重来。**别把切人失败交给框架 `switch_next_char()` 兜底** —— 它按优先级现场挑人，死顺序的轴会被打乱，症状还会伪装成别的问题。
- **演出期间 HUD 不渲染，切人确认必然失败**：紧跟在处决/大招/强化变奏后面的切人，先 `wait_hud_up` 再按数字键。
- **游戏换人 CD 约 1s**：同一个人切走后 ~1s 内切不回来。trace（`0.04:1 … 0.31:1 0.34:0`）里一串旧 index = 游戏在拒绝；
  带 `?` = count 判据挡住了；全是 `x` = HUD 不在。被拒的格子只能"技能一出手就开始狂按切人"。
- **"边打 A 边不停切人"只在角色正处于动作中时安全**（那时游戏拒绝切人，切人键只是在等放行）；角色刚到场、空闲时切人键一定被接受，预点击会被入场过渡吞掉。
- **切人确认"到场" ≠ "能出招"**：紧跟切人的长按按下沿会被入场吞掉；变奏入场有 QTE 锁（帧表「第60F前不响应输入」这类），第一下动作分两句写。
  **声骸 Q 不受 QTE 锁挡**（嘉露莫 10-16 录屏：嘉贝到场 0.1s 按的 Q 就进了 CD），所以"Q 进 CD 了"不能当入场结束的锚点 —— 后面紧跟的 A/F/E 照样落在锁里被吞（那次只按一次的强化E 就这么没了）。要按"切人确认 + 帧表锁长"等够再出手；干跑的假游戏也要放 Q 过锁，不然测不出来。
- **绕开 `switch_next_char()` 会丢掉角色自己挂在里面的动作**（菲比满协奏切走前的 `click_echo()`、outro 计数）。写宏之前先读每个队友重写的 `switch_next_char`，把动作搬进宏的收尾段。同理 `f_break`（切人时框架会按处决，宏里要 `check_f_on_switch = False` 自己控）。
- 宏表切人格的 gap 常只有 50ms，带确认的切人每格晚 ~0.13s，一轮能累计 1.7s。`run_macro` 打 `N keys in X.XXs (table says Y.YYs)`，差值就是保底总开销。

## 7. 大招与演出

- `fire_r` 是**演出一开始就返回**的。宏的最后一发大招后面必须等演出结束再把控制权交回框架（否则框架在演出里 `target lost` → 脱战 → 重进 → 又跑启动轴，实机见过 67 次启动轴 0 次循环轴）。
- 大招演出期间游戏时钟停（倒计时不走），框架用 `time_elapsed_accounting_for_freeze` 扣；`wait_hud_back` 里 `add_freeze_duration` 记一笔。
  按"游戏时间"卡窗口的格子（比如"雷主到场后 6.3s 游戏时间内不切"），要用墙钟减掉演出时长。
- 宏用 `fire_r`（不阻塞）开大招时，**内置角色的大招状态没人打时间戳**（`liberation_time` 是在内置 `click_liberation()` 里赋的）。
  之后要调内置方法（比如赞妮 `nightfall_combo` 读剩余时间）就先手动补齐 `in_liberation` / `liberation_time`。
- `BaseChar.sleep()` 结尾**无条件**把 `task.skip_combat_check` 置回 False。调完任何内置代码要重新打开。
- 大招后紧跟的那一发**只发一次**的技能键要留 ~0.8s 收招（R 会重试，E 不会；E 被吞形态就没切，后面全建立在错误前提上）。人可能还在空中：`if self.flying(): self.wait_down()`。

## 8. 长按与 SendInput

- PostMessage 长按：一次 `mouse_down()` 一直有效，**包括跨过切人**（但长按跨切人不会让新角色出手，只对"当前角色继续当前动作"有效）。
  长按期间任何 `mouse_down` / `send_key` / `click` 都会投 `WM_ACTIVATE` 把按住打断。需要在按住期间按别的键时用不带 activate 的发键（景月守的 `key_na`）。
- 蓄力类长按（绯雪 R2、秧秧重击）**不能重发按下**：按一次 → `macro_wait` → 松。"按住期间每 0.2s 重发防掉键"等于连点，蓄力从来没起来。
- 需要系统级长按时用 `SendInput`（`attack_down(direct=True)`），**SendInput 按下的必须 SendInput 松开**，否则宏异常退出时整台电脑的左键都是按着的。
  `macro_exit` 和 `on_combat_end` 都要 `release_attack()`。
- 重击预输入：把"点普攻"换成"按住 0.15s 再松"。

## 9. 日志：时间轴是排查的唯一依据

实机问题 90% 是读日志定位的，所以引擎要把这些都打出来：

- 每一步 `macro_mark`：`>Rov^(0.12|con0.00|A x2)`（切人耗时、是否变奏、点了几下）、`R_fired(x5,0.31s)` / `R_NOFIRE(x30)`、`E_ok(x3,A x4,0.52s)` / `E_CD?(...)`、`等满(cap,2.53s)`。
- 每圈结束一行 `cycle timeline: ...`；被打断/被停也要写（`(没跑完)`）。
- 切人慢（>0.4s）时打 trace；协奏没满时打采样序列；判据走了哪条路（`lead` / `air` / `forte` / `cap` / `blind`）写进标记。
- 判据函数里**不要夹带只给日志用的读屏**（一次 OCR 几十毫秒，轮询里每次都花）。

## 10. 引擎怎么搬到新队伍

1. 选底子：引擎原语从最新定稿的那份抽；某个角色的判据/段落从做过这个角色的队伍抽（见 `teams-index.md`）。
2. 写个构建脚本按方法名逐字抽方法拼成新文件（别手抄），顺手检查每个被引用的常量都定义了。生成后**以后直接改生成的文件**，构建脚本只用一次。
3. 抄完逐条过"按住语义"和"旧常量"（SKILL.md D 节）。
4. 改类名、`is_in_<队>`、`teammate()` 用到的类名、日志前缀（每条轴一个短前缀，`xls:` / `jys:`），F 监视/开关监视逐字保留。
5. `check_team.py` 过一遍，再写干跑。
