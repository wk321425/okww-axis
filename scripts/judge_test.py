"""离线判据测试 —— 把队伍代码里的读屏判据放到录屏/截图上跑, 不开游戏、不碰键鼠。

做法跟上游 tests/TestCon.py 一样: 框架照常初始化(真的认人、真的加载自定义队伍代码), 只是截图换成塞进去的图。
另外三件事:
  - 配置目录用临时拷贝(顶层 json + 这一个队伍目录): 初始化会把首选设备改成 image 写进 devices.json,
    写到真的 configs 里下次开 ok-ww 就连不上游戏了
  - 键鼠是 DoNothingInteraction, 判据里就算调了 send_key/click 也到不了游戏
  - 录屏按时刻直接取帧(video_tool 的 ffmpeg 后端), 原分辨率和缩到 1920x1080 各跑一遍(2K/1K 都要能跑)

用法(ok-ww 自带 python; 在哪个目录跑都行, 自己找 working):
  list <队伍>                                       列出队伍代码里只带 self 的读屏方法(候选判据)
  at   <队伍> --video V --t 12.3,15.0 -e "Hsin.forte3_full()" [-e ...]
  at   <队伍> --image a.png b.png -e ...
  scan <队伍> --video V --start 10 --end 20 [--step 0.1] -e ... [-o scan.csv]
       每个采样都算, 只打印值变了的时刻(判据翻转点); 全部数值写进 csv
  <队伍> = custom_teams 下的目录名, 或能唯一匹配的一段(大小写不敏感), 比如 hsin__rover
  --res native,1080   默认两个都跑; 片源本来就是 1080 就只跑一次
  --hold-chars        认人失败(开局 HUD 不在)时用 team.json 里的三个类硬建角色, 不走识别

表达式里能用: task(AutoCombatTask) / 角色类名(Hsin、Rover ...) / c1 c2 c3(按槽位) / cur(在场的那个) / np / cv2
只调纯读屏的方法: 里面有 sleep/等待循环的会照样等(next_frame 拿到的永远是同一张图)。
"""
import argparse
import ast
import csv
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import okww_paths  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402

READ_HINTS = ('frame', 'find_one', 'find_feature', 'calculate_color_percentage', 'box_of_screen', 'get_cd',
              'get_current_con', 'available', 'has_target', 'in_team', 'ocr', 'color', 'percent', 'ratio',
              'is_', 'hud')
# 这些是跑轴/状态维护, 不是判据(do_perform 会把整条轴跑一遍)
SKIP_NAMES = {'do_perform', 'drive', 'is_in_xls', 'is_healer', 'get_switch_priority', 'opener_blocked_by',
              'game_foreground'}
SKIP_PREFIX = ('perform', 'run_', 'seg_', 'macro', 'reset', 'on_', 'switch', 'handoff')


def pick_team(working, key):
    root = okww_paths.teams_root(working)
    exact = root / key
    if exact.is_dir():
        return exact
    hits = [p for p in root.iterdir() if p.is_dir() and key.lower() in p.name.lower()]
    if len(hits) != 1:
        sys.exit(f'队伍 {key!r} 匹配到 {len(hits)} 个: {[p.name for p in hits]}')
    return hits[0]


def cmd_list(team_dir, show_all):
    for py in sorted(team_dir.glob('*.py')):
        tree = ast.parse(py.read_text(encoding='utf-8'))
        for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
            rows = []
            for fn in [n for n in cls.body if isinstance(n, ast.FunctionDef)]:
                a = fn.args
                if [x.arg for x in a.args] != ['self'] or a.vararg or a.kwonlyargs or fn.name.startswith('__'):
                    continue
                if fn.name in SKIP_NAMES or fn.name.startswith(SKIP_PREFIX):
                    continue
                body = ast.get_source_segment(py.read_text(encoding='utf-8'), fn) or ''
                reads = any(h in body for h in READ_HINTS)
                waits = any(h in body for h in ('sleep(', 'wait_until', 'send_key', 'click(', 'mouse_down', 'macro_wait'))
                if show_all or (reads and not waits):
                    doc = (ast.get_docstring(fn) or '').strip().splitlines()
                    rows.append(f'  {cls.name}.{fn.name}()  L{fn.lineno}' + (f'  # {doc[0][:60]}' if doc else '')
                                + ('  [会等待/按键]' if waits else ''))
            if rows:
                print(f'{py.name}:')
                print('\n'.join(rows))


class Offline:
    """离线起一个框架: 返回的 task 和实机里的 AutoCombatTask 一样, 只是截图来自 show(img)。"""

    def __init__(self, working, team_dir):
        self.scratch = Path(tempfile.gettempdir()) / 'okww_judge'
        self.scratch.mkdir(exist_ok=True)

        def force(func, path, _exc):   # 队伍文件可能是只读的, copy2 会把只读属性一起拷过来
            os.chmod(path, 0o666)
            func(path)

        for old in self.scratch.glob('configs_*'):
            shutil.rmtree(old, onerror=force)
        shadow = self.scratch / f'configs_{os.getpid()}'
        (shadow / 'custom_teams').mkdir(parents=True)
        for f in (working / 'configs').glob('*.json'):
            shutil.copy2(f, shadow)
        try:
            shutil.copytree(team_dir, shadow / 'custom_teams' / team_dir.name,
                            ignore=shutil.ignore_patterns('__pycache__', '*.png', '*.log'))
        except PermissionError:
            sys.exit(f'读不了 {team_dir}(拒绝访问)。这个目录多半是管理员身份的 ok-ww 建的, 普通进程没权限; '
                     f'用管理员终端跑, 或者让用户给这个目录加上 Users 读权限')

        os.chdir(working)
        sys.path.insert(0, str(working))
        # 框架的 stdout 日志 handler 在 import 时就拿走了 sys.stdout: 从 import 起就重定向, 控制台只剩我们自己的输出
        # (框架日志写进临时目录的日志文件, ERROR 仍走 stderr)。devnull 不能关, handler 一直在往里写。
        import contextlib
        self._null = open(os.devnull, 'w', encoding='utf-8')
        quiet = contextlib.redirect_stdout(self._null)
        quiet.__enter__()
        from config import config
        cfg = dict(config)
        # disable_file_log: 框架日志路径写死 logs/ok-script.log, 不关会混进实机日志
        cfg.update(trigger_tasks=[], onetime_tasks=[], check_mutex=False, analytics=None, debug=False,
                   config_folder=str(shadow), disable_file_log=True)
        from ok import OK, DoNothingInteraction, og
        from ok.device.capture_methods.base import BaseCaptureMethod

        class ArrayCapture(BaseCaptureMethod):
            name = 'offline array'

            def __init__(self, exit_event):
                super().__init__()
                self.exit_event = exit_event
                self.img = None

            def do_get_frame(self):
                return self.img

            def connected(self):
                return True

            def get_abs_cords(self, x, y):
                return x, y

        try:
            self.ok = OK(cfg)
        finally:
            quiet.__exit__(None, None, None)
        dm = self.ok.device_manager
        self.cap = ArrayCapture(dm.exit_event)
        dm.capture_method = self.cap
        dm.device_dict['image'] = {'address': '', 'imei': 'image', 'device': 'image', 'nick': 'Image',
                                   'width': 0, 'height': 0, 'capture': 'image', 'connected': True}
        dm.config['preferred'] = 'image'
        dm.interaction = DoNothingInteraction(self.cap)
        ex = self.ok.task_executor
        ex.debug_mode = True
        ex.paused = False
        if cfg.get('scene'):
            from ok.util.clazz import init_class_by_name
            ex.scene = init_class_by_name(*cfg['scene'])
        from src.task.AutoCombatTask import AutoCombatTask
        self.task = AutoCombatTask(og.executor, None)
        self.task.feature_set = self.ok.feature_set
        self.task.after_init(executor=ex, scene=ex.scene)
        self.team_dir = team_dir

    def show(self, img):
        self.cap.img = img
        frame = self.task.next_frame()
        fs = self.task.executor.feature_set
        if fs and frame is not None:
            fs.check_size(frame)

    def load_chars(self, imgs, hold):
        """imgs: 依次试着认人的帧(大招演出/切人中 HUD 不在, 认不出来就试下一张)。"""
        task = self.task
        want = self.team_dir.name.split('__')
        tried = 0
        for label, img in imgs:
            tried += 1
            self.show(img)
            if hasattr(task, 'do_reset_to_false'):
                task.do_reset_to_false()
            # 每次清空再认: 框架认人有粘性(上一次认出的人置信度高就只跟他比), 认错一次会一直错下去
            task.chars = [None, None, None]
            if task.load_chars() and sorted(type(c).__name__ for c in task.chars if c) == sorted(want):
                print(f'  在 {label} 认出队伍')
                break
        names = [type(c).__name__ if c else None for c in task.chars]
        if sorted(n for n in names if n) != sorted(want):
            if not hold:
                sys.exit(f'试了 {tried} 帧, 认人结果 {names} 跟队伍 {want} 对不上(HUD 不在/不是这一队?). '
                         f'用 --chars-at 指定一个有队伍栏的时刻, 或加 --hold-chars 硬建')
            self.build_chars(want)
        for c in task.chars:
            mod = type(c).__module__
            custom = 'ok_ww_team_' in mod
            print(f'  {c.index + 1} 号位 {type(c).__name__:<12} {"队伍代码" if custom else "内置代码(没加载到队伍目录!)"}')

    def build_chars(self, class_names):
        """不走识别: 按 team.json 的顺序直接建, 再走一遍框架自己的换队伍代码(apply_team_char_classes)。"""
        from src.char import CharFactory as cf
        order = class_names
        manifest = self.team_dir / 'team.json'
        if manifest.exists():
            try:
                team = json.loads(manifest.read_text(encoding='utf-8')).get('team') or ''
                order = [x.strip() for x in team.split(',') if x.strip()] or class_names
            except Exception:
                pass
        chars = []
        for i, name in enumerate(order):
            info = next((v for v in cf.char_dict.values() if v['cls'].__name__ == name), None)
            if info is None:
                sys.exit(f'框架里没有角色类 {name}')
            char = info['cls'](self.task, i, char_name=info['canonical_name'], char_type=cf._get_char_type(self.task, info),
                               buff_time=cf._get_buff_time(self.task, info))
            chars.append(cf._apply_char_config(self.task, char, info))
        self.task.chars = cf.apply_team_char_classes(self.task, chars) or chars
        print(f'  --hold-chars: 按 {order} 硬建(槽位按 team.json, 跟录屏里的编队不一定一样)')

    def refresh_current(self):
        """按当前帧更新在场角色; 队伍栏不在(演出/切人中)就保持上一帧的, 跟实机一样。返回这帧认没认到队伍栏。"""
        try:
            ok_, idx, _ = self.task.in_team()
        except Exception:
            return False
        if ok_:
            for c in self.task.chars:
                if c is not None:
                    c.is_current_char = c.index == idx
        return bool(ok_)

    def namespace(self):
        ns = {'task': self.task, 'np': np, 'cv2': cv2, 'cur': self.task.get_current_char()}
        for i, c in enumerate(self.task.chars):
            if c is not None:
                ns[f'c{i + 1}'] = c
                ns[type(c).__name__] = c
        return ns


def fmt(v):
    if isinstance(v, (bool, np.bool_)):
        return str(bool(v))
    if isinstance(v, (float, np.floating)):
        return f'{float(v):.3f}'
    if isinstance(v, (tuple, list)):
        return '(' + ', '.join(fmt(x) for x in v) + ')'
    if v is None:
        return 'None'
    s = str(v)
    return s if len(s) <= 60 else s[:57] + '...'


def evaluate(env, img, exprs):
    env.show(img)
    seen = env.refresh_current()
    ns = env.namespace()
    out = []
    for e in exprs:
        t0 = time.perf_counter()
        try:
            out.append(fmt(eval(e, ns)))
        except Exception as ex:
            out.append(f'ERR {type(ex).__name__}: {str(ex)[:60]}')
        if time.perf_counter() - t0 > 2:
            out[-1] += f' (算了 {time.perf_counter() - t0:.1f}s, 里面有等待?)'
    cur = ns['cur']
    name = type(cur).__name__ if cur else '-'
    return (name if seen else f'({name})'), out   # 括号 = 这帧没看到队伍栏, 沿用上一帧的在场角色


_warned = set()


def variants(img, res):
    h, w = img.shape[:2]
    full = abs(w / h - 16 / 9) < 0.01
    if not full and 'aspect' not in _warned:
        _warned.add('aspect')
        print(f'  注意: {w}x{h} 不是 16:9 整帧(裁过的排查截图?), 框架按整屏比例取框, 读数不可信')
    out = []
    for r in res:
        if r == 'native':
            out.append((f'{w}x{h}', img))
        elif r == '1080' and full and (w, h) != (1920, 1080):
            out.append(('1920x1080', cv2.resize(img, (1920, 1080), interpolation=cv2.INTER_AREA)))
    return out


def video_frames_at(video, times):
    import video_tool as vt
    for t in times:
        got = next(iter(vt.frames(video, t, t + 0.5)), None)
        if got is None:
            sys.exit(f'{video} 在 {t}s 取不到帧')
        yield got


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('list'); p.add_argument('team'); p.add_argument('--all', action='store_true')
    for name in ('at', 'scan'):
        p = sub.add_parser(name)
        p.add_argument('team')
        p.add_argument('-e', '--expr', action='append', required=True)
        p.add_argument('--video')
        p.add_argument('--res', default='native,1080')
        p.add_argument('--hold-chars', action='store_true', dest='hold')
        p.add_argument('--chars-at', type=float, default=None, help='拿这个时刻的帧认人(默认用第一个采样)')
        p.add_argument('-o', '--out')
        if name == 'at':
            p.add_argument('--t', help='逗号分隔的秒数')
            p.add_argument('--image', nargs='*')
        else:
            p.add_argument('--start', type=float, required=True)
            p.add_argument('--end', type=float, required=True)
            p.add_argument('--step', type=float, default=0.1)
    a = ap.parse_args()

    working = okww_paths.find_working()
    team_dir = pick_team(working, a.team)
    if a.cmd == 'list':
        cmd_list(team_dir, a.all)
        return
    res = [r.strip() for r in a.res.split(',') if r.strip()]

    if a.cmd == 'at':
        if a.image:
            samples = [(Path(p).name, cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR)) for p in a.image]
        elif a.video and a.t:
            ts = [float(x) for x in a.t.split(',')]
            samples = [(f'{t:.3f}', f) for t, f in video_frames_at(a.video, ts)]
        else:
            sys.exit('at 要 --video + --t, 或 --image')
        source = iter(samples)
        t0 = float(a.t.split(',')[0]) if a.video and a.t else None
    else:
        if not a.video:
            sys.exit('scan 要 --video')
        import video_tool as vt
        source = ((f'{t:.3f}', f) for t, f in vt.frames(a.video, a.start, a.end, a.step))
        samples = []
        t0 = a.start

    def chars_frames():
        if a.chars_at is not None:
            yield from ((f'{t:.3f}', f) for t, f in video_frames_at(a.video, [a.chars_at]))
            return
        yield from samples
        if a.video and t0 is not None:   # 往后每秒试一帧, 最多 60 秒
            yield from ((f'{t:.3f}', f) for t, f in video_frames_at(a.video, [t0 + k for k in range(1, 61)]))

    print(f'队伍 {team_dir.name}, 起框架(配置用临时拷贝)...')
    env = Offline(working, team_dir)
    env.load_chars(chars_frames(), a.hold)

    rows = []
    last = {}
    for label, img in source:
        for rname, im in variants(img, res):
            cur, vals = evaluate(env, im, a.expr)
            rows.append([label, rname, cur] + vals)
            if a.cmd == 'at':
                print(f'{label:>9} {rname:>10} 在场={cur:<10} ' + '  '.join(f'{e} = {v}' for e, v in zip(a.expr, vals)))
            else:
                for e, v in zip(a.expr, vals):
                    key = (rname, e)
                    if last.get(key) != v:
                        print(f'{label:>9} {rname:>10} 在场={cur:<10} {e}: {last.get(key, "-")} -> {v}')
                        last[key] = v

    # 原分辨率 vs 1080 逐个采样比对
    by_label = {}
    for r in rows:
        by_label.setdefault(r[0], {})[r[1]] = r[3:]
    diffs = []
    for label, d in by_label.items():
        if len(d) == 2:
            (ra, va), (rb, vb) = d.items()
            for e, x, y in zip(a.expr, va, vb):
                if x != y:
                    diffs.append((label, e, x, y))
    if len(res) > 1:
        if diffs:
            print(f'\n两种分辨率读数不一样的采样 {len(diffs)} 个:')
            for label, e, x, y in diffs[:20]:
                print(f'  {label:>9}  {e}: {x} vs {y}')
        else:
            print('\n两种分辨率读数一致')
    if a.out:
        with open(a.out, 'w', encoding='utf-8-sig', newline='') as fh:
            w = csv.writer(fh)
            w.writerow(['t', 'res', 'on_field'] + a.expr)
            w.writerows(rows)
        print(a.out)


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
    code = 0
    try:
        main()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (print(e.code, file=sys.stderr) or 1)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)   # 框架起了后台线程, 正常退出会卡住
