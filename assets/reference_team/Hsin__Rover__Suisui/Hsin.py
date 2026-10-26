import base64
import ctypes
import threading
import time

import cv2
import numpy as np

from src import text_white_color
from src.char.BaseChar import SwitchPriority, forte_white_color
from src.Labels import Labels
from src.char.Hsin import Hsin as NativeHsin

# ==================== 物理 F 键监视 ====================
# 跟 Iuno__JingRan__ShoreKeeper/JingRan.py 里那份逐字相同, 说明见 Chisa__Suisui__YangYangSp/YangYangSp.py。
F_VK = 0x46              # 'F'
F_POLL_INTERVAL = 0.05   # 一次按键按住的时间远大于这个, 不会漏采
F_LOG_DEBOUNCE = 1.0     # 按住不放时别刷日志
F_TASK_NAME = 'FStartCombatTask'


def f_settings(task):
    """读界面上的(开关, F 之后等待秒数)。没装那张卡片就返回默认值(开, 0 秒)。"""
    executor = getattr(task, 'executor', None)
    for group in ('trigger_tasks', 'onetime_tasks'):
        for other in getattr(executor, group, None) or ():
            if type(other).__name__ == F_TASK_NAME:
                try:
                    return bool(other.enabled), float(getattr(other, 'f_start_delay', 0) or 0)
                except Exception:
                    return True, 0.0
    return True, 0.0


# ==================== 自动战斗开关监视 ====================
# 【玩家手动开关自动战斗, 必须从启动轴重跑】。手动停任务不走 combat_end(), opener_armed 会跨局留在
# False, 而角色对象常被粘性复用、reset_state() 不跑。只有独立线程能观察到 enabled 的 True->False->True。
ENABLE_POLL_INTERVAL = 0.2


def start_enable_watch(task, logger=None):
    """盯 task.enabled 的 False->True 跳变, 把时刻记到 task._ww_task_restarted_at。每个 task 只启一次。"""
    if getattr(task, '_ww_enable_watch_started', False):
        return
    task._ww_enable_watch_started = True
    if not hasattr(task, '_ww_task_restarted_at'):
        task._ww_task_restarted_at = -1

    def watch():
        was_on = None
        while True:
            try:
                now_on = bool(getattr(task, 'enabled', False))
                if was_on is False and now_on:
                    task._ww_task_restarted_at = time.time()
                    if logger:
                        logger.info('auto combat re-enabled -> opener re-armed')
                was_on = now_on
                time.sleep(ENABLE_POLL_INTERVAL)
            except Exception:
                return

    threading.Thread(target=watch, name='ok_ww_enable_watch', daemon=True).start()


def start_f_watch(task, logger=None):
    """把【物理】F 键按下的墙钟时间记到 task._f_last_press。每个 task 只启一次。"""
    if getattr(task, '_f_watch_started', False):
        return
    task._f_watch_started = True
    if not hasattr(task, '_f_last_press'):
        # -1 = 从没按过, 跟 last_opener 的"没跑过"对齐(给 0 的话开局第一次判定恒成立)
        task._f_last_press = -1

    def watch():
        try:
            user32 = ctypes.windll.user32
            user32.GetAsyncKeyState.restype = ctypes.c_short
        except Exception as e:
            task._f_watch_started = False
            if logger:
                logger.error(f'f watch: GetAsyncKeyState unavailable ({e}), '
                             f'the "press F to re-arm the opener" shortcut stays off')
            return
        last_log = 0
        was_down = False
        while True:
            try:
                down = bool(user32.GetAsyncKeyState(F_VK) & 0x8000)
                if down and not was_down and f_settings(task)[0]:
                    now = time.time()
                    # 宏正在跑 = 正在战斗, 这下 F 是玩家手动处决, 不是重开副本
                    if (getattr(task, '_three_fire_macro_busy', False)
                            or getattr(task, '_ww_macro_busy', False)):
                        if logger and now - last_log >= F_LOG_DEBOUNCE:
                            last_log = now
                            logger.info('physical F pressed while the macro is running '
                                        '(manual execution) - opener NOT re-armed')
                        was_down = down
                        time.sleep(F_POLL_INTERVAL)
                        continue
                    task._f_last_press = now
                    task._f_pressed_at = now
                    if logger and now - last_log >= F_LOG_DEBOUNCE:
                        last_log = now
                        logger.info('physical F pressed, opener re-armed')
                was_down = down
                time.sleep(F_POLL_INTERVAL)
            except Exception:
                return

    threading.Thread(target=watch, name='ok_ww_f_watch', daemon=True).start()


# ==================== SendInput 左键(心的两段长按用) ====================
# 结构体照搬 Iuno__JingRan__ShoreKeeper/JingRan.py。
_INPUT_MOUSE = 0
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', ctypes.c_ushort), ('wScan', ctypes.c_ushort), ('dwFlags', ctypes.c_ulong),
                ('time', ctypes.c_ulong), ('dwExtraInfo', ctypes.c_size_t)]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', ctypes.c_long), ('dy', ctypes.c_long), ('mouseData', ctypes.c_ulong),
                ('dwFlags', ctypes.c_ulong), ('time', ctypes.c_ulong), ('dwExtraInfo', ctypes.c_size_t)]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [('uMsg', ctypes.c_ulong), ('wParamH', ctypes.c_ushort), ('wParamL', ctypes.c_ushort)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [('ki', _KEYBDINPUT), ('mi', _MOUSEINPUT), ('hi', _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [('type', ctypes.c_ulong), ('u', _INPUTUNION)]


def send_input_left(up):
    """系统级左键按下/抬起。返回是否发出去了(发不出去调用方退回 PostMessage)。"""
    try:
        inp = _INPUT(type=_INPUT_MOUSE)
        inp.u.mi = _MOUSEINPUT(0, 0, 0, _MOUSEEVENTF_LEFTUP if up else _MOUSEEVENTF_LEFTDOWN, 0, 0)
        return ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT)) == 1
    except Exception:
        return False


class MacroBroken(Exception):
    """某一步切人没成功 / HUD 长时间不在, 后面的按键会落在错的人身上 —— 整圈放弃, 交回框架。"""


class Hsin(NativeHsin):
    """心。心雷穗(心/雷主·导电/穗穗)里她兼任【整条轴的持宏者】, 三个人的 do_perform 都转到 drive()。

    ================= 轴的出处 =================
    长风ei 的「心雷穗 25s 轮椅轴」教学视频(E:/轴视频/【电磁】心雷穗-25s轮椅轴.mp4, 1080p, 1.0x + 字幕定格),
    键盘浮层 + 步骤条 + 游戏倒计时逐帧扒的, 151~201s 的完整演示段不定格。作者编队 1 心 / 2 雷主 / 3 穗穗; 代码【按角色切人】, 编队随意。
    雷主在框架里就是 Rover(漂泊者·导电)。【心要用共鸣模态·电磁】。

    ================= 轴的形状 =================
    启动轴: 穗穗 3A(水云息满) -> 醒春潮(进濯雨时 15s) -> [马上]切雷主
            雷主 E(雷引, 把人拉上去) -> 空中 A(下落) -> 落地 -> 切穗穗
            穗穗 A 到芳菲信 600(三段回路满) -> Q -> R -> 演完 -> 变奏雷主
    循环轴: 穗穗(心变奏进来, 变奏直接给濯雨时) E -> 3A -> 第三段时切雷主
            雷主 E -> 空中 A(下落) -> 落地 -> 切穗穗
            穗穗 A 到芳菲信满 -> Q -> R(视频里常被 R 的 CD 卡一下) -> 演完 -> 变奏雷主
    之后两条一样:
      雷主 (变奏) Q -> 一直 A 到电涌满 -> 点按 E(超负荷, 只能短按) -> 连按 R(超负荷动作 ~2s 打完才出) -> 演完 -> 变奏心
      心   (变奏·应世相) Q -> A 到应世心满 -> 按住出步红尘 -> 转相 -> 演完
           -> [不切人] 照世相 3A(启动轴) / 2A(循环轴) -> E -> 连按 E 进统御众机 -> A(中间闪避, 有处决就在闪避那一刻处决)
           -> A 到照世心打空 -> 按住临寰宇 -> 万阙垂天 -> 演完【不按 E】-> 协奏满 -> 变奏穗穗
    宏在【穗穗变奏入场、HUD 在场】时返回, 下一次框架调的就是她(循环轴从她的 E 开始)。

    ================= 为什么这么打(nanoka 技能文本) =================
    - 雷主: 电涌(上限 120)由变奏/普攻/雷引/克敌攒, 满了 E 换成超负荷。短按 = 队伍攻击 +10% + 怪 10 层电磁效应;
      长按 = 扣 60 协奏进临界共鸣(心就吃不到变奏了)。延奏给下一个登场的(心)电髓: 挂上异常后全伤害加深 25%。
    - 心固有: 雷主放【变奏技能】时心和雷主导电伤害 +20%, 所以雷主第二格一定要变奏进来。
    - 心照世相(电磁): 普攻第1段生成活字心锁, 第2段/E 打碎时 +150 照世心(转相后一次), E 打完照世心满 300 就换万阙连衡。
    - 穗穗第一次翾舞(延奏后 ~6s)时在场的人, 他的延奏把烟岚交给下一个登场的人 —— 这队是雷主在场、交给心。
    - 作者: 万阙垂天之后别按 E, E 会把电磁效应层数一次结算掉, 心专武那 30% 效应加深要心在场才吃得到。

    ================= 判据 =================
    - 心: 应世心满 = hsin_h1(花图标); 转相解锁 = 步红尘清空 + 2.06s; 万阙垂天解锁 = hsin_lib2 —— 这三条都照心汐守定稿。
    - 心: 进统御众机 = 重击位雕像图标(xn_tongyu), 照世心打空 = 重击位人像(XN_READY_GLYPH), 都照心卜穗定稿。
    - 心: 【统御众机里回路条 8 颗雕像 = 照世心, 被吃掉的从右往左翻面】(xn_statue_count): 翻面那一刻雕像上半身先变亮白,
      0.3~0.4s 后中间才出红菱形; 两样任一连读 2 帧就记住这颗翻了。中间那根白条是统御众机的剩余时间(13s 匀速), 不是照世心。
    - 雷主: 【电涌满 = 回路条右边那两个 [E] 小框亮(白字)】(lei_ready_white, 跟框架 is_forte_full 同一个框)。
      超负荷出没出去 = 点按 E 到进 CD, 而且 CD > 12s(雷引才 10s)。小框在超负荷动作期间一直亮, 不能拿来确认。
    - 雷主: 【在空中 = Q(声骸)图标整个变灰】(lei_echo_white)。第一格看到 白 -> 灰 -> 白 才切人(下落打出来、落地了)。
    - 穗穗: suisui_e1 = 醒春潮可放, suisui_forte3 = 芳菲信满 600, 照秧千穗定稿。

    ================= 改这个文件之前先读 =================
    - 引擎(macro_* / quick_switch / fire_r / wait_hud_back ...)、心两段、穗穗几格逐字抄自 Douling__Hsin__Suisui/Hsin.py(心卜穗定稿 v1.0)。
    - 【自定义 __init__ 里跟内置版不同的字段会被打回内置值】, 要保住就在 reset_state() 里重申。
    - 普攻一律走 tap()(按住 A_TAP 秒): task.click() 只按 10ms, 打不出来。
    - 长按期间不调 click()/mouse_down()/send_key() —— 它们先投 WM_ACTIVATE, 会把按住打断。
    """

    # ==================== 全局节奏(引擎用) ====================
    A_INTERVAL = 0.12
    KEY_INTERVAL = 0.10
    A_TAP = 0.06                 # 普攻按住这么久才算一下; task.click() 的 10ms 会被吞

    # ---- 切人 ----
    SWITCH_TIME_OUT = 2.5
    SWITCH_KEY_DOWN_TIME = 0.02
    SWITCH_KEY_INTERVAL = 0.0
    UNTRUSTED_CONFIRM = 3
    TRACE_SWITCH = True

    # ---- 大招 / 演出 ----
    LIB_KEY_INTERVAL = 0.03
    LIB_ANIM_TIME_OUT = 8.0
    HUD_NO_ANIM_GRACE = 0.35
    LIB_GONE_CONFIRM = 3         # HUD 连续这么多帧不在 = 演出真的开始了
    HUD_UP_CAP = 1.0             # 按 R 之前等 HUD 在场的上限(防假成功)
    HUD_BACK_CONFIRM = 2         # 演出中途 HUD 会闪一两帧, 回来要连读这么多帧

    # ---- 杂项 ----
    CON_SAMPLE_MAX = 24
    FIELD_SETTLE_TIME_OUT = 1.5
    E_RESEND_STEP = 0.06
    SKILL_BAR_SETTLE = 0.40      # 刚切进来多久没见过技能亮就当它在 CD 上
    M_E_KEY_DOWN = 0.05
    # 协奏: 0.99 是环没闭合的哨兵值, 要真满; 连着几帧才算
    CON_ENOUGH = 1.0
    CON_FULL_CONFIRM = 3
    CON_POLL = 0.03

    # ==================== 防重入 ====================
    OPENER_MIN_GAP = 60.0

    # ==================== 保底 ====================
    # 只花时间的保底默认开(切人重试 / 等 HUD / 判据没成立就再按【那一个本该出去的键】);
    # 会改状态的只在判据明确说"这一下没出去"时才补
    SWITCH_RETRIES = 2           # 切人超时后先等 HUD 回来再切, 最多再试这么多次(被击飞/硬直时游戏不放人)
    SWITCH_RETRY_TIME_OUT = 3.00
    HUD_LOST_ABORT = 9.00        # 队伍 HUD 连续这么久没见过 = 关卡结束/过场/窗口没了, 整圈放弃(最长的演出是万阙垂天)
    DRIVE_HUD_CAP = 1.50         # 框架调进来时 HUD 这么久都不在就什么都不做(结算画面上框架还会一直调进来)
    R_TRIES = 3                  # R 亮着但没放出去(被吞/被打断)就再按, 最多这么多次
    R_BLIND_EVERY = 3            # R 读成暗时每这么多轮攒能量盲按一次(防读数不准)
    R_BLIND_WINDOW = 0.40
    R_BUILD_SLICE = 0.60         # 攒能量每轮的连点时长

    # ==================== 穗穗 ====================
    # ---- 启动轴: 3A 攒满水云息 -> 醒春潮(强化E) -> 马上切雷主 ----
    # 醒春潮第1F 就清水云息、给 15s 濯雨时, 后面的伤害可脱手; 视频里按完 E 0.1s 就切走了
    SUI_E1_THRESHOLD = 0.80      # suisui_e1 = E 图标的醒春潮图案, 亮着 = 水云息满
    SUI_E1_FILL = 2.50           # 没亮就点普攻攒, 上限(循环轴兜底那种, 穗穗可能还在濯雨时); 3A 正好 123 水云息(上限 120), 视频 3A 用了 1.9s
    # 启动轴醒春潮必须开出来: 上限放到这么久。10-06 实机 10 局 4 局 2.5s 没亮(开局普攻打不中怪), 按了普通 E 切走, 穗穗第二格整段白打
    SU_E1_MUST_CAP = 12.0
    SUI_E1_FILL_INTERVAL = 0.12
    SUI_E1_CAST_CAP = 1.50       # 按到图标消失的上限
    SUI_E1_KEY_INTERVAL = 0.05
    # ---- 循环轴第一格: 心变奏进来(变奏直接给濯雨时) -> E -> 3A -> 第三段时切雷主 ----
    # 视频: 变奏入场 ~1.4s 里按的 E 全被丢, 进 CD 那一刻起 A 了 2.2~2.6s(三段)才切
    SU_L_E_CAP = 2.20            # E 按到进 CD 的上限(变奏入场里按的会被丢, 一直按到出去)
    SU_L_3A = 2.30               # E 判到进 CD 之后连点普攻这么久再切(打到第三段)
    SU_L_A_EVERY = 0.15
    SU_L_MIN_FIELD = 1.00
    SU_L_INTRO_FRESH = 4.00      # 到场超过这么久才轮到这一格 = 中间断过(濯雨时还在不在说不准), 走启动格
    # ---- 第二格: A 到芳菲信满 -> Q -> R -> 演完 -> 变奏雷主 ----
    # 强化A1~A4 一轮只给 570 芳菲信, 不到 600 —— 所以不按段数按判据: 延奏清掉 >599 才有三次翾舞 + 烟岚前置
    FORTE3_GATE = True
    FORTE3_WAIT = 6.0            # 等的上限(秒), 超了照放不误
    FORTE3_THRESHOLD = 0.75
    FORTE3_CONFIRM = 2
    FORTE3_SUSPECT = 0.30
    # 【濯雨时只有 ~15s】(醒春潮 / 变奏入场给的), 过了芳菲信就清掉、普攻再也攒不满。循环轴是变奏那一刻起算,
    # 穗穗第二次上场时常常只剩 4s 左右: 10-06 实机循环轴 5 圈 4 圈撞满 6s 上限(启动轴醒春潮晚 2s, 大多 3.95~5.43s 就满)。
    # 唯一一次循环轴满的是变奏后 15.4s。所以等满的上限 = 濯雨时还剩多久(SU_QIANG_DUR), 过期了就直接 Q R
    SU_QIANG_DUR = 16.0
    SU2_A_MIN = 3.60             # 至少打完 4A(强化A1~A4 ≈ 3.4s)
    # 【三段回路不满不 QR】(用户 10-06): 14:17~14:18 三局启动轴撞 6s 上限没满就开了大, 另两局 5.95/5.99s 才满(贴着上限)。
    # 上限放到 SU2_MUST_CAP; 只有濯雨时估计已经过了 SU_QIANG_GRACE 还没满才放弃(过了普攻攒不出芳菲信)
    SU2_MUST_CAP = 10.0
    SU_QIANG_GRACE = 2.50
    # 打完 4A(~3.4s)还没满、E 好了: 补一个 E。濯雨时 E 第36F 还在场就给 100 芳菲信(帧表), 正好补上 4A 只有 570 的那一截
    SU2_E_RESCUE_AT = 4.20
    # 【大招前协奏要够】(用户 10-06): 穗穗大招只回 20 协奏(帧表「大招-前置」协奏回收 20, nanoka 同; 声骸封庭械囿 0),
    # 大招前不到 80, 放完协奏不满, 切雷主就不是变奏(心的导电加成、雷主延奏全没)。启动轴回路满了协奏也可能才七十几。
    # 不够就点普攻补(强化普攻一段 4~8 协奏), 上限 SU_R_CON_CAP; 濯雨时只剩 SU_R_QIANG_MARGIN 就不补了(过了芳菲信清零, 翾舞全丢)
    SU_R_CON_MIN = 0.82          # 100 - 20 = 80, 留 2 点读数误差
    SU_R_CON_CAP = 4.00
    SU_R_QIANG_MARGIN = 1.00
    SU_Q_WINDOW = 0.15           # Q 连发两下的窗口(视频 Q 后 0.07s 就按 R)
    SU_R_WINDOW = 1.50
    SU_R_CAP = 5.00              # R 不亮就攒能量的上限
    SU_R_ANIM_MIN = 3.60         # 穗穗大招藏 HUD 258F = 4.3s
    SU_R_ANIM_CAP = 7.00
    # 变奏心之前穗穗协奏要真满: 心没吃到变奏就没有 +60 应世心, 穗穗也不会跳延奏(三次翾舞全丢)
    SU_CON_CAP = 3.00

    # ==================== 雷主(漂泊者·导电, 框架类名 Rover) ====================
    # ---- 第一格(普通切人进来): E(雷引, 把人拉上去) -> 空中 A(下落) -> 落地 -> 切穗穗 ----
    # 10-06 实机录屏: E 后 0.35~0.5s 离地; 旧版 E 后 ~1.0s 就切, 两次切的时候都还在空中, 下落没打出来。
    # 教学视频: E -> 空中按 A 0.63s -> 切人 1.13s(下落正好落地)。切人的冷却只有 1s(穗穗头像上有倒计时), 不卡。
    # 判据: 雷主的 Q(声骸)图标在空中整个变灰 —— 白字占比 地面 0.11~0.14 / 空中 0.00(录屏两次, 一帧不差)。
    # 看到 白 -> 灰 -> 白 就是落地了。声骸在 CD 上读不出来(一开始就没见过白), 就按 E 后 LEI1_BLIND 秒切
    LEI1_E_CAP = 1.20            # E 按到进 CD 的上限
    LEI1_A_EVERY = 0.15          # 一直点: 离地之后第一下 A 就是下落
    LEI1_ECHO_WHITE = 0.04       # 录屏(720p 压缩)按框架 text_white_color: 地面 0.062~0.122, 空中 0.000
    LEI1_ECHO_CONFIRM = 2
    LEI1_MIN_AFTER_E = 0.90      # 落地了也至少 E 后这么久才切
    LEI1_AIR_BY = 1.00           # E 后这么久还没看到离地 = 读不出来, 走 LEI1_BLIND
    LEI1_BLIND = 1.50
    LEI1_CAP = 2.40              # 离地了一直没读到落地也到这一刻切
    LEI1_SWITCH_TIME_OUT = 3.00
    LEI1_FULL_READS = 2          # 上场先读这么多帧 [E] 小框: 电涌已经满了就不按 E(那一下会是超负荷)
    # ---- 第二格(穗穗大招演完变奏进来): Q -> A 到电涌满 -> 点按 E(超负荷) -> 连按 R -> 演完 -> 变奏心 ----
    # 视频(倒计时, 从到场起): Q 0.37~0.43s; 超负荷动作 ~2s 打完 R 才出; R 演出停游戏时钟 ~3.8s; 演完马上变奏心
    LEI2_A_FROM = 0.20
    LEI2_Q_AT = 0.35
    LEI2_Q_WINDOW = 0.15
    LEI2_A_EVERY = 0.15
    # 到场这么久小框还没亮就按 E: 电涌没满按出来的是雷引, 正好把人拉到怪身边(雷引也加电涌), 再补到满放超负荷。
    # 10-06 16:27 循环轴电涌攒了 6s 才满; 16:49 启动轴 Boss 飞远了普攻打空气, 7.5s 都没满, 雷引之后只补了 0.6s 就放弃, 那一圈没超负荷
    LEI2_READY_CAP = 6.50
    # 【电涌满 = 回路条右边那两个 [E] 小框亮(白字)】。10-06 实机录屏(2560x1440): 满的那一帧亮起, 一直亮到超负荷动作打完;
    # 雷引还在 CD 上也照亮(E 图标同时换成超负荷)。框架 is_forte_full() 读的就是左边那个小框。
    # 旧版读回路条的紫色, 实机一直读 0: 条是半透明的, 颜色跟着背景走(教学视频色相 130~139, 这关橙红背景 157~174)。
    # 旧版因此启动轴满了 1.4s 才按(撞 6s 上限)
    LEI_READY_BOX = (2251, 1993, 2311, 2016)
    LEI_READY_MIN = 0.03         # 白字占比到这个算亮。录屏(720p 压缩)按框架同一套白色阈值: 亮 0.056~0.131, 没亮 0.000; 框架 is_forte_full 的 0.08 太贴
    LEI_READY_MAX = 0.70         # 放大招整屏白闪那几帧整块都白(1.00), 不算
    LEI_READY_CONFIRM = 2
    LEI_E_CAP = 1.00             # 超负荷: 一直点按 E 到它进 CD(按键 10ms, 只短按; 长按扣 60 协奏进临界共鸣)
    LEI_E_CD_MIN = 12.0          # 超负荷 CD 25s, 雷引 10s: 进 CD 了还要够长才是超负荷
    LEI_E_TRIES = 2              # 没认出超负荷就接着 A 到小框亮再按, 一共这么多回
    LEI_E_RETRY_A = 2.50         # 第二回之前 A 到小框亮的上限(第一回多半是雷引贴脸, 要给时间攒满)
    LEI_R_WINDOW = 3.50          # R 一直连按: 超负荷动作那 ~2s 里按的全被丢
    LEI_R_CAP = 6.00
    LEI_R_ANIM_MIN = 2.80        # 雷主大招藏 HUD ~3.8s
    LEI_R_ANIM_CAP = 6.50
    # 穗穗第一次翾舞(延奏后 5.87~6.11s, 心卜穗实测)时雷主要在场, 他变奏心才把烟岚交给心。
    # 游戏时间 = 到场到现在 - 大招演出(那段停时钟)。视频启动轴只有 6.0s, 贴线
    LEI2_LEAVE_MIN = 6.30
    LEI_CON_CAP = 3.00           # 变奏心之前雷主协奏要真满: 心才有变奏 +60 应世心, 雷主才放延奏(心拿电髓)

    # ==================== 心 ====================
    # ---- 应世心条(4K 坐标, hcenter): 回路条中间徽记左右两半的紫色格子(心汐守定稿) ----
    XN_GAUGE_L = (1627, 1999, 1837, 2011)
    XN_GAUGE_R = (1965, 1999, 2175, 2011)
    XN_GAUGE_VALID = 0.50        # 左半 >= 这个才算"在应世相、读数可信"(变奏入场之后左半就是满的)
    XN_YING_READY = 0.70         # 右半到这么多就算到线
    XN_CONSUMED = 0.15           # 按住之后左半掉到这个以下 = 整条清空 = 步红尘出手
    XN_FULL_THRESHOLD = 0.70     # hsin_h1(应世心满的花图标)
    XN_HOLD_SENDINPUT = True     # 心的长按走 SendInput(游戏在前台时): PostMessage 的按下沿落在普攻收招里会被丢掉

    # ---- 第一段(雷主变奏进来, 应世相): Q -> A 到应世心满 -> 按住出步红尘 -> 转相 ----
    # 视频(倒计时, 从到场起): Q 0.46~0.55s; 一直点普攻(变奏后第一下是 a4); 按住 2.0 / 2.3 / 3.2s; 按住后马上连按 R 到转相出
    XN1_Q_AT = 0.30
    XN1_Q_WINDOW = 0.15
    # 上场先认一下是不是应世相(转相图标 / 应世心花 / 应世心条, 任一读到就是): 上一圈万阙垂天没放出来的话心还在照世相,
    # 这时按 R 放的是借相。连读 XN_FORM_READS 帧(HUD 在场)三样都没有才算照世相
    XN_FORM_CAP = 0.40
    XN_FORM_READS = 4
    XN1_A_FROM = 0.45
    XN1_A_EVERY = 0.17
    XN1_A_HOLD = 0.08
    XN1_GATE_CONFIRM = 2         # 连读这么多帧满/到线才算(特效扫过会闪)
    XN1_HOLD_AT_MIN = 1.90       # 满了也至少打到这一刻再按住(a4 打完)。心卜穗那边为了卜灵赶翾舞放到 2.40, 这队心两段不切人, 不用等
    XN1_A_CAP = 4.50             # 一直不满就打到这一刻照按
    XN1_LAST_A_GAP = 0.12        # 最后一下普攻和按住之间至少隔这么久(按下沿别跟点击粘在一起)
    XN1_HOLD = 1.80              # 按住时长。步红尘免疫打断, 转相解锁从清空那一刻算, 按久了不耽误 R
    XN1_RETRIES = 2              # 按满 XN1_HOLD 条都没清空(= 出的是普通重击) -> 补两下 A 再按
    XN1_RETRY_A = 2
    XN1_FILL_EVERY = 0.40
    # 转相(R1)解锁 = 应世心条清空(步红尘出手) + 2.06s(心汐守三个样本一帧不差)。这队转相解锁就按, 演完直接打照世相
    XN1_R1_UNLOCK = 2.06
    XN1_R1_POLL_FROM = 1.85
    XN1_R1_MARGIN = 0.08
    XN1_R1_LIT_CAP = 3.00
    XN1_R1_READS = 2
    XN1_R1_BLIND_AT = 2.60
    XN_R_WINDOW = 1.50           # R 连按到 HUD 消失的窗口
    XN1_R1_RESCUE_CAP = 8.00     # 转相没出就补到出为止(照世相、万阙垂天、整个第二段都靠它)
    XN1_R1_RESCUE_A = 0.80
    XN1_R1_LOST_ROUNDS = 3
    XN_R_ANIM_MIN = 3.90         # 转相 / 万阙垂天演出藏 HUD 4.3s 以上, 中途 HUD 会闪一帧
    XN_R_ANIM_CAP = 8.00

    # ---- 第二段(转相演完接着打, 照世相): 3A/2A -> E -> 连按 E 到统御众机 -> A -> 闪 -> 2A -> 按住到临寰宇 -> 万阙垂天 ----
    # 视频(倒计时, 从 HUD 回来起): 启动轴 3A 1.6s 后 E, E -> 统御众机 0.4s; 循环轴 2A 后 E; 完整演示 E 后连按 1.6s 才进。
    # 统御众机里 A 3.5~3.8s -> 闪(启动轴是处决) -> A -> 按住 0.7s 临寰宇出手(照世心打空)
    XN2_A_EVERY = 0.15
    # 作者: 3A 攒效应层数、2A 消耗效应层数, 都行。普攻第1段生成活字心锁, 第2段打碎它才给那一次 +150 照世心。
    # 启动轴照视频 3A -> E -> 马上万阙连衡(视频和实机都是 E 后 0.44~0.58s, 普通 E 起手就被接掉)。
    # 【循环轴照视频 2A -> E -> 等普通 E 整段打完 -> 万阙连衡】: 视频 2A 后 ~1s 按 E, E 放完 1.5s 图标才换万阙连衡。
    # 普通 E 最后一下会主动引爆电磁效应(技能文本), 不能接掉。10-06 16:28 循环轴改打 3A, 照世心早满了,
    # 普通 E 起手 0.45s 就被万阙连衡接掉(用户: "循环轴里根本没放出 E 直接就强化 E 了")
    XN2_3A = 1.55
    XN2_2A = 0.85
    XN2_E_FULL = 1.45            # 循环轴普通 E 判到进 CD 之后这么久内不再按 E(让它打完)。视频 1.5s, 10-06 实机 2A 那版 1.45~1.68s 才换万阙连衡
    XN2_E1_CAP = 1.20            # 照世相 E(CD 20s)按到进 CD 的上限
    XN2_E_MASH = 0.15            # 之后连按 E 的间隔: 照世心满的那一刻 E 变万阙连衡, 按下去进统御众机; 没满按 E 是空操作(还在 CD)
    XN2_LIANHENG_CAP = 3.00
    # E 后这么久还没进统御众机就边按 E 边点 A(普攻也给照世心), 不干站。放在普通 E 打完之后, 免得普攻把 E 打断
    XN2_LIANHENG_POKE_AT = 1.80
    XN2_LIANHENG_A_EVERY = 0.20
    XN2_RESCUE_CAP = 3.00        # 没进统御众机: 普攻攒照世心 + 按 E 交替, 上限
    XN2_RESCUE_A = 0.80
    XN2_RESCUE_E = 0.80
    XN2_TY_CONFIRM = 2           # 雕像图标连读几帧才认
    XN_TY_MIN = 0.60             # 统御众机 0.71~1.00 / 其他 <= 0.38
    XN_TY_GLYPH = (
        'AAAAAAAMJCEsJBYBAAAAAAAAABiR1cJ40tzbpyYAAAAAABK+4+Pt2unk48BaJAAAAAhQg6aMnN1/l6RzUVEbAAAzV3Dw9crHyvngXlFQRQIJ'
        'VFqs8dbtovLV8JdRUFAdIlmK7ZPT7IT7v6Dtbk9bOzdhj5en/O2E/PmHoXdelTpIsV1Xrv3thPz7iE9XwJuUJsCvW6797YX9+4dTsfjxriWy'
        '9KGQ++2E/fqGnvfU33sBpvjsmt/thPzfmeylk9cPADOnpLzM7IT4tc54Y+FhAAAASGKt+eyD5uiKUbyiBQAAAAAkjf3tg/j6h3aCCQAAAAAA'
        'AAZbpFvGrUwKAAAAAA=='
    )
    XN_TY_SLOT = (2826, 1893, 82, 79)   # 重击位(4K, 跟 hsin_h1 的标注框一样)
    # 【照世心打空 = 重击位从雕像换成人像】, 这时候按住 ~0.45s 出临寰宇。雕像还在时按住是白按:
    # 统御众机里照世心是普攻/闪避反击打掉的, 按住重击不消耗(10-06 实机 09:36 / 09:39 两次按满 3s 没出, 补几下 A 人像一出来就出了)。
    # 人像模板取自 10-06 两份 2K 录屏三次临寰宇: 人像帧 0.93~1.00(按住时外面多一圈金光也算), 雕像帧 <= 0.16, 其余所有帧 <= 0.64, 缩 1080 一样
    XN_READY_MIN = 0.80
    XN_READY_GLYPH = (
        'AAAAAAAGGDxjHgwAAAAAAAAAABQoWcH31Vg3Jg0AAAAAACGmh+r9+X82NzlcMgAAAAZ47tD9/c06R2NGZ2cWAAA32P38/f2+N0xtaDY3MQIa'
        '3/v9/v3x4DhNbFk2OEcVYf39/f34yMM4RGJWQjmCKmH9+vW6sa2FPT09WGFLyjZ5/c7E4fWaQD0/UHOX0POeYfmXotjqXz09PkBvmojMUTfc'
        'vZnUhD08PDw9mcfbvzMBauG+pJZJREA9P9L05XAFACb1+/38refMZD3D+oQjAAAAbfn9/tDY/LQ7tOMxAgAAAABU2f7is/y+QMd0AgAAAAAA'
        'AAhcpG3GgygPAAAAAA=='
    )
    XN2_READY_CONFIRM = 2
    # 统御众机里: 一直普攻到人像出来, 中间闪避一次(有处决提示就用处决代替)。
    # 【闪避/处决的时机 = 照世心雕像从右往左翻满 4 颗的那一刻】(用户 10-06 "前面就是 4 层, 后面每下都是 2"):
    # 万阙连衡出招动画 ~2.5s 里按的普攻全被吃掉, 之后每一下万阙连衡普攻翻 2 颗。作者第 4 颗一翻就闪避/处决, 把第二下的收招打断,
    # 之后每下普攻都是 2 颗(5、6 一起, 7、8 一起), 两下就能按住出临寰宇。视频三次: 第 4 颗翻面 -> 出手 0.03 / 0.17 / 0.17s。
    # 10-06 实机旧版按固定时间: 第 2 颗(循环轴)/第 4 颗前 0.11s(启动轴)就闪了, 第二下的消耗被打断, 后面要多打几下(用户: "还是快了一点")
    XN2_TY_A_EVERY = 0.18
    XN2_TY_DODGE_COUNT = 4
    XN2_TY_DODGE_MIN = 2.50      # 进统御众机这么久之前不出手(万阙连衡出招动画里不会翻面, 防误读)
    XN2_TY_DODGE_CAP = 5.00      # 一直没数到 4 颗(读不准)也到这一刻出手。实机第 4 颗在进统御众机后 3.75~3.95s
    XN2_TY_PROMPT_KEEP = 3.00    # 处决提示在出手前这么久内见过, 出手那一刻就再确认一下, 还在就处决代替闪避
    # 照世心雕像(4K, hcenter): 8 颗的中心 x, 红菱形那一行 y, 上半身(亮白)那一行 y。取自 10-06 实机录屏(2560x1440 缩 720p)
    XN_STATUE_XS = (1647, 1719, 1794, 1866, 1938, 2013, 2085, 2160)
    XN_STATUE_Y = 1980
    XN_STATUE_UP_Y = 1953
    XN_STATUE_HW = 9
    XN_STATUE_RED = 0.08         # 红菱形占比(没翻 0.00, 翻了 0.10~0.55)
    XN_STATUE_GLOW = 0.30        # 上半身亮白占比(没翻 <= 0.12, 翻面那一刻 0.45~0.61, 翻完常亮 0.14~0.5)
    XN_STATUE_CONFIRM = 2
    XN2_DODGE_HOLD = 0.07        # 闪避 = 右键
    XN2_DODGE_TO_A = 0.12
    XN2_TY_CAP = 10.0            # 统御众机 13s; 一直没看到人像就到这一刻照按(实机打空要 5.1~5.3s 的普攻)
    XN2_HOLD_CAP = 1.20          # 人像出来后按住到 HUD 消失(临寰宇出手, 实测 0.40~0.45s)
    XN2_BLIND_HOLD = 2.00        # 没看到人像(撞上限/没认出统御众机)时按住试一次的上限
    XN2_RELEASE_AFTER_GONE = 0.30
    XN2_RETRIES = 2              # 按住没出(被打断) -> 普攻到人像再按, 最多这么多次
    XN2_RETRY_CAP = 3.00         # 补的那一轮普攻到人像的上限
    XN2_ANIM_MIN = 1.40          # 临寰宇藏 HUD ~2.0s
    XN2_ANIM_CAP = 4.00
    # 临寰宇演完后读 hsin_lib2(万阙垂天解锁)的上限。【认不出就不按 R】: 10-06 09:31 那圈照按, R 放成了借相(CD 1.5s, 心切回应世相)
    XN2_LIB2_CAP = 1.50
    XN2_LIB2_READS = 2
    # 万阙垂天之前协奏低于这个就照世相普攻补(人还贴着怪; 开完大离怪远了打不到 —— 心汐守实机 10-05 11:56)
    XN2_PRE_R2_CON = 0.80
    XN2_PRE_R2_CAP = 2.00
    # 变奏穗穗之前心协奏要真满(不满穗穗不是变奏进来, 循环轴第一格就没有濯雨时)
    XN2_CON_CAP = 3.00
    # 处决: 只按 F, 从第一下起等满 XN_BREAK_ANIM。
    # 【判据只认怪身上的 F 提示(屏幕中间 f_break >= 0.90, 不是拾取 F), 不认顶部谐度满(f_break_full)】:
    # 10-06 09:39 录屏顶部谐度满比 F 提示早 2.8s, 宏在只有顶部那个时按 F 是空按(倒计时没停), 白站 1.4s;
    # 真提示出来时正在按住重击, 处决没打。两份录屏 F 提示帧 0.91~0.98, 其余 <= 0.81
    XN_BREAK = True
    XN_BREAK_FROM = 0.80         # 进统御众机这么久之后才看(万阙连衡那一下的演出)
    XN_BREAK_CONFIRM = 2
    XN_BREAK_PRESSES = 3
    XN_BREAK_ANIM = 1.40         # 视频: 按 F 到恢复普攻 ~1.2s, 倒计时停了 ~1.0s
    XN_BREAK_CENTER_MIN = 0.90

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.opener_armed = True
        self.last_opener = -1
        self.macro_t0 = 0.0
        self.macro_marks = []
        self.cur = None
        self.holding_attack = False
        self.si_holding = False
        self.switch_press_at = 0.0
        self.lib_press_at = 0.0
        self.loop_count = 0
        self.su_qiang_at = -99.0       # 穗穗进濯雨时的时刻(醒春潮 / 变奏入场)
        self.su_no_qiang = False       # 醒春潮确定没开出来
        self.lei2_t0 = 0.0             # 雷主第二格到场时刻 / 大招演出时长(算游戏时间用)
        self.lei2_pause = 0.0
        self.xn_broke = False
        self.hud_seen_at = 0.0         # 最后一次读到队伍 HUD 在场的时刻(HUD_LOST_ABORT 用)
        self.hud_watch = False         # 宏跑着的时候才查 HUD 丢没丢
        self.drive_log_at = 0.0
        self.timeline_logged = True
        # reset_state() 只在 load_chars() 时跑, 而角色对象会被粘性复用 —— 这里也要启一次
        try:
            start_enable_watch(self.task, self.logger)
        except Exception:
            pass

    def reset_state(self):
        super().reset_state()
        self.opener_armed = True
        # 内置非治疗角色默认 True, 换类时会被打回, 所以在这里重申(这条轴不在切人时按处决)
        self.check_f_on_switch = False
        start_f_watch(self.task, self.logger)
        start_enable_watch(self.task, self.logger)

    # ==================== 队伍判定 ====================

    @property
    def is_in_xls(self) -> bool:
        """本队 = 心 + 雷主(Rover) + 穗穗。按类名判。"""
        members = 0
        for char in self.task.chars:
            if char and char.name in {'Rover', 'Suisui'}:
                members += 1
        return members == 2

    def teammate(self, name):
        for char in self.task.chars:
            if char is not None and char.name == name:
                return char
        return None

    def opener_pending(self):
        return self.opener_blocked_by() is None

    def opener_blocked_by(self):
        """启动轴不跑的原因; 返回 None 表示该跑。不查任何技能可用性(场下读数是旧的)。"""
        if not self.is_in_xls:
            return 'team is not hsin/rover/suisui'
        if not self.opener_armed:
            restarted = getattr(self.task, '_ww_task_restarted_at', -1)
            if restarted > self.last_opener:
                self.logger.info('auto combat 重开过 — 启动轴重新武装, 从头跑')
                self.opener_armed = True
                return None
            return 'already armed-down (ran once this combat)'
        f_press = getattr(self.task, '_f_last_press', -1)
        if f_press > self.last_opener:
            waited = time.time() - f_press
            delay = f_settings(self.task)[1]
            if waited < delay:
                return f'F pressed {waited:.2f}s ago, waiting {delay:.2f}s for the mobs'
            return None
        if self.last_opener >= 0 and time.time() - self.last_opener < self.OPENER_MIN_GAP:
            return f'ran {time.time() - self.last_opener:.1f}s ago (< {self.OPENER_MIN_GAP:.0f}s)'
        if not self.task.use_liberation:
            return 'task.use_liberation is off'
        return None


    # ==================== 宏原语(引擎) ====================

    def macro_wait(self, sec):
        """精确等待, 【不点击】。切成 0.1 秒一片, 片间检查任务是否被停用。"""
        if sec <= 0:
            self.task.executor.check_enabled(check_pause=False)
            return
        end = time.time() + sec
        while True:
            left = end - time.time()
            if left <= 0:
                return
            time.sleep(min(0.1, left))
            self.task.executor.check_enabled(check_pause=False)

    def wait_until_time(self, deadline):
        self.macro_wait(deadline - time.time())

    def macro_start(self):
        self.macro_t0 = time.time()
        self.macro_marks = []

    def macro_mark(self, name):
        self.macro_marks.append(f'{name}@{time.time() - self.macro_t0:.2f}')
        # 【看门狗】每一步都会打标记, 在这里顺手查: HUD 很久没出现 = 关卡结束/过场/窗口没了,
        # 再按下去就是在结算画面上乱按(景月守实机 2026-09-28 19:17 见过)。不读屏, 只比时间戳
        if self.hud_watch and time.time() - self.hud_seen_at > self.HUD_LOST_ABORT:
            self.hud_watch = False
            raise MacroBroken(f'队伍 HUD {time.time() - self.hud_seen_at:.1f}s 没出现(关卡结束/过场/窗口没了?)')

    def hud_ok(self):
        """队伍 HUD 在不在(读当前帧)。见到就记下时刻, 给看门狗用。"""
        ok = bool(self.task.in_team()[0])
        if ok:
            self.hud_seen_at = time.time()
        return ok

    def macro_timeline(self, since=0):
        return ' '.join(self.macro_marks[since:])

    def macro_spam(self, window, interval=None, tag='A'):
        """连点一个窗口。打出几段由 window 决定(动画期间的点击被丢掉, 连点保证总有一下落在动画刚结束时)。"""
        interval = self.A_INTERVAL if interval is None else interval
        start = time.time()
        n = 0
        cap = int(window / max(interval, 0.01)) + 2
        while time.time() - start < window and n < cap:
            self.click()
            n += 1
            remaining = window - (time.time() - start)
            if remaining <= 0:
                break
            # click 自己按住 A_TAP 秒, 不扣的话连点周期从 interval 变成 interval + A_TAP
            self.macro_wait(min(max(0.0, interval - self.A_TAP), remaining))
        self.macro_mark(f'{tag}(x{n})')
        return n

    def spam_key(self, send, window, interval=None, tag='key', poke=None, presses=None,
                 click_interval=None, stop_when=None):
        """在一个窗口里反复发同一个技能键, 用来盖住动画那一段。

        动画期间的按键是被丢掉的、不排队, 所以单发必丢 —— 这个形状在爱琳莫那条轴上
        踩到过六次, 症状统一是"那一步慢了"(要等整个动画演完才有第二次机会)。

        【必须在这个角色自己的回合里跑完, 不要跟切人并行】: 切人期间发出去的键会被
        游戏带过换人边界落在新角色身上。点击可以并行(quick_switch 的 click_during),
        技能键不行。唯一的例外是 switch_into_lib()。

        Args:
            poke: 发键期间要不要照常点普攻(默认不点)。
            click_interval: 点普攻的间隔, 默认 A_INTERVAL。给 A_INTERVAL_FAST
                就是"技能键按自己的节奏、普攻按加密节奏", 两条流互不影响。
            stop_when: 每发一次键之后调一次, 返回 True 就停。用在【多按一下会
                烧掉后面要用的充能】的地方 —— 一旦读到技能已经不可用就立刻收手。
                【会读屏, 别配太密的 interval】。
            presses: 只发这么多次, 均匀铺在窗口里。用在"连续点按两次E"那种
                【次数本身有意义】的地方 —— 连发会把两发挤成一发。
                【给了 presses 就由它说了算, window 只用来推间隔】: 否则
                window=0(要求两发贴着发)会在第一发之后就把循环停掉, 变成单发。
        """
        interval = self.KEY_INTERVAL if interval is None else interval
        poke = bool(poke)
        click_interval = self.A_INTERVAL if click_interval is None else click_interval
        if presses is not None and presses > 0:
            interval = max(interval, window / presses)
        start = time.time()
        n = 0
        clicks = 0
        next_click = 0.0
        while True:
            send()
            n += 1
            if stop_when is not None and stop_when():
                break
            if presses is not None:
                if n >= presses:
                    break
                left = interval
            else:
                left = window - (time.time() - start)
                if left <= 0:
                    break
            step_end = time.time() + min(interval, left)
            # 发键的节奏和点击的节奏各走各的 —— 挂在一起的话点击会被技能键的
            # 间隔卡住(爱琳莫那边 R 被 E2_POLL 卡住就是这个)
            while True:
                now = time.time()
                if now >= step_end:
                    break
                if poke and now >= next_click:
                    self.click()
                    clicks += 1
                    next_click = now + click_interval
                self.macro_wait(min(0.02, step_end - time.time()))
        # 【点击数也要打进去】: x{n} 只数了技能键, 看不出这段时间有没有在持续普攻。
        # 用户 2026-08-16 问过一次"E的期间也要一直普攻" —— 实际一直在点,
        # 只是日志里看不见。A x0 就是真的没点(poke=False 的那几格)
        self.macro_mark(f'{tag}(x{n},A x{clicks})')
        return n

    def game_foreground(self):
        try:
            return bool(self.task.executor.interaction.hwnd_window.is_foreground())
        except Exception:
            return False

    def attack_down(self, direct):
        """按下左键。direct = 走 SendInput(失败自动退回 PostMessage)。返回实际走没走 SendInput。"""
        if direct and send_input_left(False):
            self.si_holding = True
        else:
            direct = False
            self.task.mouse_down()
        self.holding_attack = True
        return direct

    def release_attack(self):
        # 【SendInput 按下的必须 SendInput 松开】: PostMessage 的 mouse_up 只进游戏窗口的消息队列,
        # 系统里那个左键会一直按着 —— 宏异常退出时整台电脑的左键都是按住的
        if self.si_holding:
            if not send_input_left(True):
                self.logger.warning('SendInput 左键松开没发出去 — 如果左键卡住, 手动点一下')
            self.si_holding = False
            self.holding_attack = False
        elif self.holding_attack:
            self.task.mouse_up()
            self.holding_attack = False

    def tap(self, hold=None):
        """点一下普攻, 【真的按住 hold 秒】。"""
        hold = self.A_TAP if hold is None else hold
        self.task.mouse_down()
        self.holding_attack = True
        try:
            self.macro_wait(hold)
        finally:
            self.task.mouse_up()
            self.holding_attack = False

    def click(self, *args, **kwargs):
        """本队里所有的 self.click() 都改成按住 A_TAP(BaseChar.click 强制 10ms, 等于没点)。不在本队走原版。"""
        if not self.is_in_xls:
            return super().click(*args, **kwargs)
        self.tap()

    def quick_switch(self, target, click_during=False, time_out=None, read_con=False, assume_con=False):
        """按数字键直切给指定角色(不走 switch_next_char 选人)。

        read_con: 按键之后读一次协奏决定按不按"带变奏"记账; assume_con: 不读屏直接按满协奏记。
        Returns: 是否真的切过去了。
        """
        if target is None:
            return False
        if target is self.cur:
            self.macro_mark(f'>{target.name[:3]}(already)')
            return True
        entry = time.time()
        time_out = self.SWITCH_TIME_OUT if time_out is None else time_out
        source = self.cur if self.cur is not None else self
        slot = target.index + 1
        self.switch_press_at = time.time()
        self.task.send_key(slot, down_time=self.SWITCH_KEY_DOWN_TIME)
        if assume_con:
            con_full = True
        elif read_con:
            # 不用 char.is_con_full(): 那层读到过一次满就一直缓存成满
            try:
                con_full = float(self.task.get_current_con()) >= 1.0
            except Exception:
                con_full = False
        else:
            con_full = False
        con_cost = time.time() - entry

        start = time.time()
        last = start
        next_click = 0.0
        trace = [] if self.TRACE_SWITCH else None
        team_size = len([c for c in self.task.chars if c is not None])
        untrusted_hits = 0
        clicks = 0
        while time.time() - start < time_out:
            now = time.time()
            if now - last >= self.SWITCH_KEY_INTERVAL:
                self.task.send_key(slot, down_time=self.SWITCH_KEY_DOWN_TIME)
                last = now
            if click_during and now >= next_click:
                self.click()
                clicks += 1
                next_click = now + self.A_INTERVAL
            self.task.next_frame()
            in_team, index, count = self.task.in_team()
            if in_team:
                self.hud_seen_at = time.time()
            hit = in_team and index == target.index
            trusted = in_team and count >= team_size
            untrusted_hits = untrusted_hits + 1 if (hit and not trusted) else 0
            if trace is not None:
                trace.append(f'{time.time() - start:.2f}:'
                             f'{(index if trusted else f"?{index}") if in_team else "x"}')
            if hit and (trusted or untrusted_hits >= self.UNTRUSTED_CONFIRM):
                self.handoff(source, target, con_full)
                self.macro_mark(f'>{target.name[:3]}{"^" if con_full else ""}'
                                f'({time.time() - entry:.2f}|con{con_cost:.2f}|A x{clicks})')
                if trace and time.time() - entry > 0.4:
                    self.logger.info(f'slow switch trace -> {target.name}: {" ".join(trace)}')
                return True
        # 一直是旧角色的 index = 游戏在拒绝切人; 带 ? 的都是目标 = count 判据挡住了; 全是 x = HUD 不在
        self.logger.warning(f'switch to {target.name} slot {slot} timed out '
                            f'after {time_out:.1f}s (stuck in an animation?)'
                            + (f' trace: {" ".join(trace)}' if trace else ''))
        self.macro_mark(f'>{target.name[:3]}FAIL')
        return False

    def handoff(self, from_char, to_char, con_full):
        """复刻 switch_next_char() 尾部那套交接记账。不补的话 get_current_char() 返回 None, 主循环当场崩。"""
        self.task.in_liberation = False
        from_char.switch_out(con_full=con_full)
        to_char.is_current_char = True
        to_char.has_intro = con_full
        to_char.has_sub_dps_intro = con_full and from_char.is_sub_dps
        to_char.last_switch_in_time = time.time()
        if con_full:
            now = time.time()
            self.task.add_freeze_duration(now, to_char.intro_motion_freeze_duration, -100)
            from_char.last_outro_time = now
        self.cur = to_char

    def switch_retry(self, target, tag, **kw):
        """quick_switch, 超时了先等 HUD 回来再切, 最多再试 SWITCH_RETRIES 次。只花时间。"""
        if self.quick_switch(target, **kw):
            return True
        for i in range(self.SWITCH_RETRIES):
            self.wait_hud_up(cap=2.0, tag=f'{tag}重切前HUD')
            self.macro_mark(f'{tag}切{target.name[:3]}重试#{i + 1}')
            kw2 = dict(kw)
            kw2['time_out'] = self.SWITCH_RETRY_TIME_OUT
            if self.quick_switch(target, **kw2):
                return True
        return False

    def wait_hud_back(self, tag='anim', time_out=None, min_gone=0.0, tail=0.0):
        """等演出结束(队伍 HUD 回来), 【期间一下都不点】。先确认消失过。

        min_gone: 从第一次读到消失起, 这么久之内读到的"回来"不认(演出中途 HUD 会闪一两帧)。
        回来要连读 HUD_BACK_CONFIRM 帧。
        """
        time_out = self.LIB_ANIM_TIME_OUT if time_out is None else time_out
        start = time.time()
        gone_at = None
        back_hits = 0
        back = False
        while time.time() - start < time_out:
            self.task.next_frame()
            if not self.hud_ok():
                if gone_at is None:
                    gone_at = time.time()
                back_hits = 0
            elif gone_at is not None:
                if time.time() - gone_at >= min_gone:
                    back_hits += 1
                    if back_hits >= self.HUD_BACK_CONFIRM:
                        back = True
                        break
            elif time.time() - start >= self.HUD_NO_ANIM_GRACE:
                back = True
                break
            self.macro_wait(0.01)
        if gone_at is not None:
            self.add_freeze_duration(gone_at, time.time() - gone_at)
        self.macro_mark(f'{tag}({"ok" if back else "timeout"},'
                        f'{"anim" if gone_at is not None else "NOANIM"},{time.time() - start:.2f}s)')
        self.macro_wait(tail)
        return back

    def wait_hud_up(self, cap=None, tag='HUD'):
        """等队伍 HUD 【现在】在场。按 R 之前用 —— HUD 本来就不在的时候判"演出开始了"是假成功。"""
        cap = self.HUD_UP_CAP if cap is None else cap
        start = time.time()
        while time.time() - start < cap:
            self.task.next_frame()
            if self.hud_ok():
                if time.time() - start > 0.05:
                    self.macro_mark(f'{tag}在场({time.time() - start:.2f}s)')
                return True
            self.macro_wait(0.02)
        self.macro_mark(f'{tag}一直不在({cap:.1f}s)')
        return False

    def watch_hud_gone(self, window, tag, poke_after=None):
        """在 window 里盯队伍 HUD 有没有连续消失(= 演出开始), 消失了立刻返回 True。

        poke_after: 过了这么久 HUD 还在就开始点普攻(这一下技能没出手, A 在攒资源)。None = 不点。
        """
        start = time.time()
        gone = clicks = 0
        next_click = 0.0
        while time.time() - start < window:
            self.task.next_frame()
            if not self.hud_ok():
                gone += 1
                if gone >= self.LIB_GONE_CONFIRM:
                    self.macro_mark(f'{tag}(出手,{time.time() - start:.2f}s,A x{clicks})')
                    return True
            else:
                gone = 0
                now = time.time()
                if poke_after is not None and now - start >= poke_after and now >= next_click:
                    self.tap()
                    clicks += 1
                    next_click = time.time() + self.A_INTERVAL
            self.macro_wait(0.02)
        self.macro_mark(f'{tag}(没出,A x{clicks})')
        return False

    def on_field_char(self, time_out=None):
        """现在场上是谁 —— 只在拿不到入口角色时才用(开局 HUD 渐入时 in_team() 会说谎, 要 count 达标)。"""
        time_out = self.FIELD_SETTLE_TIME_OUT if time_out is None else time_out
        expected = len([c for c in self.task.chars if c is not None])
        end = time.time() + time_out
        while True:
            self.task.next_frame()
            in_team, index, count = self.task.in_team()
            if in_team:
                self.hud_seen_at = time.time()
            if in_team and count >= expected:
                for char in self.task.chars:
                    if char is not None and char.index == index:
                        return char
                return None
            if time.time() >= end:
                self.logger.warning(f'team HUD never settled in {time_out:.1f}s '
                                    f'(in_team={in_team} index={index} count={count} '
                                    f'expected={expected}), cannot tell who is on field')
                return None
            self.macro_wait(0.03)

    def mark_busy(self, busy):
        """F 键监视线程靠它区分"战斗中手动处决"和"重开副本"。"""
        self.task._ww_macro_busy = busy
        self.task._three_fire_macro_busy = busy

    def need(self, ok, what):
        if not ok:
            raise MacroBroken(what)

    def press_key_until_cd(self, send, available, cap, tag, ready_grace=0.15, poke=False):
        """一直按某个技能键到它进 CD。返回放出去了没有(本来就在 CD 上返回 False)。

        【先见过"亮"才认"暗"】: 刚切人那几帧技能栏还是上一个人的, 读到的是上一个人的 CD。
        """
        start = time.time()
        n = live = clicks = 0
        seen_ready = False
        next_click = 0.0
        while time.time() - start < cap:
            self.task.next_frame()
            hud = bool(self.hud_ok())
            if hud:
                if available():
                    seen_ready = True
                elif seen_ready and live > 0:
                    self.macro_mark(f'{tag}_ok(x{n},A x{clicks},{time.time() - start:.2f}s)')
                    return True
                elif not seen_ready and time.time() - start >= ready_grace:
                    self.macro_mark(f'{tag}_没见过亮(x{n},{time.time() - start:.2f}s)')
                    return False
            send()
            n += 1
            if hud:
                live += 1
            step_end = time.time() + self.E_RESEND_STEP
            while True:
                now = time.time()
                if now >= step_end:
                    break
                if poke and now >= next_click:
                    self.click()
                    clicks += 1
                    next_click = now + self.A_INTERVAL
                self.macro_wait(min(0.02, step_end - now))
        self.macro_mark(f'{tag}_CD?(x{n},seen{int(seen_ready)},{cap:.1f}s)')
        self.logger.info(f'{tag}: never read as on-cooldown after {n} presses (seen ready={seen_ready})')
        return False

    def press_res_until_cd(self, char, cap, tag, ready_grace=None, poke=False):
        ready_grace = self.SKILL_BAR_SETTLE if ready_grace is None else ready_grace
        return self.press_key_until_cd(char.send_resonance_key, char.resonance_available, cap, tag,
                                       ready_grace=ready_grace, poke=poke)

    def fire_r(self, char, tag, window):
        """发大招到队伍 HUD【连续】消失 LIB_GONE_CONFIRM 帧。返回放出去没有。

        发键之前先等 HUD 在场(HUD 本来就不在会假成功)。确认期间继续按 R 没有副作用 —— 演出里的按键被丢掉。
        """
        self.wait_hud_up(tag=f'{tag}前HUD')
        start = time.time()
        self.lib_press_at = start
        n = gone = 0
        fired = False
        while time.time() - start < window:
            char.send_liberation_key()
            n += 1
            self.task.next_frame()
            if not self.hud_ok():
                gone += 1
                if gone >= self.LIB_GONE_CONFIRM:
                    fired = True
                    break
            else:
                gone = 0
            self.macro_wait(self.LIB_KEY_INTERVAL)
        self.task.skip_combat_check = True
        if fired:
            char.record_liberation_use()
            self.macro_mark(f'{tag}_fired(x{n},{time.time() - start:.2f}s)')
            return True
        self.macro_mark(f'{tag}_NOFIRE(x{n})')
        try:
            lit = bool(char.liberation_available())
        except Exception:
            lit = 'err'
        # lit=True: 键被上一个动作吞了; lit=False: 能量不够
        self.logger.warning(f'{tag}: {char.name} liberation never started an animation '
                            f'after {n} presses (icon lit={lit})')
        return False

    def lib_ready_reads(self, char, frames):
        """HUD 在场时连续 frames 帧读到 char 的 R 可用。HUD 不在的帧不算, 最多读 frames*3 帧。"""
        hits = 0
        for _ in range(frames * 3):
            self.task.next_frame()
            if self.hud_ok():
                try:
                    ready = bool(char.liberation_available())
                except Exception:
                    ready = False
                if not ready:
                    return False
                hits += 1
                if hits >= frames:
                    return True
            self.macro_wait(0.02)
        return False

    def ensure_r(self, char, tag, window, cap, build):
        """R 一定要放出来。读 R 亮 -> 按; 亮着却没放出去就再按, 最多 R_TRIES 次;
        不亮 -> build(轮次) 攒一小段再读, 每 R_BLIND_EVERY 轮盲按一次防读数不准。上限 cap 只防打不到怪。
        """
        start = time.time()
        tries = rounds = 0
        while time.time() - start < cap:
            if self.lib_ready_reads(char, 2):
                tries += 1
                if self.fire_r(char, f'{tag}R' if tries == 1 else f'{tag}R重按#{tries - 1}', window):
                    if rounds:
                        self.logger.info(f'{tag}: {char.name} R 攒了 {time.time() - start:.1f}s 能量才放出去')
                    return True
                if tries >= self.R_TRIES:
                    break
                continue
            rounds += 1
            if rounds == 1:
                self.macro_mark(f'{tag}R没亮(攒能量)')
            build(rounds)
            if rounds % self.R_BLIND_EVERY == 0 and not self.lib_ready_reads(char, 2) and \
                    self.fire_r(char, f'{tag}R盲按#{rounds}', self.R_BLIND_WINDOW):
                return True
        self.logger.warning(f'{tag}: {char.name} 的 R 保底 {time.time() - start:.1f}s 还是没放出去 '
                            f'(亮了按 {tries} 次, 攒能量 {rounds} 轮), 不放了')
        return False

    def read_cd(self, name='resonance', char=None):
        """读技能框里的 CD 数字(秒)。不在 CD / 读不到都返回 0(框架没 CD 时返回负数, 截成 0)。"""
        try:
            index = None if char is None else char.index
            return max(0.0, float(self.task.get_cd(name, index)))
        except Exception:
            return 0.0

    def read_con(self, want, settle=None, click=False, tag=None):
        """读协奏: 自己刷帧、给结算留时间, 连着几帧达到 want 就立刻返回。返回期间读到的最大值。"""
        settle = 0.50 if settle is None else settle
        start = time.time()
        best = 0.0
        hits = 0
        next_click = 0.0
        while True:
            now = time.time()
            if click and now >= next_click:
                self.click()
                next_click = now + self.A_INTERVAL
            self.task.next_frame()
            self.hud_ok()
            try:
                con = float(self.task.get_current_con())
            except Exception:
                con = 0.0
            best = max(best, con)
            hits = hits + 1 if con >= want else 0
            if hits >= self.CON_FULL_CONFIRM or time.time() - start >= settle:
                break
            self.macro_wait(self.CON_POLL)
        if tag:
            self.macro_mark(f'{tag}(con{best:.2f},{time.time() - start:.2f}s)')
        return best

    def wait_con_full(self, who, cap, tag, poke=True):
        """边打边等协奏真满(连着几帧)。返回满没满。"""
        start = time.time()
        samples = []
        hits = 0
        next_click = 0.0
        while time.time() - start < cap:
            now = time.time()
            if poke and now >= next_click:
                self.click()
                next_click = now + self.A_INTERVAL
            self.task.next_frame()
            self.hud_ok()
            try:
                con = float(self.task.get_current_con())
            except Exception:
                con = 0.0
            if len(samples) < self.CON_SAMPLE_MAX:
                samples.append(f'{time.time() - start:.2f}:{con:.2f}')
            hits = hits + 1 if con >= self.CON_ENOUGH else 0
            if hits >= self.CON_FULL_CONFIRM:
                self.macro_mark(f'{tag}(满,{time.time() - start:.2f}s)')
                return True
            self.macro_wait(self.CON_POLL)
        self.macro_mark(f'{tag}(没满,{time.time() - start:.2f}s)')
        self.logger.info(f'{tag}: {who} 协奏 {" ".join(samples)}')
        return False

    @staticmethod
    def glyph_vec(a):
        v = a.astype(np.float32).flatten()
        v = v - v.mean()
        n = float(np.linalg.norm(v))
        return v / n if n > 0 else v


    def dodge(self, tag):
        """闪避(右键)。"""
        self.task.mouse_down(key='right')
        try:
            self.macro_wait(self.XN2_DODGE_HOLD)
        finally:
            self.task.mouse_up(key='right')
        self.macro_mark(f'{tag}闪避')

    def break_prompt_reads(self, frames):
        """最多读 frames 帧, 有一帧读到怪身上的处决提示就返回 True。"""
        for _ in range(frames):
            self.task.next_frame()
            if self.break_prompt():
                return True
        return False

    def break_prompt(self):
        """怪身上有处决提示(屏幕中间那个 F, 排除拾取 F)。读当前帧。不看顶部的谐度满(f_break_full): 那个比提示早好几秒, 那时按 F 是空按。"""
        task = self.task
        try:
            hit = task.find_one('f_break', box=task.box_of_screen(0.2, 0.2, 0.75, 0.8, hcenter=True, vcenter=True),
                                target_height=720, threshold=self.XN_BREAK_CENTER_MIN)
            return bool(hit) and not task.is_pick_f()
        except Exception as e:
            self.logger.info(f'处决提示读失败 {e}')
            return False

    # ==================== 穗穗 ====================

    def sui_e1_lit(self):
        """穗穗的强化E(醒春潮)就绪没有 —— 读的是 E 图标那张强化态模板。"""
        return bool(self.task.find_one(Labels.suisui_e1, threshold=self.SUI_E1_THRESHOLD))

    def fill_sui_e1(self, char, tag, cap=None):
        """强化E 图标不亮(= 水云息没满)就接着点普攻攒, 亮了立刻停手。返回亮了没有。"""
        cap = self.SUI_E1_FILL if cap is None else cap
        start = time.time()
        n = 0
        next_click = 0.0
        while time.time() - start < cap:
            self.task.next_frame()
            self.hud_ok()                   # 喂看门狗: 这一格最长 SU_E1_MUST_CAP, 比 HUD_LOST_ABORT 长
            if self.sui_e1_lit():
                if n:
                    self.macro_mark(f'{tag}攒回路({time.time() - start:.2f}s,A x{n})')
                return True
            now = time.time()
            if now >= next_click:
                self.click()
                n += 1
                next_click = now + self.SUI_E1_FILL_INTERVAL
            self.macro_wait(0.02)
        self.macro_mark(f'{tag}攒回路(CAP,A x{n},{cap:.1f}s)')
        return False

    def cast_sui_e1(self, char, tag):
        """按到 suisui_e1 这张图消失 —— 消失才等于强化E(醒春潮)真的放出去了。

        【为什么要连按】: 这一格紧跟在切人后面, 入场动画会把单发吞掉(跟 fire_r 一个道理)。
        【连按在这里是安全的】: 图标一消失就停手, 多按的那几下落不到第二次 E 上。
        """
        start = time.time()
        n = 0
        while time.time() - start < self.SUI_E1_CAST_CAP:
            char.send_resonance_key(down_time=self.M_E_KEY_DOWN)
            n += 1
            self.macro_wait(self.SUI_E1_KEY_INTERVAL)
            self.task.next_frame()
            if not self.sui_e1_lit():
                self.macro_mark(f'{tag}强化E出手(x{n},{time.time() - start:.2f}s)')
                return True
        self.macro_mark(f'{tag}强化E没出手(x{n},CAP)')
        self.logger.warning(f'{tag}: 按了 {n} 下 suisui_e1 还亮着 — 这几下多半被吞了'
                            f'(入场动画/硬直?), 这一轮穗穗进不了濯雨时')
        return False

    def forte3_full(self):
        """穗穗的三段回路(芳菲信 600)满没满。

        【这几帧连着读完, 中间不做别的】—— 靠外层循环去凑命中次数会白白多等一轮。
        HUD 被演出盖住时读不到, 返回 False 落在"还没满"这一侧, 方向是安全的
        (顶多多点几下普攻, 不会误判成满就去放大招)。
        """
        for i in range(self.FORTE3_CONFIRM):
            if not self.task.find_one(Labels.suisui_forte3, threshold=self.FORTE3_THRESHOLD):
                return False
            if i + 1 < self.FORTE3_CONFIRM:
                self.task.next_frame()   # 换一帧再读, 否则两次读的是同一张图
        return True

    def wait_forte3(self, tag, cap=None, su=None):
        """穗穗大招前的保底: 三段回路没满就接着点普攻, 满了立刻停手。返回满了没有。
        su: 打了 SU2_E_RESCUE_AT 秒还没满、E 好了就补一个 E(濯雨时的 E 第36F 给 100 芳菲信), 只补一次。
        上限 cap 到了【照放不误】。
        """
        cap = self.FORTE3_WAIT if cap is None else cap
        if not self.FORTE3_GATE:
            return True
        start = time.time()
        n = 0
        next_click = 0.0
        e_used = su is None
        while time.time() - start < cap:
            self.hud_ok()                   # 喂看门狗: 上限可能比 HUD_LOST_ABORT 长
            if not e_used and time.time() - start >= self.SU2_E_RESCUE_AT:
                e_used = True
                try:
                    ready = bool(su.resonance_available())
                except Exception:
                    ready = False
                if ready:
                    self.spam_key(su.send_resonance_key, 0.20, tag=f'{tag}补E(+100芳菲信)', presses=2)
                    su.record_resonance_use()
                    continue
            # 【先点再读】(2026-09-22 用户: "穗穗最后回路没满要补的时候, 经常卡顿一下才A")。
            # forte3_full() 要连读 FORTE3_CONFIRM 帧, 一帧 next_frame 就几十毫秒 ——
            # 把读屏放在点击前面, 进这一格的第一下 A 就被硬生生压后, 手感上就是"卡一下"。
            # 判据晚一轮(0.02s)成立没有任何代价, 第一下 A 晚 60ms 是看得出来的
            now = time.time()
            if now >= next_click:
                self.click()
                n += 1
                next_click = now + self.A_INTERVAL
            if self.forte3_full():
                waited = time.time() - start
                self.macro_mark(f'{tag}满({waited:.2f}s,A x{n})')
                if n <= 1 and waited < self.FORTE3_SUSPECT:
                    # 【一下没点就"满"了, 十有八九是误判】。穗穗有两个形态两条【不同】的
                    # 资源条: 浣尘时显示【水云息】, 濯雨时才是【芳菲信】; 而 suisui_forte3
                    # 匹配的是芳菲信满档那张图 —— 她要是没进濯雨时(E 被吞, 醒春潮没放出来),
                    # 读的就是水云息那条条, 会误命中。
                    # 实机对照: 启动轮 满(1.44s,A x11) / (1.88s,A x14), 循环轮 满(0.03s,A x0)
                    self.logger.info(
                        f'{tag}: {waited:.2f}s 一下没点就读到"回路满"(循环轮常见: 前面上场已经攒满); '
                        f'要是这一轮秧秧没吃到烟岚, 再怀疑穗穗没进濯雨时、读到的是水云息那条')
                return True
            self.macro_wait(0.02)
        self.macro_mark(f'{tag}没满(CAP,A x{n},{cap:.1f}s)')
        self.logger.warning(f'{tag}: 三段回路 {cap:.1f}s 没攒满(点了 {n} 下 A), '
                            f'照放(濯雨时过了 / 打不到怪)')
        return False


    def seg_su_open(self, su, lei, tag, must=True):
        """穗穗·启动格: 3A 攒满水云息 -> 醒春潮(进濯雨时 15s) -> 切雷主。
        【醒春潮必须开出来才切】(心卜穗用户 10-06): 没进濯雨时, 穗穗第二格的芳菲信根本攒不起来。
        图标不亮就一直 A(开局怪还没站稳时普攻打不中), 按了图标还亮(被吞/被打断)就回去接着 A 再按, 上限 SU_E1_MUST_CAP。
        must=False(循环轴兜底, 穗穗可能还在濯雨时 —— 那样图标永远不亮): 短上限, 不亮照按 E 走人。"""
        self.su_qiang_at = -99.0
        self.su_no_qiang = False
        if self.cur is not su:
            self.need(self.switch_retry(su, f'{tag}切穗穗'), 'opener: switch to suisui')
        cap = self.SU_E1_MUST_CAP if must else self.SUI_E1_FILL
        start = time.time()
        tries = 0
        while time.time() - start < cap:
            if not self.fill_sui_e1(su, tag, cap=cap - (time.time() - start)):
                break
            tries += 1
            if self.cast_sui_e1(su, tag):
                self.su_qiang_at = time.time()
                break
            self.macro_mark(f'{tag}醒春潮按了没出(#{tries}, 接着A再按)')
        if self.su_qiang_at < 0:
            if must:
                self.su_no_qiang = True
                self.logger.warning(f'{tag}: 醒春潮 {cap:.0f}s 都没开出来(普攻打不到怪?), 照常切雷主 —— 穗穗第二格芳菲信攒不满')
            else:
                self.press_res_until_cd(su, self.SU_L_E_CAP, tag=f'{tag}E(醒春潮没亮)')
        su.record_resonance_use()
        self.need(self.switch_retry(lei, f'{tag}切雷主'), 'suisui -> rover')

    def seg_su_loop(self, su, lei, tag):
        """穗穗·循环格(心变奏进来, 变奏直接给 15s 濯雨时): E -> 3A -> 第三段时切雷主。"""
        arrived = getattr(su, 'last_switch_in_time', 0.0) or 0.0
        # has_intro 是上一圈交棒时记的; 宏散过/框架隔了很久才调进来的话不作数
        if self.cur is not su or not su.has_intro or time.time() - arrived > self.SU_L_INTRO_FRESH:
            # 变奏进来但隔久了: 濯雨时多半还在(醒春潮图标不会亮), 短上限; 不是变奏进来的: 醒春潮必须开出来
            still = self.cur is su and su.has_intro and time.time() - arrived < self.SU_QIANG_DUR - 4.0
            self.macro_mark(f'{tag}穗穗不是刚变奏进来的(走启动格{",濯雨时多半还在" if still else ""})')
            self.seg_su_open(su, lei, tag, must=not still)
            if still and self.su_qiang_at < 0:
                self.su_qiang_at = arrived
            return
        self.su_qiang_at = arrived          # 变奏入场第1F 给 15s 濯雨时
        self.su_no_qiang = False
        # 变奏入场里按的 E 被丢, 一直按到进 CD
        self.press_res_until_cd(su, self.SU_L_E_CAP, tag=f'{tag}E', ready_grace=0.6)
        su.record_resonance_use()
        self.macro_spam(self.SU_L_3A, self.SU_L_A_EVERY, tag=f'{tag}3A')
        self.wait_until_time(arrived + self.SU_L_MIN_FIELD)
        self.need(self.switch_retry(lei, f'{tag}切雷主'), 'suisui -> rover')

    def seg_su2(self, lei, tag):
        """穗穗·第二格(雷主第一格切回来): A 到芳菲信满 -> Q -> R -> 演完 -> 协奏满 -> 变奏雷主。"""
        su = self.cur
        if self.su_no_qiang:
            cap = 0.0                  # 醒春潮没开出来, 不在濯雨时: 普攻攒不出芳菲信, 不白打
            self.macro_mark(f'{tag}不在濯雨时(醒春潮没开出来)')
        elif self.su_qiang_at > 0:
            left = self.su_qiang_at + self.SU_QIANG_DUR - time.time()
            cap = max(self.SU2_A_MIN, min(self.SU2_MUST_CAP, left + self.SU_QIANG_GRACE))
            self.macro_mark(f'{tag}濯雨时还剩{left:.1f}s(最多等{cap:.1f}s)')
        else:
            cap = self.SU2_MUST_CAP    # 醒春潮没认出来按的, 不知道濯雨时从哪一刻算
        if cap > 0:
            self.wait_forte3(f'{tag}芳菲信', cap=cap, su=su)
        self.su_con_before_r(tag)
        self.spam_key(su.send_echo_key, self.SU_Q_WINDOW, tag=f'{tag}Q', presses=2)
        su.record_echo_use()
        # 循环轴这里 R 常常还差零点几秒转好(视频), ensure_r 边 A 边等
        if self.ensure_r(su, tag, self.SU_R_WINDOW, self.SU_R_CAP,
                         lambda rounds: self.macro_spam(self.R_BUILD_SLICE, tag=f'{tag}攒能量#{rounds}')):
            self.wait_hud_back(tag=f'{tag}R演出', min_gone=self.SU_R_ANIM_MIN, time_out=self.SU_R_ANIM_CAP)
        full = self.read_con(1.0, settle=0.15) >= 1.0 or self.wait_con_full('穗穗', self.SU_CON_CAP, tag=f'{tag}协奏')
        if not full:
            self.logger.warning(f'{tag}: 穗穗协奏没满就切雷主 —— 雷主没有变奏(心的导电加成没了), 穗穗不跳延奏(这一圈没有翾舞)')
        self.need(self.switch_retry(lei, f'{tag}切雷主', assume_con=full), 'suisui -> rover')

    def su_con_before_r(self, tag):
        """穗穗大招前协奏不到 SU_R_CON_MIN 就点普攻补到够(大招只回 20)。上限 SU_R_CON_CAP, 濯雨时快结束了就停。"""
        con = self.read_con(self.SU_R_CON_MIN, settle=0.15)
        if con >= self.SU_R_CON_MIN:
            self.macro_mark(f'{tag}大招前协奏{con:.2f}')
            return
        start = time.time()
        deadline = start + self.SU_R_CON_CAP
        why = 'cap'
        if self.su_qiang_at > 0:
            qiang_end = self.su_qiang_at + self.SU_QIANG_DUR - self.SU_R_QIANG_MARGIN
            if qiang_end < deadline:
                deadline = qiang_end
                why = '濯雨时快结束'
        taps = 0
        samples = [f'0:{con:.2f}']
        while time.time() < deadline:
            self.tap()
            taps += 1
            self.macro_wait(max(0.0, self.A_INTERVAL - self.A_TAP))
            con = self.read_con(self.SU_R_CON_MIN, settle=0.03)
            if len(samples) < 20:
                samples.append(f'{time.time() - start:.2f}:{con:.2f}')
            if con >= self.SU_R_CON_MIN:
                why = 'ok'
                break
        self.macro_mark(f'{tag}大招前补协奏({con:.2f},A x{taps},{time.time() - start:.2f}s)')
        if why != 'ok':
            self.logger.warning(f'{tag}: 大招前协奏只补到 {con:.2f}({why}), 放完多半不满, 后面再补 — {" ".join(samples)}')

    # ==================== 雷主 ====================

    def lei_ready_white(self):
        """回路条右边 [E] 小框的白字占比(电涌满了才亮)。读当前帧。"""
        box = self.task.box_of_screen_scaled(3840, 2160, *self.LEI_READY_BOX, hcenter=True)
        return float(self.task.calculate_color_percentage(forte_white_color, box))

    def lei_echo_white(self):
        """雷主 Q(声骸)图标的白字占比: 地面亮着, 人在空中整个变灰。读当前帧。"""
        return float(self.task.calculate_color_percentage(text_white_color, self.task.get_box_by_name('box_echo')))

    def lei_ready_reads(self, frames):
        """HUD 在场时连着 frames 帧读到 [E] 小框亮(电涌满)。HUD 不在的帧、整屏白闪的帧不算, 最多读 frames*3 帧。"""
        hits = 0
        for _ in range(frames * 3):
            self.task.next_frame()
            if self.hud_ok():
                try:
                    w = self.lei_ready_white()
                except Exception:
                    return False
                if w >= self.LEI_READY_MAX:
                    continue
                if w <= self.LEI_READY_MIN:
                    return False
                hits += 1
                if hits >= frames:
                    return True
        return False

    def lei_wait_ready(self, deadline, tag):
        """一直点 A 到 [E] 小框亮(电涌满, 连读 LEI_READY_CONFIRM 帧)。到 deadline 没亮返回 False。"""
        start = time.time()
        taps = hits = 0
        next_tap = 0.0
        trace = []
        while True:
            now = time.time()
            if now >= next_tap:
                self.tap()
                taps += 1
                next_tap = time.time() + max(0.0, self.LEI2_A_EVERY - self.A_TAP)
            self.task.next_frame()
            if self.hud_ok():
                try:
                    w = self.lei_ready_white()
                except Exception as e:
                    self.logger.info(f'lei_ready_white probe failed ({e})')
                    w = -1.0
                if len(trace) < 40:
                    trace.append(f'{time.time() - start:.2f}:{w:.2f}')
                hits = hits + 1 if self.LEI_READY_MIN < w < self.LEI_READY_MAX else 0
                if hits >= self.LEI_READY_CONFIRM:
                    self.macro_mark(f'{tag}电涌满(A x{taps},{time.time() - start:.2f}s)')
                    return True
            if time.time() >= deadline:
                break
            self.macro_wait(0.01)
        self.macro_mark(f'{tag}小框没亮(A x{taps},{time.time() - start:.2f}s)')
        self.logger.info(f'{tag}: [E] 小框白字占比 — {" ".join(trace)}')
        return False

    def lei_overload(self, lei, arrived, tag):
        """点按 E 到进 CD(超负荷, 只短按), CD > LEI_E_CD_MIN 才算超负荷出去了(雷引 CD 才 10s)。
        没认出来(按出来的是雷引 / 被吞 / CD 读不准): 接着 A 到小框亮再按, 一共 LEI_E_TRIES 回。
        超负荷之后 E 在 CD 上, 多按的几下是空操作。"""
        for k in range(self.LEI_E_TRIES):
            if k > 0:
                self.lei_wait_ready(time.time() + self.LEI_E_RETRY_A, f'{tag}补电涌#{k}')
            self.press_res_until_cd(lei, self.LEI_E_CAP, tag=f'{tag}E#{k + 1}', ready_grace=0.30)
            cd = self.read_cd('resonance')
            if cd >= self.LEI_E_CD_MIN:
                lei.record_resonance_use()
                self.macro_mark(f'{tag}超负荷出手(#{k + 1},CD{cd:.1f},到场{time.time() - arrived:.2f}s)')
                return True
            self.macro_mark(f'{tag}E#{k + 1}没认出超负荷(CD{cd:.1f})')
        self.logger.warning(f'{tag}: 按了 {self.LEI_E_TRIES} 回 E 都没认出超负荷(电涌没满? CD 读不准?), 照常开 R')
        return False

    def lei1_cast_e(self, lei, tag):
        """第一格的 E(雷引): 按到进 CD 为止(期间点 A)。【读到 [E] 小框亮就立刻停手】: 雷引打中也加电涌,
        电涌一满 E 就换成超负荷、图标又亮了, 再按就把第二格要用的超负荷放掉了(CD 25s)。返回放出去没有。"""
        start = time.time()
        n = clicks = 0
        next_click = 0.0
        seen_ready = False
        why = 'cap'
        while time.time() - start < self.LEI1_E_CAP:
            self.task.next_frame()
            if self.hud_ok():
                try:
                    full = self.LEI_READY_MIN < self.lei_ready_white() < self.LEI_READY_MAX
                except Exception:
                    full = False
                if full and n > 0:
                    why = 'full'
                    break
                if lei.resonance_available():
                    seen_ready = True
                elif seen_ready and n > 0:
                    why = 'cd'
                    break
            lei.send_resonance_key()
            n += 1
            step_end = time.time() + self.E_RESEND_STEP
            while time.time() < step_end:
                if time.time() >= next_click:
                    self.click()
                    clicks += 1
                    next_click = time.time() + self.A_INTERVAL
                self.macro_wait(min(0.02, max(0.0, step_end - time.time())))
        self.macro_mark(f'{tag}E({ {"cd": "进CD", "full": "电涌满了停手", "cap": "没判到进CD"}[why]},x{n},A x{clicks},{time.time() - start:.2f}s)')
        if why != 'cap':
            lei.record_resonance_use()
        return why != 'cap'

    def seg_lei1(self, su, tag):
        """雷主·第一格(普通切人进来): E(雷引, 把人拉上去) -> 一直点 A(离地后第一下就是下落) -> 落地 -> 切穗穗。
        落地 = Q 图标 白 -> 灰(离地) -> 白, 各连读 LEI1_ECHO_CONFIRM 帧; 读不出来就 E 后 LEI1_BLIND 秒切。"""
        lei = self.cur
        if self.lei_ready_reads(self.LEI1_FULL_READS):
            # 电涌已经满了: 这时按 E 放的是超负荷, 第二格就没得放了(CD 25s)。只打普攻, 按时间切
            self.macro_spam(self.LEI1_BLIND, self.LEI1_A_EVERY, tag=f'{tag}电涌已满(不按E)A')
            self.logger.warning(f'{tag}: 雷主第一格上场电涌就是满的, 没放雷引(免得把超负荷用掉)')
            self.need(self.switch_retry(su, f'{tag}切穗穗', click_during=True, time_out=self.LEI1_SWITCH_TIME_OUT),
                      'rover -> suisui')
            return
        self.lei1_cast_e(lei, tag)
        e_at = time.time()
        taps = g_hits = a_hits = 0
        next_tap = 0.0
        seen_ground = False
        air_at = None
        why = 'cap'
        trace = []
        while True:
            now = time.time()
            if now >= next_tap:
                self.tap()
                taps += 1
                next_tap = time.time() + max(0.0, self.LEI1_A_EVERY - self.A_TAP)
            self.task.next_frame()
            if self.hud_ok():
                try:
                    w = self.lei_echo_white()
                except Exception as e:
                    self.logger.info(f'lei_echo_white probe failed ({e})')
                    w = -1.0
                if len(trace) < 40:
                    trace.append(f'{time.time() - e_at:.2f}:{w:.2f}')
                ground = w >= self.LEI1_ECHO_WHITE
                g_hits = g_hits + 1 if ground else 0
                a_hits = a_hits + 1 if (w >= 0 and not ground) else 0
                if g_hits >= self.LEI1_ECHO_CONFIRM:
                    seen_ground = True
                if air_at is None and seen_ground and a_hits >= self.LEI1_ECHO_CONFIRM:
                    air_at = time.time()
                    self.macro_mark(f'{tag}离地(E后{air_at - e_at:.2f}s)')
                if air_at is not None and g_hits >= self.LEI1_ECHO_CONFIRM:
                    why = 'landed'
            el = time.time() - e_at
            if why == 'landed' and el >= self.LEI1_MIN_AFTER_E:
                break
            if air_at is None and el >= self.LEI1_AIR_BY and el >= self.LEI1_BLIND:
                why = 'blind'
                break
            if el >= self.LEI1_CAP:
                break
            self.macro_wait(0.01)
        el = time.time() - e_at
        self.macro_mark(f'{tag}{ {"landed": "落地", "blind": "读不出离地", "cap": "没读到落地"}[why]}(E后{el:.2f}s,A x{taps})')
        if why != 'landed':
            self.logger.info(f'{tag}: Q 图标白字占比(E 后) — {" ".join(trace)}')
        self.need(self.switch_retry(su, f'{tag}切穗穗', click_during=True, time_out=self.LEI1_SWITCH_TIME_OUT),
                  'rover -> suisui')

    def seg_lei2(self, tag):
        """雷主·第二格(穗穗大招演完变奏进来): Q -> A 到电涌满 -> 点按 E(超负荷) -> 连按 R -> 演完 -> 等翾舞 -> 协奏满 -> 变奏心。"""
        lei = self.cur
        arrived = getattr(lei, 'last_switch_in_time', 0.0) or time.time()
        self.lei2_t0 = arrived
        self.lei2_pause = 0.0
        if not lei.has_intro:
            self.macro_mark(f'{tag}雷主不是变奏进来的(心的导电加成没了)')
        self.wait_until_time(arrived + self.LEI2_A_FROM)
        self.tap()
        self.wait_until_time(arrived + self.LEI2_Q_AT)
        self.spam_key(lei.send_echo_key, self.LEI2_Q_WINDOW, tag=f'{tag}Q', presses=2)
        lei.record_echo_use()
        self.lei_wait_ready(arrived + self.LEI2_READY_CAP, tag)
        self.lei_overload(lei, arrived, tag)
        if self.ensure_r(lei, tag, self.LEI_R_WINDOW, self.LEI_R_CAP,
                         lambda rounds: self.macro_spam(self.R_BUILD_SLICE, tag=f'{tag}攒能量#{rounds}')):
            fire_t = time.time()
            self.wait_hud_back(tag=f'{tag}R演出', min_gone=self.LEI_R_ANIM_MIN, time_out=self.LEI_R_ANIM_CAP)
            self.lei2_pause = time.time() - fire_t
        # 第一次翾舞那一刻雷主要在场(他变奏心才把烟岚交给心); 大招演出停游戏时钟, 不算
        game = time.time() - arrived - self.lei2_pause
        if game < self.LEI2_LEAVE_MIN:
            self.macro_spam(self.LEI2_LEAVE_MIN - game, self.LEI2_A_EVERY, tag=f'{tag}等翾舞A')
        full = self.read_con(1.0, settle=0.15) >= 1.0 or self.wait_con_full('雷主', self.LEI_CON_CAP, tag=f'{tag}协奏')
        self.macro_mark(f'{tag}雷主到场->变奏心 游戏时间{time.time() - arrived - self.lei2_pause:.2f}s')
        if not full:
            self.logger.warning(f'{tag}: 雷主协奏没满就切心 —— 心没有变奏(少 60 应世心), 雷主不放延奏(心没有电髓)')
        self.need(self.switch_retry(self, f'{tag}切心', assume_con=full), 'rover -> hsin')

    # ==================== 心 ====================

    def xn_gauge(self):
        """应世心条 -> (左半, 右半) 有紫色的列占比。读当前帧, 调用方负责 next_frame。"""
        frame = self.task.frame
        out = []
        for x1, y1, x2, y2 in (self.XN_GAUGE_L, self.XN_GAUGE_R):
            box = self.task.box_of_screen_scaled(3840, 2160, x1, y1, x2, y2, hcenter=True)
            crop = frame[box.y:box.y + box.height, box.x:box.x + box.width, :3]
            if crop.size == 0:
                return 0.0, 0.0
            hsv = cv2.cvtColor(np.ascontiguousarray(crop), cv2.COLOR_BGR2HSV)
            h, sat, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
            purple = (h >= 125) & (h <= 160) & (sat >= 70) & (v >= 90)
            out.append(float(purple.any(axis=0).mean()))
        return out[0], out[1]

    def xn_ying(self):
        """应世心 -> (满没满, 左半紫, 右半紫)。满 = 重击位的花图标 hsin_h1; 没满时条是紫色格子。读当前帧。"""
        try:
            full = bool(self.task.find_one('hsin_h1', threshold=self.XN_FULL_THRESHOLD))
        except Exception:
            full = False
        L, R = self.xn_gauge()
        return full, L, R

    def xn_icon(self, name):
        """心技能栏的图标模板(hsin_lib1 = 转相 / hsin_lib2 = 万阙垂天解锁)。读当前帧。"""
        try:
            return bool(self.task.find_one(name, threshold=0.7))
        except Exception:
            return False

    def xn_attack_down(self):
        return self.attack_down(self.XN_HOLD_SENDINPUT and self.game_foreground())

    def xn_hold_burn(self, tag):
        """按住重击 XN1_HOLD 秒, 期间看应世心条有没有被清空(= 步红尘出手)。

        返回 (状态, 清空时刻, 按下时刻)。状态:
          'burned'  清空了(时刻可能是 None: 按住期间没读到那一帧, 松手后读到是空的)
          'full'    松手后条还在 = 出的是普通重击(条差太多/被打断) -> 调用方补 A 再按
          'unknown' 条一次都没读出来, 不知道 -> 不重按(重按落在步红尘演出里会再起一个重击)
        """
        si = self.xn_attack_down()
        start = time.time()
        self.macro_mark(f'{tag}按住({"SI" if si else "PM"})')
        seen_full = False
        burned_at = None
        low_at = None
        trace = []
        try:
            while time.time() - start < self.XN1_HOLD:
                self.task.next_frame()
                if self.hud_ok() and burned_at is None:
                    now = time.time()
                    full, L, R = self.xn_ying()
                    if len(trace) < 30:
                        trace.append(f'{now - start:.2f}:{"满" if full else ""}{L:.2f}/{R:.2f}')
                    if full or L >= self.XN_GAUGE_VALID:
                        seen_full = True
                        low_at = None
                    elif seen_full and L < self.XN_CONSUMED:
                        # 连着两帧空才算(特效闪一下会压暗一帧); 时刻记第一帧 —— 转相解锁从这一刻算
                        if low_at is None:
                            low_at = now
                        else:
                            burned_at = low_at
                            self.macro_mark(f'{tag}步红尘出手({burned_at - start:.2f}s)')
                self.macro_wait(0.02)
        finally:
            self.release_attack()
        if burned_at is not None:
            self.macro_mark(f'{tag}松开')
            return 'burned', burned_at, start
        # 按住期间没读到清空: 松手后再读两帧, 条还在 = 真没出步红尘
        full = empty = 0
        for _ in range(6):
            self.task.next_frame()
            if self.hud_ok():
                is_full, L, R = self.xn_ying()
                if is_full or L >= self.XN_GAUGE_VALID:
                    full += 1
                    seen_full = True
                elif seen_full and L < self.XN_CONSUMED:
                    empty += 1
                if full >= 2 or empty >= 2:
                    break
            self.macro_wait(0.02)
        state = 'full' if full >= 2 else ('burned' if empty >= 2 else 'unknown')
        self.macro_mark(f'{tag}松开({state})')
        self.logger.info(f'{tag}: 按住 {self.XN1_HOLD:.1f}s 没读到应世心清空 -> {state} — {" ".join(trace)}')
        return state, None, start

    def xn_r1_ready(self):
        """转相能不能按: R 图标是转相(hsin_lib1)而且亮着。读当前帧。

        不查 CD(check_cd=False): 那一路每换一帧就 OCR 一次技能栏, 解锁那 0.3s 的窗口里读不了几次; 转相也没有 CD 数字。
        """
        try:
            lit = bool(self.available('liberation', check_color=True, check_cd=False))
        except Exception:
            lit = False
        return lit and self.xn_icon('hsin_lib1')

    def xn_r1_rescue(self, xn, tag):
        """转相第一次没放出去: 补到放出去为止(上限 XN1_R1_RESCUE_CAP)。返回放出去没有。

        每一轮看现在卡在哪:
          转相图标亮着(连两帧)       -> 按 R(被吞了就再来)
          应世心是满的(花图标 / 右半到线) -> 再按住出步红尘, 清空后等解锁
          都不是                     -> 普攻攒应世心
          HUD 不在(被击飞/演出)       -> 等它回来
        一直既看不到转相图标也读不到应世心条 = 已经进照世相了(转相其实出了只是没看到演出), 不再按 R ——
        照世相里按 R 放的是借相。
        """
        start = time.time()
        rounds = 0
        lost = 0
        self.macro_mark(f'{tag}转相补救开始')
        while time.time() - start < self.XN1_R1_RESCUE_CAP:
            rounds += 1
            self.task.next_frame()
            if not self.hud_ok():
                self.wait_hud_up(cap=1.0, tag=f'{tag}转相补救等HUD')
                continue
            lit = 0
            for _ in range(self.XN1_R1_READS):
                if self.xn_r1_ready():
                    lit += 1
                self.task.next_frame()
            if lit >= self.XN1_R1_READS:
                lost = 0
                if self.fire_r(xn, f'{tag}转相补#{rounds}', self.XN_R_WINDOW):
                    self.macro_mark(f'{tag}转相补救成功({time.time() - start:.2f}s)')
                    return True
                continue
            full, L, R = self.xn_ying()
            if full or L >= self.XN_GAUGE_VALID or self.xn_icon('hsin_lib1'):
                lost = 0
            else:
                lost += 1
                if lost >= self.XN1_R1_LOST_ROUNDS:
                    self.macro_mark(f'{tag}转相补救: 已不在应世相(当转相出过了)')
                    return True
            if full or (L >= self.XN_GAUGE_VALID and R >= self.XN_YING_READY):
                state, burned_at, _hold_at = self.xn_hold_burn(f'{tag}补步红尘#{rounds}')
                if state == 'burned':
                    # 清空后 2.06s 解锁: 等到点(期间亮了就提前走), 下一轮去按
                    anchor = burned_at if burned_at is not None else time.time() - 0.3
                    due = anchor + self.XN1_R1_UNLOCK + self.XN1_R1_MARGIN
                    while time.time() < due:
                        self.task.next_frame()
                        if self.hud_ok() and self.xn_r1_ready():
                            break
                        self.macro_wait(0.01)
                continue
            self.macro_spam(self.XN1_R1_RESCUE_A, self.XN1_FILL_EVERY, tag=f'{tag}补应世心A#{rounds}')
        self.macro_mark(f'{tag}转相补救(cap,{rounds}轮)')
        return False

    def xn_hold_until_gone(self, cap, tag):
        """按住左键到队伍 HUD 消失(临寰宇出手)。消失后再按 XN2_RELEASE_AFTER_GONE 秒松手。返回出手没有。"""
        si = self.xn_attack_down()
        start = time.time()
        self.macro_mark(f'{tag}按住({"SI" if si else "PM"})')
        gone = 0
        fired = False
        try:
            while time.time() - start < cap:
                self.task.next_frame()
                if not self.hud_ok():
                    gone += 1
                    if gone >= self.LIB_GONE_CONFIRM:
                        fired = True
                        break
                else:
                    gone = 0
                self.macro_wait(0.02)
            if fired:
                self.macro_mark(f'{tag}临寰宇出手({time.time() - start:.2f}s)')
                self.macro_wait(self.XN2_RELEASE_AFTER_GONE)
        finally:
            self.release_attack()
        self.macro_mark(f'{tag}松开({"出手" if fired else "没出"})')
        return fired

    def xn_pre_r2_con(self, tag):
        """万阙垂天之前: 协奏低于 XN2_PRE_R2_CON 就照世相普攻补(人还贴着怪), 每下之后读一次。"""
        start = time.time()
        con = self.read_con(1.0, settle=0.12)
        if con >= self.XN2_PRE_R2_CON:
            self.macro_mark(f'{tag}开大前协奏{con:.2f}')
            return
        samples = [f'0:{con:.2f}']
        taps = 0
        while time.time() - start < self.XN2_PRE_R2_CAP:
            self.tap()
            taps += 1
            self.macro_wait(max(0.0, self.A_INTERVAL - self.A_TAP))
            con = self.read_con(1.0, settle=0.03)
            if len(samples) < 20:
                samples.append(f'{time.time() - start:.2f}:{con:.2f}')
            if con >= self.XN2_PRE_R2_CON:
                break
        self.macro_mark(f'{tag}开大前补协奏({con:.2f},A x{taps},{time.time() - start:.2f}s)')
        if con < self.XN2_PRE_R2_CON:
            self.logger.info(f'{tag}: 开大前协奏补不到 {self.XN2_PRE_R2_CON:.2f} — {" ".join(samples)}')


    def xn_slot_glyph(self):
        """重击位 16x16 灰度(只取圆内像素), 已归一化。心不在场/HUD 不在返回 None。读当前帧。"""
        in_team, index, _count = self.task.in_team()
        if not in_team or index != self.index:
            return None
        self.hud_seen_at = time.time()
        ref = getattr(self, '_slot_ref', None)
        if ref is None:
            yy, xx = np.mgrid[:96, :96]
            disk = ((((xx - 48) ** 2 + (yy - 44) ** 2) <= 25 ** 2)).astype(np.float32)
            mask = cv2.resize(disk[18:70, 22:74], (16, 16), interpolation=cv2.INTER_AREA) > 0.99

            def tpl(chunks):
                raw = base64.b64decode(''.join(chunks))
                return self.glyph_vec(np.frombuffer(raw, np.uint8).reshape(16, 16).astype(np.float32)[mask])

            ref = self._slot_ref = (mask, disk, tpl(self.XN_TY_GLYPH), tpl(self.XN_READY_GLYPH))
        mask, disk, _ty, _rd = ref
        x, y, w, h = self.XN_TY_SLOT
        box = self.task.box_of_screen_scaled(3840, 2160, x, y, x + w, y + h, hcenter=True)
        frame = self.task.frame
        cx, cy = int(box.x + box.width / 2), int(box.y + box.height / 2)
        half = int(box.height * 1.1)
        icon = frame[max(0, cy - half):cy + half, max(0, cx - half):cx + half, :3]
        g = cv2.cvtColor(cv2.resize(icon, (96, 96), interpolation=cv2.INTER_AREA),
                         cv2.COLOR_BGR2GRAY).astype(np.float32) * disk
        v = cv2.resize(g[18:70, 22:74], (16, 16), interpolation=cv2.INTER_AREA)
        return self.glyph_vec(v[mask])

    def xn_tongyu(self):
        """在不在统御众机: 重击位是雕像图标。读当前帧; 心不在场/HUD 不在返回 None。"""
        try:
            v = self.xn_slot_glyph()
            if v is None:
                return None
            self._ty_score = float(v @ self._slot_ref[2])
            return self._ty_score >= self.XN_TY_MIN
        except Exception as e:
            self.logger.info(f'xn_tongyu probe failed ({e})')
            return None

    def xn_slot_state(self):
        """统御众机里重击位: 'statue'(照世心还没打空) / 'ready'(人像, 临寰宇可按) / '?' / None(HUD 不在)。读当前帧。"""
        try:
            v = self.xn_slot_glyph()
            if v is None:
                return None
            _mask, _disk, ty, rd = self._slot_ref
            self._ty_score = float(v @ ty)
            self._rd_score = float(v @ rd)
            if self._rd_score >= self.XN_READY_MIN:
                return 'ready'
            if self._ty_score >= self.XN_TY_MIN:
                return 'statue'
            return '?'
        except Exception as e:
            self.logger.info(f'xn_slot_state probe failed ({e})')
            return '?'

    def xn_form(self, tag):
        """心现在是哪个相: 'ying'(转相图标 hsin_lib1 / 应世心花 / 应世心条读得出) / 'zhao'(HUD 在场读够帧数, 三样都不是) /
        '?'(HUD 一直不在, 当应世相处理)。最多读 XN_FORM_CAP 秒。"""
        start = time.time()
        live = 0
        while time.time() - start < self.XN_FORM_CAP:
            self.task.next_frame()
            if self.hud_ok():
                live += 1
                full, L, _R = self.xn_ying()
                if full or L >= self.XN_GAUGE_VALID or self.xn_icon('hsin_lib1'):
                    return 'ying'
                if live >= self.XN_FORM_READS:
                    self.macro_mark(f'{tag}在照世相({time.time() - start:.2f}s)')
                    return 'zhao'
            self.macro_wait(0.02)
        return '?'

    def xn1_fill(self, arrived, tag):
        """心第一段: 一直点普攻, 应世心满(花图标 / 右半到线, 连读几帧)并且过了 XN1_HOLD_AT_MIN 就返回。
        返回原因: 'ready' / 'cap'(到上限还没满, 照按) / 'blind'(条一次都没读出来, 照按)。"""
        self.wait_until_time(arrived + self.XN1_A_FROM)
        hits = taps = 0
        next_tap = last_tap = 0.0
        ready_at = None
        valid_seen = False
        trace = []
        why = 'cap'
        while True:
            now = time.time()
            if now >= next_tap:
                self.tap(self.XN1_A_HOLD)
                taps += 1
                last_tap = time.time()
                next_tap = last_tap + max(0.0, self.XN1_A_EVERY - self.XN1_A_HOLD)
            self.task.next_frame()
            now = time.time()
            if self.hud_ok():
                full, L, R = self.xn_ying()
                if len(trace) < 30:
                    trace.append(f'{now - arrived:.2f}:{"满" if full else ""}{L:.2f}/{R:.2f}')
                if full or L >= self.XN_GAUGE_VALID:
                    valid_seen = True
                hits = hits + 1 if (full or (L >= self.XN_GAUGE_VALID and R >= self.XN_YING_READY)) else 0
                if hits >= self.XN1_GATE_CONFIRM and ready_at is None:
                    ready_at = now
                    self.macro_mark(f'{tag}应世心满({"花" if full else f"{R:.2f}"},A x{taps},{now - arrived:.2f}s)')
            if ready_at is not None and now >= arrived + self.XN1_HOLD_AT_MIN:
                why = 'ready'
                break
            if now >= arrived + self.XN1_A_CAP:
                why = 'cap' if valid_seen else 'blind'
                break
            self.macro_wait(0.02)
        if why != 'ready':
            self.macro_mark(f'{tag}应世心{"不够" if why == "cap" else "读不到"}(照按,A x{taps})')
            self.logger.info(f'{tag}: 应世心 {why} — {" ".join(trace)}')
        left = last_tap + self.XN1_LAST_A_GAP - time.time()
        if left > 0:
            self.macro_wait(left)
        return why

    def seg_xn1(self, tag):
        """心·第一段(雷主变奏进来, 应世相): Q -> A 到应世心满 -> 按住出步红尘 -> 转相解锁 -> 转相 -> 演完。
        返回 'zhao'(上场就在照世相, 这一段跳过) / 'r1'(转相放出去了) / 'nor1'(补到上限也没放出去, 还在应世相)。"""
        arrived = getattr(self, 'last_switch_in_time', 0.0) or time.time()
        if not self.has_intro:
            self.macro_mark(f'{tag}心不是变奏进来的(应世心少 60)')
        self.wait_until_time(arrived + self.XN1_Q_AT)
        self.spam_key(self.send_echo_key, self.XN1_Q_WINDOW, tag=f'{tag}Q', presses=2)
        self.record_echo_use()
        if self.xn_form(tag) == 'zhao':
            # 上一圈第二段没放出万阙垂天, 心还在照世相: 这一段没有步红尘/转相可打, 按 R 是借相(切回应世相)。
            # 直接走第二段照世相那套(会把万阙垂天补上)
            self.logger.warning(f'{tag}: 心上场还在照世相(上一圈万阙垂天没放出来), 第一段跳过步红尘/转相')
            return 'zhao'
        self.xn1_fill(arrived, tag)

        state = 'unknown'
        hold_at = burned_at = None
        for attempt in range(1 + self.XN1_RETRIES):
            if attempt > 0:
                # 上一次松手后条还在 = 出的是普通重击: 补两下 A 再按
                for _ in range(self.XN1_RETRY_A):
                    self.tap(self.XN1_A_HOLD)
                    self.macro_wait(self.XN1_FILL_EVERY)
                self.macro_mark(f'{tag}重击重按#{attempt}')
            state, burned_at, hold_at = self.xn_hold_burn(f'{tag}重击' if attempt == 0 else f'{tag}重击#{attempt}')
            if state != 'full':
                break
        burned = state == 'burned'
        if state == 'full':
            self.logger.warning(f'{tag}: 重按 {self.XN1_RETRIES} 次应世心都没清空(步红尘没出), 转相多半放不出来')

        if burned_at is not None:
            # 锚点 + 固定时长: 清空后 2.06s 解锁。期间读到一帧亮就提前走
            self.wait_until_time(burned_at + self.XN1_R1_POLL_FROM)
            due = burned_at + self.XN1_R1_UNLOCK + self.XN1_R1_MARGIN
            why = '到点'
            while time.time() < due:
                self.task.next_frame()
                if self.hud_ok() and self.xn_r1_ready():
                    why = '亮'
                    break
                self.macro_wait(0.01)
            self.macro_mark(f'{tag}转相解锁({why},清空后{time.time() - burned_at:.2f}s)')
        else:
            # 没看到清空: 读图标, 连着亮几帧才算; 读不到就到这一刻照按(没解锁时按 R 什么都不发生)
            cap_at = hold_at + self.XN1_R1_LIT_CAP
            blind_at = hold_at + self.XN1_R1_BLIND_AT
            hits = 0
            lit = False
            while time.time() < cap_at:
                self.task.next_frame()
                if self.hud_ok():
                    hits = hits + 1 if self.xn_r1_ready() else 0
                    if hits >= self.XN1_R1_READS:
                        lit = True
                        break
                if not burned and time.time() >= blind_at:
                    break
                self.macro_wait(0.02)
            self.macro_mark(f'{tag}转相{"亮" if lit else "没读到亮"}(没看到清空)')
        fired = self.fire_r(self, f'{tag}转相', self.XN_R_WINDOW)
        if not fired:
            fired = self.xn_r1_rescue(self, tag)
        if not fired:
            self.logger.warning(f'{tag}: 补了 {self.XN1_R1_RESCUE_CAP:.0f}s 转相还是没放出去, 这一圈没有照世相(补满协奏就交棒)')
            return 'nor1'
        self.wait_hud_back(tag=f'{tag}转相演出', min_gone=self.XN_R_ANIM_MIN, time_out=self.XN_R_ANIM_CAP)
        return 'r1'

    def xn_break(self, tag):
        """统御众机里处决: 只按 F(最多 XN_BREAK_PRESSES 下, 提示没了就停), 从第一下起等满 XN_BREAK_ANIM。返回花了多久。
        不走框架的 task.f_break(): 那个会连点左键、至少卡 0.5s。"""
        start = time.time()
        presses = 0
        while presses < self.XN_BREAK_PRESSES:
            self.task.send_key('f', down_time=0.05)
            presses += 1
            self.macro_wait(0.10)
            self.task.next_frame()
            if not self.break_prompt():
                break
        try:
            self.task.can_break = False
        except Exception:
            pass
        self.macro_wait(max(0.0, start + self.XN_BREAK_ANIM - time.time()))
        self.macro_mark(f'{tag}处决(F x{presses},{time.time() - start:.2f}s)')
        return time.time() - start

    def xn_lianheng(self, tag, waited=0.0):
        """E(照世相)之后连按 E: 照世心满 300 的那一刻 E 是万阙连衡, 按出去进统御众机。返回进没进。
        没满时 E 在 CD 上, 按了是空操作。没进去就 普攻攒照世心 + 按 E 交替, 上限 XN2_RESCUE_CAP。"""
        start = time.time()
        n = hits = na = 0
        next_e = next_a = 0.0
        scores = []
        while time.time() - start < self.XN2_LIANHENG_CAP:
            now = time.time()
            if now >= next_e:
                self.send_resonance_key(down_time=self.M_E_KEY_DOWN)
                n += 1
                next_e = time.time() + self.XN2_E_MASH
            elif now - start >= self.XN2_LIANHENG_POKE_AT - waited and now >= next_a:
                self.tap()
                na += 1
                next_a = time.time() + self.XN2_LIANHENG_A_EVERY
            self.task.next_frame()
            ty = self.xn_tongyu()
            if len(scores) < 30:
                scores.append(f'{time.time() - start:.2f}:{getattr(self, "_ty_score", -1):.2f}')
            hits = hits + 1 if ty else 0
            if hits >= self.XN2_TY_CONFIRM:
                self.macro_mark(f'{tag}进统御众机(E x{n},A x{na},{time.time() - start:.2f}s)')
                return True
            self.macro_wait(0.02)
        self.macro_mark(f'{tag}强化E没进统御众机(E x{n},A x{na},{self.XN2_LIANHENG_CAP:.1f}s)')
        self.logger.info(f'{tag}: 雕像图标读数 — {" ".join(scores)}')
        r0 = time.time()
        rounds = 0
        while time.time() - r0 < self.XN2_RESCUE_CAP:
            rounds += 1
            self.macro_spam(self.XN2_RESCUE_A, self.XN2_A_EVERY, tag=f'{tag}攒照世心A#{rounds}')
            end = time.time() + self.XN2_RESCUE_E
            hits = 0
            while time.time() < end:
                self.send_resonance_key(down_time=self.M_E_KEY_DOWN)
                self.macro_wait(0.05)
                self.task.next_frame()
                hits = hits + 1 if self.xn_tongyu() else 0
                if hits >= self.XN2_TY_CONFIRM:
                    self.macro_mark(f'{tag}补进统御众机(#{rounds},{time.time() - start:.2f}s)')
                    return True
                self.macro_wait(max(0.0, self.XN2_E_MASH - 0.05))
        self.macro_mark(f'{tag}统御众机补救(cap,{rounds}轮)')
        return False

    def xn_statue_reset(self):
        self._statue_streak = [0] * len(self.XN_STATUE_XS)
        self._statue_latch = [False] * len(self.XN_STATUE_XS)

    def xn_statue_count(self):
        """照世心雕像从右往左连续翻了几颗(翻过的记住, 每次进统御众机先 xn_statue_reset)。读当前帧。"""
        frame = self.task.frame
        hw = self.XN_STATUE_HW
        for k, x in enumerate(self.XN_STATUE_XS):
            if self._statue_latch[k]:
                continue
            red = glow = 0.0
            for y, kind in ((self.XN_STATUE_Y, 'red'), (self.XN_STATUE_UP_Y, 'glow')):
                box = self.task.box_of_screen_scaled(3840, 2160, x - hw, y - hw, x + hw, y + hw, hcenter=True)
                crop = frame[box.y:box.y + box.height, box.x:box.x + box.width, :3]
                if crop.size == 0:
                    continue
                hsv = cv2.cvtColor(np.ascontiguousarray(crop), cv2.COLOR_BGR2HSV)
                h, sat, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
                if kind == 'red':
                    red = float((((h < 12) | (h > 160)) & (sat > 90) & (v > 110)).mean())
                else:
                    glow = float(((v > 235) & (sat < 60)).mean())
            hit = red >= self.XN_STATUE_RED or glow >= self.XN_STATUE_GLOW
            self._statue_streak[k] = self._statue_streak[k] + 1 if hit else 0
            if self._statue_streak[k] >= self.XN_STATUE_CONFIRM:
                self._statue_latch[k] = True
        n = 0
        for latched in reversed(self._statue_latch):
            if not latched:
                break
            n += 1
        return n

    def xn_tongyu_phase(self, tag, cap, dodge_at=None):
        """统御众机里一直普攻到重击位换成人像(照世心打空)。dodge_at: 给了就闪避一次(None = 不闪)。
        【闪避的时机 = 照世心雕像翻满 XN2_TY_DODGE_COUNT 颗】(不早于 XN2_TY_DODGE_MIN, 数不到也不晚于 XN2_TY_DODGE_CAP)。
        怪身上出了处决提示就处决: 出在闪避之前就等到闪避那一刻再处决(代替闪避), 之后出的马上处决(只处决一次)。
        返回 'ready'(人像连读几帧) / 'cap'(到上限没看到人像)。"""
        start = time.time()
        n = 0
        next_click = 0.0
        dodged = dodge_at is None
        ready_hits = brk_hits = 0
        prompt_at = None
        count = last_count = 0
        counts = []
        self.xn_statue_reset()
        why = 'cap'
        last = None
        while time.time() - start < cap:
            now = time.time()
            if now >= next_click:
                self.tap()
                n += 1
                next_click = time.time() + max(0.0, self.XN2_TY_A_EVERY - self.A_TAP)
            self.task.next_frame()
            st = self.xn_slot_state()
            last = st
            ready_hits = ready_hits + 1 if st == 'ready' else 0
            if ready_hits >= self.XN2_READY_CONFIRM:
                why = 'ready'
                break
            el = time.time() - start
            if st is not None:
                try:
                    count = self.xn_statue_count()
                except Exception as e:
                    self.logger.info(f'xn_statue_count failed ({e})')
                if count != last_count:
                    last_count = count
                    if len(counts) < 12:
                        counts.append(f'{count}@{el:.2f}')
            prompt = False
            if self.XN_BREAK and not self.xn_broke and st is not None and el >= self.XN_BREAK_FROM:
                brk_hits = brk_hits + 1 if self.break_prompt() else 0
                prompt = brk_hits >= self.XN_BREAK_CONFIRM
                if prompt and prompt_at is None:
                    prompt_at = time.time()
                    self.macro_mark(f'{tag}处决提示({el:.2f}s,翻{count})')
            if dodged and prompt:
                # 闪避之后才出的提示: 马上处决
                self.xn_broke = True
                self.macro_mark(f'{tag}统御众机A(x{n},{el:.2f}s,翻{count})')
                self.xn_break(tag)
                continue
            if not dodged and el >= self.XN2_TY_DODGE_MIN and (count >= self.XN2_TY_DODGE_COUNT or el >= self.XN2_TY_DODGE_CAP):
                dodged = True
                self.macro_mark(f'{tag}统御众机A(x{n},{el:.2f}s,翻{count}{"" if count >= self.XN2_TY_DODGE_COUNT else ",数不到撞上限"})')
                # 之前见过处决提示: 这一刻再确认一下(提示读数会闪), 还在就处决代替闪避
                use_break = False
                if self.XN_BREAK and not self.xn_broke and prompt_at is not None and \
                        time.time() - prompt_at <= self.XN2_TY_PROMPT_KEEP:
                    use_break = prompt or self.break_prompt_reads(3)
                if use_break:
                    self.xn_broke = True
                    self.xn_break(tag)
                else:
                    self.dodge(tag)
                    self.macro_wait(self.XN2_DODGE_TO_A)
                continue
            self.macro_wait(0.01)
        self.macro_mark(f'{tag}照世心{"打空" if why == "ready" else "没看到打空(cap)"}(A x{n},{time.time() - start:.2f}s)')
        if counts:
            self.logger.info(f'{tag}: 照世心雕像翻面(颗@秒) — {" ".join(counts)}')
        if why != 'ready':
            self.logger.info(f'{tag}: {cap:.1f}s 没看到重击位换人像(最后读成 {last}, '
                             f'雕像{getattr(self, "_ty_score", -1):.2f} 人像{getattr(self, "_rd_score", -1):.2f})')
        return why

    def seg_xn2(self, su, opener, state, tag):
        """心·第二段(转相演完接着打, 照世相): 3A(启动轴)/2A(循环轴) -> E -> [循环轴等普通 E 打完] -> 连按 E 进统御众机 -> A -> 闪 -> 2A
        -> 按住到临寰宇 -> 万阙垂天(认 hsin_lib2) -> 演完【不按 E】-> 协奏满 -> 变奏穗穗。
        state: seg_xn1 的返回。'nor1'(转相没放出去, 还在应世相)就跳过照世相这套, 补满协奏交棒。"""
        if state == 'nor1':
            self.macro_mark(f'{tag}没转相, 跳过照世相')
            self.xn_handoff(su, tag)
            return
        self.wait_hud_up(cap=self.HUD_UP_CAP, tag=f'{tag}HUD')
        self.macro_spam(self.XN2_3A if opener else self.XN2_2A, self.XN2_A_EVERY, tag=f'{tag}{"3A" if opener else "2A"}')
        e_ok = self.press_res_until_cd(self, self.XN2_E1_CAP, tag=f'{tag}E')
        if not e_ok:
            self.logger.info(f'{tag}: 照世相 E 没判到进 CD')
        self.record_resonance_use()
        waited = 0.0
        if not opener and e_ok:
            # 普通 E 最后一下引爆电磁效应, 让它打完再按万阙连衡
            self.macro_wait(self.XN2_E_FULL)
            waited = self.XN2_E_FULL
            self.macro_mark(f'{tag}等普通E打完({waited:.2f}s)')
        in_ty = self.xn_lianheng(tag, waited)
        self.xn_broke = False
        if in_ty:
            why = self.xn_tongyu_phase(tag, self.XN2_TY_CAP, dodge_at=True)
            fired = self.xn_hold_until_gone(self.XN2_HOLD_CAP if why == 'ready' else self.XN2_BLIND_HOLD, f'{tag}按住')
            for attempt in range(1, 1 + self.XN2_RETRIES):
                if fired:
                    break
                # 按住没出(被打断 / 人像是误读): 普攻到人像再按
                why = self.xn_tongyu_phase(f'{tag}补#{attempt}', self.XN2_RETRY_CAP)
                fired = self.xn_hold_until_gone(self.XN2_HOLD_CAP if why == 'ready' else self.XN2_BLIND_HOLD,
                                                f'{tag}重按#{attempt}')
        else:
            # 没认出统御众机: 不在统御众机里临寰宇出不来, 只按一次试探(万一是雕像图标没认出来), 不重按
            fired = self.xn_hold_until_gone(self.XN2_BLIND_HOLD, f'{tag}按住(试探)')
        if not fired:
            self.logger.warning(f'{tag}: 临寰宇一直没出手(统御众机{"进了" if in_ty else "没进"}), '
                                f'这一轮不放万阙垂天(按 R 会放成借相)')
        else:
            self.wait_hud_back(tag=f'{tag}临寰宇演出', min_gone=self.XN2_ANIM_MIN, time_out=self.XN2_ANIM_CAP)
            # 【R 只认 hsin_lib2】: 照世相里 R 一直亮(借相·应世), 只有临寰宇之后才换成万阙垂天的图标; 认不出就不按
            start = time.time()
            hits = 0
            unlocked = False
            while time.time() - start < self.XN2_LIB2_CAP:
                self.task.next_frame()
                if self.hud_ok():
                    hits = hits + 1 if self.xn_icon('hsin_lib2') else 0
                    if hits >= self.XN2_LIB2_READS:
                        unlocked = True
                        break
                self.macro_wait(0.02)
            self.macro_mark(f'{tag}万阙垂天{"解锁" if unlocked else "图标没出来(不按, 免得放成借相)"}'
                            f'({time.time() - start:.2f}s)')
            if unlocked:
                self.xn_pre_r2_con(tag)
                if self.fire_r(self, f'{tag}万阙垂天', self.XN_R_WINDOW):
                    self.wait_hud_back(tag=f'{tag}万阙垂天演出', min_gone=self.XN_R_ANIM_MIN,
                                       time_out=self.XN_R_ANIM_CAP)
                else:
                    self.logger.warning(f'{tag}: 万阙垂天没放出去(能量不够?)')
            else:
                self.logger.warning(f'{tag}: 临寰宇之后 {self.XN2_LIB2_CAP:.1f}s 没认出万阙垂天图标, 这一轮不放'
                                    f'(心留在照世相, 下一圈第一段会跳过转相)')
        self.xn_handoff(su, tag)

    def xn_handoff(self, su, tag):
        """协奏满 -> 变奏穗穗。补协奏只点普攻: 万阙垂天之后按 E 会把电磁效应层数一次结算掉(作者), 心专武的效应加深要心在场才吃得到。"""
        full = self.read_con(1.0, settle=0.20) >= 1.0 or self.wait_con_full('心', self.XN2_CON_CAP, tag=f'{tag}协奏')
        if not full:
            self.logger.warning(f'{tag}: 心协奏没满就切穗穗 —— 穗穗不是变奏进来的, 下一圈第一格走启动格(3A 醒春潮)')
        self.need(self.switch_retry(su, f'{tag}切穗穗', assume_con=full), 'hsin -> suisui')

    # ==================== 一圈 ====================

    def run_cycle(self, lei, su, opener, tag):
        """穗穗(HUD 在场) -> 雷主 -> 穗穗 -> 雷主(变奏) -> 心(变奏, 两段连着打) -> 穗穗变奏入场、HUD 在场。"""
        marks = len(self.macro_marks)
        self.timeline_logged = False
        if opener:
            self.seg_su_open(su, lei, tag=f'{tag}穗0')
        else:
            self.seg_su_loop(su, lei, tag=f'{tag}穗0')
        self.seg_lei1(su, tag=f'{tag}雷1')
        self.seg_su2(lei, tag=f'{tag}穗2')
        self.seg_lei2(tag=f'{tag}雷2')
        state = self.seg_xn1(tag=f'{tag}心1')
        self.seg_xn2(su, opener, state, tag=f'{tag}心2')
        self.logger.info(f'{tag} cycle timeline: {self.macro_timeline(marks)}')
        self.timeline_logged = True

    def macro_enter(self, entry_char):
        lei = self.teammate('Rover')
        su = self.teammate('Suisui')
        if lei is None or su is None:
            return None
        previous = getattr(self.task, 'skip_combat_check', False)
        self.task.skip_combat_check = True
        self.mark_busy(True)
        self.cur = entry_char or self.on_field_char() or self
        for char in (self, lei, su):
            char.check_f_on_switch = False
        self.macro_start()
        self.timeline_logged = False
        self.hud_seen_at = time.time()
        self.hud_watch = True
        return lei, su, previous

    def macro_exit(self, previous):
        # 长按跨了好几个方法, 中途抛异常的话鼠标会一直按着。这里是唯一保证松手的地方
        self.release_attack()
        # 中途被停(关自动战斗/切出窗口)也要把时间轴写下来
        if not self.timeline_logged and self.macro_marks:
            self.logger.info(f'xls timeline (没跑完): {self.macro_timeline()}')
            self.timeline_logged = True
        self.hud_watch = False
        self.task.skip_combat_check = previous
        self.mark_busy(False)

    def perform_opener(self, entry_char=None):
        """启动轴: 切穗穗 -> 一圈(穗穗启动格)。返回时穗穗刚变奏入场、HUD 在场。"""
        got = self.macro_enter(entry_char)
        if got is None:
            return False
        lei, su, previous = got
        self.logger.info(f'xls opener entry: {self.cur.name}')
        try:
            self.loop_count = 0
            self.run_cycle(lei, su, opener=True, tag='op')
            self.logger.info(
                f'xls opener total {self.time_elapsed_accounting_for_freeze(self.macro_t0):.2f}s '
                f'(wall {time.time() - self.macro_t0:.2f}s)')
        except MacroBroken as e:
            self.logger.warning(f'xls opener broke ({e}) — timeline: {self.macro_timeline()}')
            self.timeline_logged = True
        finally:
            self.macro_exit(previous)
        return True

    def perform_loop(self, entry_char=None):
        """循环轴一圈。场上不是穗穗(宏散过)就先切给她, 第一格走启动格(3A 醒春潮)。"""
        got = self.macro_enter(entry_char)
        if got is None:
            return False
        lei, su, previous = got
        try:
            self.loop_count += 1
            n = self.loop_count
            self.run_cycle(lei, su, opener=False, tag=f'L{n}')
            self.logger.info(
                f'xls loop #{n} {self.time_elapsed_accounting_for_freeze(self.macro_t0):.2f}s '
                f'(wall {time.time() - self.macro_t0:.2f}s)')
        except MacroBroken as e:
            self.logger.warning(f'xls loop broke ({e}) — timeline: {self.macro_timeline()}')
            self.timeline_logged = True
        finally:
            self.macro_exit(previous)
        return True

    # ==================== 框架接口 ====================

    def drive(self, entry):
        """三个人的 do_perform 都走这里。entry = 框架这次调的是谁(= 场上是谁)。"""
        # 【HUD 不在就什么都不做】: 关卡结束/结算/过场时框架还会接着调进来(F 开始战斗那边撑着不脱战)
        if not self.wait_hud_up(cap=self.DRIVE_HUD_CAP, tag='drive'):
            if time.time() - self.drive_log_at > 10:
                self.drive_log_at = time.time()
                self.logger.info('xls: 队伍 HUD 不在(结算/过场/窗口没了?), 宏不动')
            return None
        blocked = self.opener_blocked_by()
        if blocked is None:
            # 标记要在跑之前落: 中途抛异常(脱战/任务被停)也不能让启动轴重跑
            self.opener_armed = False
            self.last_opener = time.time()
            return self.perform_opener(entry)
        self.logger.info(f'xls: opener not pending ({blocked}), running the loop')
        return self.perform_loop(entry)

    def do_perform(self):
        if not self.is_in_xls:
            return super().do_perform()
        self.drive(self)

    def get_switch_priority(self, current_char=None, has_intro=False, target_low_con=False):
        """启动轴待跑时不让框架把心切上来(宏自己切)。"""
        if self.is_in_xls and self.opener_pending():
            return SwitchPriority.NO
        return super().get_switch_priority(current_char, has_intro, target_low_con)

    def on_combat_end(self, chars):
        self.release_attack()
        return super().on_combat_end(chars)
