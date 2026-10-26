"""心雷穗轴的干跑: 假 task + 假游戏, 真跑一遍启动轴和几圈循环。

验证的是【调用链、判据分支和逐格墙钟】, 不是打得对不对:
  - 有没有 AttributeError / 参数对不上
  - 每一格是等到了判据, 还是撞上限出来的
  - 演出时长按视频(雷主R 3.8 / 穗穗R 4.3 / 转相 4.3 / 临寰宇 2.0 / 万阙垂天 5.0)
  - 穗穗第一次翾舞(延奏后 6.0s 游戏时间)那一刻在场的是不是雷主(烟岚要交给心)
用法: 放在 <working>/configs/custom_teams/Hsin__Rover__Suisui/ 里(跟三个 .py 一起), 用 ok-ww 自带 python 跑:
      <ok-ww 安装目录>/data/apps/ok-ww/python/python.exe dryrun.py.tool
      working 目录从本文件位置往上自动找; 放在别处跑就设环境变量 OKWW_WORKING=<...>/data/apps/ok-ww/working
环境变量:
  DRY_LOOPS=2            循环几圈
  DRY_FULL=0             心变奏入场应世心直接满(1) / 只给 60(0)
  DRY_BREAK=0            统御众机里怪的谐度满(处决可用)
  DRY_FAIL=a,b,...       故意失败(每圈各触发一次), 测保底分支:
                         sw        切心第一下被拒 2.8s(被击飞/硬直)
                         sue1      启动轴穗穗醒春潮图标不亮(已经在濯雨时, 走照按 E)
                         sueslow   启动轴穗穗前 4s 普攻打不中(水云息不涨, 醒春潮晚亮)
                         sueeat    穗穗醒春潮第一下被吞(图标还亮, 要接着 A 再按)
                         fangslow  穗穗第二格普攻一半没打中(芳菲信涨得慢, 要靠补 E + 放长的上限)
                         sucon     穗穗大招后协奏差一截(要补)
                         suconlow  穗穗第二格上场协奏只有 0.70(大招前要补到 0.82)
                         suback    雷主第一格穗穗 3s 都切不回来(要靠切人重试)
                         readyblind 雷主 [E] 小框一直读不到(撞上限照按 E)
                         oeat      雷主超负荷第一下被吞(要补 A 再按)
                         echocd    雷主第一格 Q 图标读不出离地(声骸在 CD 上, 走按时间切)
                         noplunge  雷主第一格空中 A 没出下落(自然落地 1.5s)
                         heavy     心第一段第一次按住只出普通重击(没出步红尘)
                         r1        心转相解锁后 R 被吞 2.5s(走转相补救)
                         e1miss    心照世相 E 没打碎活字心锁(照世心不够 300, 走统御众机补救)
                         lin       心第一次按住被打断(临寰宇没出, 要补 A 重按)
                         hudlost   循环 #1 心万阙垂天之后关卡结束(HUD 再也不回来)
"""
import os
import random
import sys
import time
import types
from pathlib import Path


def find_working():
    """ok-ww 的 working 目录(里面有 src/char/CustomCharLoader.py): OKWW_WORKING > 本文件往上 > 当前目录往上。"""
    marker = Path('src') / 'char' / 'CustomCharLoader.py'
    cands = [Path(os.environ['OKWW_WORKING'])] if os.environ.get('OKWW_WORKING') else []
    here = Path(os.path.abspath(__file__))
    cands += [*here.parents, Path.cwd(), *Path.cwd().parents]
    for c in cands:
        if (c / marker).is_file():
            return str(c)
    sys.exit('找不到 ok-ww 的 working 目录: 把本文件放进 <working>/configs/custom_teams/Hsin__Rover__Suisui/ 再跑, '
             '或者设环境变量 OKWW_WORKING')


sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
WORKING = find_working()
sys.path.insert(0, WORKING)
os.chdir(WORKING)              # 框架按相对路径 configs/custom_teams 找队伍代码

DRY_LOOPS = int(os.environ.get('DRY_LOOPS', '2'))
FAILS = set(x for x in os.environ.get('DRY_FAIL', '').split(',') if x)
FULL = os.environ.get('DRY_FULL', '0') == '1'
BREAK = os.environ.get('DRY_BREAK', '0') == '1'
random.seed(7)
LOG = []
T0 = [time.time()]
XN, LEI, SU = 0, 1, 2          # 视频的编队: 1 心 / 2 雷主 / 3 穗穗
NAMES = ['心', '雷', '穗']


def rec(what):
    LOG.append((time.time() - T0[0], what))


class FakeExecutor:
    trigger_tasks = []
    onetime_tasks = []
    interaction = None

    def check_enabled(self, check_pause=False):
        pass


class Game:
    def __init__(self):
        self.on_field = XN
        self.pending = None
        self.hud_hidden = []
        self.flickers = []
        self.lock_until = 0.0
        self.no_switch_until = 0.0
        self.con = {XN: 0.2, LEI: 0.0, SU: 0.0}
        self.e_cd = {XN: 0.0, LEI: 0.0, SU: 0.0}
        self.r_cd = {XN: 0.0, LEI: 0.0, SU: 0.0}
        self.holding = False
        self.hold_at = 0.0
        self.cycle = 0
        self.fail_used = set()
        self.hud_dead = False
        self.last_step = {XN: 0.0, LEI: 0.0, SU: 0.0}
        self.arrived_at = 0.0
        self.break_cd = 0.0
        self.avail_at = {XN: 0.0, LEI: 0.0, SU: 0.0}   # 切走后多久才能再切回来
        # 停游戏时钟的演出(算翾舞用)
        self.freezes = []
        self.su_outro_at = None
        # 穗穗
        self.shui = 0
        self.fang = 0
        self.qiang_until = 0.0
        self.su_qiang_cast_at = -9.0
        # 雷主
        self.surge = 0
        self.overload_until = 0.0
        self.lei_air_from = None
        self.lei_land_at = None
        # 心
        self.xn_mode = 'ying'
        self.ying = 100 if FULL else 60
        self.ying_hits = []
        self.burned_at = None
        self.r1_unlock = None
        self.r1_unlocked = False
        self.r1_block_until = 0.0
        self.huozi = False
        self.zhao_xin = 0
        self.zhao_due = []
        self.tongyu = False
        self.lin_unlocked = False
        self.heavy_fail = None
        self.lin_block = False
        self.normal_heavy_done = False

    def fail_once(self, name):
        if name not in FAILS or (name, self.cycle) in self.fail_used:
            return False
        self.fail_used.add((name, self.cycle))
        rec(f'!!故意失败:{name}')
        return True

    def hud_visible(self, now=None):
        now = time.time() if now is None else now
        if self.hud_dead:
            return False
        for a, b in self.flickers:
            if a <= now < b:
                return True
        for a, b in self.hud_hidden:
            if a <= now < b:
                return False
        return True

    def hide(self, dur, flick=(), freeze=True):
        now = time.time()
        self.hud_hidden.append((now, now + dur))
        if freeze:
            self.freezes.append((now, now + dur))
        for f in flick:
            self.flickers.append((now + f, now + f + 0.06))
        self.lock_until = max(self.lock_until, now + dur)
        self.no_switch_until = max(self.no_switch_until, now + dur)

    def game_since(self, t0):
        now = time.time()
        frozen = sum(max(0.0, min(b, now) - max(a, t0)) for a, b in self.freezes)
        return now - t0 - frozen

    def busy(self):
        return time.time() < self.lock_until

    def add_con(self, i, v):
        self.con[i] = min(1.0, self.con[i] + v)

    def tick(self):
        now = time.time()
        if self.pending and now >= self.pending[1]:
            dst = self.pending[0]
            src = self.on_field
            self.pending = None
            intro = self.con[src] >= 1.0
            if intro:
                self.con[src] = 0.0
            self.on_field = dst
            self.arrived_at = now
            self.avail_at[src] = now + (2.2 if src == SU and now - self.su_qiang_cast_at < 0.6 else 1.0)
            if src == LEI and dst == SU and self.fail_once('suback'):
                pass
            rec(f'到场{NAMES[dst]}{"(变奏)" if intro else ""}')
            if src == SU and intro:
                self.su_outro_at = now
            if src == LEI and dst == XN and self.su_outro_at is not None:
                g = self.game_since(self.su_outro_at)
                rec(f'{"烟岚: 雷主在场吃到翾舞1" if g >= 6.11 else "!!烟岚: 翾舞1 时雷主已经走了"}'
                    f'(穗穗延奏后游戏时间 {g:.2f}s)')
                self.su_outro_at = None
            if dst == SU and intro:
                self.qiang_until = now + 15.0
                self.lock_until = now + 1.4             # 视频: 变奏入场 ~1.4s 里按的 E 全丢
                self.no_switch_until = now + 1.0
                self.add_con(SU, 0.47)
            elif dst == XN and intro:
                if self.xn_mode == 'ying':
                    self.ying = 100 if FULL else min(100, self.ying + 60)
                    self.lock_until = now + 0.45
                else:
                    self.lock_until = now + 0.9
            if dst == SU and not intro and src == LEI and self.fail_once('suconlow'):
                self.con[SU] = min(self.con[SU], 0.70)
            if dst == LEI:
                self.plunged = False
                self.lei_air_from = None
                self.lei_land_at = None
            if dst == LEI and intro:
                self.surge = min(120, self.surge + 20)
                self.lock_until = now + 0.30
                self.add_con(LEI, 0.10)
        for at, v in list(self.ying_hits):
            if now >= at:
                self.ying_hits.remove((at, v))
                if self.on_field == XN and self.xn_mode == 'ying' and self.burned_at is None:
                    self.ying = min(100, self.ying + v)
        for at, v in list(self.zhao_due):
            if now >= at:
                self.zhao_due.remove((at, v))
                if self.xn_mode == 'zhao' and not self.tongyu:
                    self.zhao_xin = min(300, self.zhao_xin + v)
        if self.holding and not self.busy():
            held = now - self.hold_at
            who = self.on_field
            if who == XN and self.xn_mode == 'ying' and self.burned_at is None and held >= 0.3:
                if self.heavy_fail is None:
                    self.heavy_fail = self.fail_once('heavy')
                if self.ying >= 85 and not self.heavy_fail:
                    self.ying = 0
                    self.burned_at = now
                    self.r1_unlock = now + 2.06
                    self.lock_until = now + 2.2
                    self.add_con(XN, 0.1)
                    rec('心步红尘出手')
                elif not self.normal_heavy_done:
                    self.normal_heavy_done = True
                    self.ying = min(100, self.ying + 8)
                    rec(f'心普通重击(应世心{self.ying})')
            if who == XN and self.xn_mode == 'zhao' and held >= 0.3:
                if not getattr(self, 'lin_checked', False):
                    self.lin_checked = True
                    self.lin_block = self.fail_once('lin')
                if self.tongyu and not self.lin_block and self.zhao_xin == 0 and held >= 0.45:
                    self.tongyu = False
                    self.lin_unlocked = True
                    self.hide(2.0)
                    self.add_con(XN, 0.15)
                    rec('心临寰宇出手')
        if self.r1_unlock and now >= self.r1_unlock and not self.r1_unlocked:
            self.r1_unlocked = True
            rec('心转相解锁')

    def step_ok(self, who, gap):
        now = time.time()
        if now - self.last_step[who] < gap:
            return False
        self.last_step[who] = now
        return True

    # ---------- 输入 ----------
    def press(self, key, down_time):
        now = time.time()
        self.tick()
        if key == 'f':
            if BREAK and self.on_field == XN and self.tongyu and now >= self.break_cd:
                self.break_cd = now + 20.0
                self.hide(1.2)
                rec('心处决')
            return
        if key in ('1', '2', '3'):
            dst = int(key) - 1
            if dst == self.on_field or self.pending:
                return
            if now < self.no_switch_until or not self.hud_visible() or now < self.avail_at[dst]:
                return
            if dst == SU and ('suback', self.cycle) in self.fail_used and not getattr(self, 'suback_done', False):
                self.suback_done = True
                self.avail_at[SU] = now + 3.0
                return
            if dst == XN and getattr(self, 'sw_block_until', 0) > now:
                return
            if dst == XN and self.fail_once('sw'):
                self.sw_block_until = now + 2.8
                return
            self.pending = (dst, now + 0.08)
            return
        if key in ('space', 'w', 'lshift'):
            return
        if not self.hud_visible() or self.busy():
            return
        who = self.on_field
        if key == 'e':
            if who == SU:
                if self.shui >= 120 and now >= self.qiang_until and 'sue1' not in FAILS and self.fail_once('sueeat'):
                    return
                if self.shui >= 120 and now >= self.qiang_until and 'sue1' not in FAILS:
                    self.shui = 0
                    self.fang = 0
                    self.qiang_until = now + 15.0
                    self.su_qiang_cast_at = now
                    self.lock_until = now + 0.3
                    self.add_con(SU, 0.30)
                    rec('穗醒春潮(进濯雨时)')
                elif now >= self.e_cd[SU]:
                    self.e_cd[SU] = now + 6.0
                    if now < self.qiang_until:
                        self.fang += 100
                        rec('穗E(濯雨时)')
                    else:
                        self.shui += 40
                        rec('穗E(浣尘时)')
                    self.lock_until = now + 0.3
                    self.add_con(SU, 0.06)
                return
            if who == LEI:
                if self.surge >= 120:
                    if down_time > 0.3:
                        rec('!!雷主长按E(临界共鸣, 扣 60 协奏)')
                        return
                    if self.fail_once('oeat'):
                        return
                    self.surge = 0
                    self.e_cd[LEI] = now + 25.0
                    self.overload_until = now + 2.0
                    self.lock_until = now + 2.0
                    self.add_con(LEI, 0.15)
                    rec('雷超负荷(短按)')
                elif now >= self.e_cd[LEI]:
                    self.e_cd[LEI] = now + 10.0
                    self.surge = min(120, self.surge + 20)
                    self.lock_until = now + 0.35
                    self.add_con(LEI, 0.08)
                    self.lei_air_from = now + 0.40
                    self.lei_land_at = now + 0.40 + 1.5          # 不按 A 自然落地
                    rec(f'雷雷引(电涌{self.surge})')
                return
            if who == XN:
                if self.xn_mode == 'zhao' and not self.tongyu and self.zhao_xin >= 300:
                    self.tongyu = True
                    self.lock_until = now + 0.4
                    rec('心万阙连衡(进统御众机)')
                elif self.xn_mode == 'zhao' and now >= self.e_cd[XN]:
                    self.e_cd[XN] = now + 20.0
                    if self.huozi and not self.fail_once('e1miss'):
                        self.zhao_xin = min(300, self.zhao_xin + 150)
                        self.zhao_due.append((now + 0.6, 300))
                        rec('心照世相E(打碎活字心锁)')
                    else:
                        self.zhao_xin = min(300, self.zhao_xin + 60)
                        rec('心照世相E(没活字心锁)')
                    self.huozi = False
                    self.lock_until = now + 0.5
                    self.add_con(XN, 0.1)
                elif self.xn_mode == 'zhao' and self.tongyu:
                    rec('!!心统御众机里按了E')
                elif self.xn_mode == 'ying' and getattr(self, 'r2_done', False):
                    rec('!!心万阙垂天之后按了E(结算掉电磁效应)')
                return
        elif key == 'q':
            rec(f'{NAMES[who]}Q')
            self.add_con(who, 0.05)
        elif key == 'r':
            if who == SU and now >= self.r_cd[SU]:
                self.r_cd[SU] = now + 25
                self.hide(4.3)
                self.add_con(SU, 0.2 if 'sucon' not in FAILS or (('sucon', self.cycle) in self.fail_used)
                             else (self.fail_once('sucon') and 0.0))
                rec(f'穗R(芳菲信{self.fang})')
            elif who == LEI and now >= self.r_cd[LEI]:
                self.r_cd[LEI] = now + 25
                self.hide(3.8)
                self.add_con(LEI, 0.2)
                rec('雷R')
            elif who == XN:
                if self.xn_mode == 'ying' and self.r1_unlocked and now < self.r1_block_until:
                    pass
                elif self.xn_mode == 'ying' and self.r1_unlocked and self.fail_once('r1'):
                    self.r1_block_until = now + 2.5
                elif self.xn_mode == 'ying' and self.r1_unlocked:
                    self.r1_unlocked = False
                    self.r1_unlock = None
                    self.burned_at = None
                    self.xn_mode = 'zhao'
                    self.zhao_xin = 0
                    self.r2_done = False
                    self.hide(4.3, flick=(0.55, 3.6))
                    rec('心转相')
                elif self.xn_mode == 'zhao' and self.lin_unlocked:
                    self.lin_unlocked = False
                    self.xn_mode = 'ying'
                    self.ying = 0
                    self.r2_done = True
                    self.hide(5.0)
                    self.add_con(XN, 0.15)
                    rec('心万阙垂天')
                    if 'hudlost' in FAILS and self.cycle == 1:
                        self.hud_dead = True
                        rec('!!关卡结束(HUD 没了)')
                elif self.xn_mode == 'zhao':
                    rec('!!心借相(按早了)')

    def tap(self):
        self.tick()
        if not self.hud_visible() or self.busy():
            return
        who = self.on_field
        now = time.time()
        if who == SU:
            if not self.step_ok(SU, 0.40):
                return
            self.add_con(SU, 0.05)
            if 'sueslow' in FAILS and self.cycle == 0 and now - self.arrived_at < 4.0:
                return
            if now < self.qiang_until:
                self.fang += 60 if 'fangslow' in FAILS else 142
            else:
                self.shui += 41
        elif who == LEI:
            if self.lei_air_from and self.lei_air_from <= now < self.lei_land_at and not getattr(self, 'plunged', False):
                self.plunged = True
                if 'noplunge' in FAILS:
                    return
                self.lei_land_at = now + 0.45
                self.surge = min(120, self.surge + 15)
                rec('雷空中A(下落)')
                return
            if not self.step_ok(LEI, 0.30):
                return
            self.surge = min(120, self.surge + 10)
            self.add_con(LEI, 0.03)
        elif who == XN:
            if not self.step_ok(XN, 0.16):
                return
            self.add_con(XN, 0.03)
            if self.xn_mode == 'ying':
                self.ying_hits.append((now + 0.3, 13))
            elif self.tongyu:
                self.zhao_xin = max(0, self.zhao_xin - 10)        # 实机普攻打空照世心要 ~5.2s
            else:
                if not self.huozi and now >= self.e_cd[XN]:
                    self.huozi = True
                    rec('心A1(活字心锁)')
                self.zhao_due.append((now + 0.2, 6))


G = Game()


class FakeTask:
    def __init__(self):
        self.executor = FakeExecutor()
        self.chars = []
        self.key_config = {'Echo Key': 'q', 'Liberation Key': 'r', 'Resonance Key': 'e',
                           'Jump Key': 'space', 'Dodge Key': 'lshift'}
        self.skip_combat_check = False
        self.use_liberation = True
        self.in_liberation = False
        self._f_last_press = -1
        self.frame = None
        self.enabled = True
        self.can_break = False

    def send_key(self, key, down_time=0.02, interval=-1, after_sleep=0):
        key = str(key)
        end = time.time() + max(down_time, 0.003)
        G.press(key, down_time)
        left = end - time.time()
        if left > 0:
            time.sleep(left)

    def send_key_down(self, key, after_sleep=0):
        pass

    def send_key_up(self, key, after_sleep=0):
        pass

    def jump(self, after_sleep=0.01):
        pass

    def mouse_down(self, *a, **kw):
        if kw.get('key') == 'right':
            rec(f'闪避({NAMES[G.on_field]})')
            return
        G.tick()
        if not G.holding:
            G.holding = True
            G.hold_at = time.time()
            G.normal_heavy_done = False
            G.heavy_fail = None
            G.lin_checked = False
            G.lin_block = False
        time.sleep(0.002)

    def mouse_up(self, *a, **kw):
        if kw.get('key') == 'right':
            return
        if G.holding and time.time() - G.hold_at < 0.25:
            G.tap()
        G.tick()
        G.holding = False

    def next_frame(self):
        time.sleep(0.03)
        G.tick()

    def in_team(self):
        return (G.hud_visible(), G.on_field, 3) if G.hud_visible() else (False, -1, 0)

    def get_current_con(self):
        G.tick()
        return G.con[G.on_field]

    def get_cd(self, name, index=None):
        return max(0.0, G.e_cd[G.on_field] - time.time()) if name == 'resonance' else 0.0

    def find_e_forte(self):
        return G.on_field == LEI and G.hud_visible() and time.time() < G.overload_until

    def find_one(self, name, threshold=0.0, **kw):
        name = str(name)
        if name in ('f_break_full', 'f_break'):
            return (BREAK and G.hud_visible() and G.on_field == XN and G.tongyu and time.time() >= G.break_cd) or None
        if not G.hud_visible():
            return None
        if G.on_field == SU:
            if name.endswith('suisui_e1'):
                return (G.shui >= 120 and time.time() >= G.qiang_until and 'sue1' not in FAILS) or None
            if name.endswith('suisui_forte3'):
                return (time.time() < G.qiang_until and G.fang >= 600) or None
            return None
        if G.on_field != XN:
            return None
        if name == 'hsin_h1':
            return (G.xn_mode == 'ying' and G.ying >= 100 and G.burned_at is None) or None
        if name == 'hsin_lib1':
            return G.xn_mode == 'ying' or None
        if name == 'hsin_lib2':
            return (G.xn_mode == 'zhao' and G.lin_unlocked) or None
        return None

    def add_freeze_duration(self, *a, **kw):
        pass

    def box_of_screen(self, *a, **kw):
        return None

    def is_pick_f(self):
        return False

    def available(self, name, check_color=True, check_cd=True):
        who = G.on_field
        now = time.time()
        if name == 'liberation':
            if who == XN:
                return (G.xn_mode == 'ying' and G.r1_unlocked) or G.xn_mode == 'zhao'
            return now >= G.r_cd[who]
        if name == 'resonance':
            if who == LEI and G.surge >= 120:
                return True                             # 电涌满 E 换成超负荷, 雷引 CD 不挡
            return G.e_cd[who] <= now
        if name == 'echo':
            return True
        return False

    def has_cd(self, name, index=None):
        return False

    def wait_until(self, *a, **kw):
        return True

    def get_resonance_key(self):
        return 'e'

    def get_echo_key(self):
        return 'q'

    def get_liberation_key(self):
        return 'r'

    def find_mouse_forte(self):
        return False


task = FakeTask()

from src.char.BaseChar import CharType  # noqa: E402
from src.char import CustomCharLoader as L  # noqa: E402
from src.char.Hsin import Hsin as NHsin  # noqa: E402
from src.char.Rover import Rover as NRover  # noqa: E402
from src.char.Suisui import Suisui as NSuisui  # noqa: E402

team = ('Hsin', 'Rover', 'Suisui')
CXn = L.load_team_char_class(NHsin, team)
CLei = L.load_team_char_class(NRover, team)
CSu = L.load_team_char_class(NSuisui, team)
assert CXn is not NHsin and CLei is not NRover and CSu is not NSuisui, 'custom team code not loaded'


class Logger:
    def info(self, m):
        rec(f'[info] {m}')

    def warning(self, m):
        rec(f'[WARN] {m}')

    def debug(self, m):
        pass

    def error(self, m):
        rec(f'[ERR] {m}')


def build(cls, index, name, char_type):
    c = object.__new__(cls)
    c.task = task
    c.index = index
    c.char_name = name
    c.logger = Logger()
    c._char_type = char_type

    c.is_current_char = index == XN
    c.has_intro = False
    c.has_sub_dps_intro = False
    c.current_con = 0
    c.last_switch_in_time = 0
    c.last_switch_time = 0
    c.last_outro_time = 0
    c._buff_time = 0
    c.last_buff_time = 0
    c.intro_motion_freeze_duration = 0.9
    c.check_f_on_switch = False
    c.last_res = c.last_liberation = c.last_echo = 0
    c._resonance_available = c._echo_available = c._liberation_available = False
    c.freeze_durations = []
    c.ring_index = -1
    c._last_known_form = -1
    if cls is CXn:
        c.__dict__.update(dict(opener_armed=True, last_opener=-1, macro_t0=0.0, macro_marks=[], cur=None,
                               holding_attack=False, si_holding=False, switch_press_at=0.0, lib_press_at=0.0,
                               loop_count=0, hud_seen_at=0.0, hud_watch=False, drive_log_at=0.0,
                               timeline_logged=True, lei2_t0=0.0, lei2_pause=0.0))
    return c


xn = build(CXn, XN, 'char_hsin', CharType.MAIN_DPS)
lei = build(CLei, LEI, 'char_rover', CharType.SUB_DPS)
su = build(CSu, SU, 'char_suisui', CharType.HEALER)
task.chars = [xn, lei, su]
for c in task.chars:
    c.add_freeze_duration = lambda *a, **kw: None
    c.time_elapsed_accounting_for_freeze = lambda start, *a, **kw: time.time() - start
    c.switch_out = types.MethodType(lambda self, con_full=False: setattr(self, 'is_current_char', False), c)
xn.game_foreground = lambda: False


def gauge():
    if G.on_field != XN or G.xn_mode != 'ying' or not G.hud_visible():
        return 0.0, 0.0
    v = G.ying
    if v >= 100:
        return 0.42, 0.42          # 满了条是粉红高柱, 紫色判据读成 0.4 上下(实机)
    return min(1.0, v / 50) * 0.88, max(0.0, (v - 50) / 50) * 0.88


xn.xn_gauge = gauge


def ready_white():
    if G.on_field != LEI or not G.hud_visible() or 'readyblind' in FAILS:
        return 0.0
    if random.random() < 0.05:
        return 1.0                                       # 整屏白闪
    return 0.2 if (G.surge >= 120 or time.time() < G.overload_until) else 0.0


def echo_white():
    if G.on_field != LEI or not G.hud_visible():
        return 0.0
    if 'echocd' in FAILS:
        return 0.06                                      # 灰图标 + 白色 CD 数字, 地面空中一样
    now = time.time()
    air = G.lei_air_from is not None and G.lei_air_from <= now < G.lei_land_at
    return 0.0 if air else 0.12


xn.lei_ready_white = ready_white
xn.lei_echo_white = echo_white


def tongyu():
    if G.on_field != XN or not G.hud_visible():
        return None
    xn.hud_seen_at = time.time()
    xn._ty_score = 0.95 if G.tongyu else 0.1
    return G.tongyu


xn.xn_tongyu = tongyu


def slot_state():
    if G.on_field != XN or not G.hud_visible():
        return None
    xn.hud_seen_at = time.time()
    if not G.tongyu:
        return '?'
    return 'ready' if G.zhao_xin == 0 else 'statue'


xn.xn_slot_state = slot_state


def statue_count():
    if G.on_field != XN or not G.hud_visible() or not G.tongyu:
        return 0
    return int((300 - G.zhao_xin) // 37.5)          # 8 颗雕像, 每颗 37.5 照世心


xn.xn_statue_count = statue_count
xn.break_prompt = lambda: BREAK and G.on_field == XN and G.tongyu and time.time() >= G.break_cd and G.hud_visible()

ok = True
try:
    G.cycle = 0
    rec('==== 启动轴 ====')
    xn.drive(xn)
    for n in range(DRY_LOOPS):
        G.cycle = n + 1
        rec(f'==== 循环 #{n + 1} ====')
        cur = next((c for c in task.chars if c.index == G.on_field), xn)
        xn.drive(cur)
        if G.hud_dead:
            break
except Exception:
    import traceback
    ok = False
    rec('!!EXCEPTION ' + traceback.format_exc())
for t, w in LOG:
    print(f'{t:7.2f}  {w}')
print('OK' if ok else 'FAILED')
