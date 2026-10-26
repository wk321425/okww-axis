"""读「跑轴记录」插件存的每局记录(logs/axis_runs), 给排查用: 文字摘要 + 只把要看的那几帧写成小图。

用法(都用 ok-ww 自带 python 跑, <局> = latest / list 里的序号 / 文件名里的一段如 015212 / jsonl 路径 / 反馈包 zip):
  run_report.py list [N]                       最近 N 局(默认 15): 队伍、时长、结束原因、有没有画面/F8 导出
  run_report.py summary <局> [--lap 角色]      摘要 + 分圈逐段表(比同顺序圈中位数慢 1s 标 *) + 警告/报错日志 + 画面空档
  run_report.py around <局> <秒> [--span 2] [--kinds in,read,log,field,perf,mark] [--grep 字] [--max 150] [--raw-keys]
                                               这一刻前后的事件(按键/读屏读数/在场/日志), 带代码位置; 点按默认合成「点按 A ×N」
  run_report.py frame <局> <秒> [--out 目录] [--raw]
                                               那一刻的画面(960x540, 叠上前后 0.15s 读过的框) + 那几处读屏的原图小块
  run_report.py sheet <局> <起秒> <止秒> [--out 目录] [--cols 4] [--max 16]
                                               一段时间的画面拼成一张缩略图(一张图看一串动作, 比一帧帧看省)
  run_report.py exports <局>                   这局按 F8 导出的原图文件夹(2K PNG)和 judge_test 命令

秒 = 这局开打后的秒数(时间线/表格里的时间)。插件源码按 OKWW_AXIS_RECORDER > <安装根>/pr_work/axis_recorder_plugin >
working/ok_import 找; 记录目录默认 working/logs/axis_runs, 可用 OKWW_AXIS_RUNS 改。
"""
import argparse
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from okww_paths import find_working, install_root  # noqa: E402

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

LAP_SLOW = 1.0
FRAME_GAP = 0.6
BOX_WINDOW = 0.15
# BGR
BOX_COLORS = {'found': (122, 179, 61), 'missed': (30, 135, 232), 'color': (214, 92, 176), 'mark': (23, 160, 212)}
KINDS = ('in', 'read', 'log', 'field', 'perf', 'mark')


def die(message):
    # 走 stdout: stderr 在 Windows 终端按系统码页出, 中文会乱
    print(message)
    sys.exit(1)


def load_plugin(working):
    """插件的 runs.py / media.py 就是复盘页用的解析, 直接借来用, 结果和页面一致。"""
    cands = []
    env = os.environ.get('OKWW_AXIS_RECORDER')
    if env:
        cands.append(Path(env))
    cands += [install_root(working) / 'pr_work' / 'axis_recorder_plugin' / 'axis_recorder',
              working / 'ok_import' / 'axis_recorder']
    for folder in cands:
        try:
            if (folder / 'runs.py').is_file() and (folder / 'media.py').is_file():
                break
        except OSError:  # ok_import 下的目录普通进程可能读不了
            continue
    else:
        die('没找到「跑轴记录」插件的源码(要有 runs.py / media.py)。设 OKWW_AXIS_RECORDER=<插件的 axis_recorder 文件夹> 再跑;\n'
                 '没装这个插件就只能按老办法看 ok-script.log 和录屏。')
    if folder.name != 'axis_recorder':
        die(f'插件文件夹要叫 axis_recorder: {folder}')
    sys.path.insert(0, str(working))
    sys.path.insert(0, str(folder.parent))
    os.chdir(working)
    from axis_recorder import media, runs  # noqa: E402
    return runs, media


def out_dir_of(working):
    return Path(os.environ.get('OKWW_AXIS_RUNS') or working / 'logs' / 'axis_runs')


def resolve_run(arg, runs_dir, runs):
    """返回 (jsonl 路径, 它所在的记录目录)。反馈包先解压到临时目录。"""
    if arg.lower().endswith('.zip') and os.path.isfile(arg):
        target = Path(tempfile.gettempdir()) / 'okww_run_report' / Path(arg).stem
        if not target.is_dir():
            with zipfile.ZipFile(arg) as zf:
                zf.extractall(target)
        found = sorted((target / 'axis_runs').glob('*.jsonl'))
        if not found:
            die(f'反馈包里没有 axis_runs/*.jsonl: {arg}')
        print(f'(反馈包解压在 {target}, 里面还有 反馈说明.txt 和 ok-script_这一局.log)')
        return str(found[0]), str(target / 'axis_runs')
    if os.path.isfile(arg):
        return arg, os.path.dirname(os.path.abspath(arg))
    summaries = runs.list_runs(str(runs_dir))
    if not summaries:
        die(f'{runs_dir} 里没有记录')
    if arg in ('latest', 'last'):
        return summaries[0].path, str(runs_dir)
    if arg.isdigit() and int(arg) < len(summaries) and len(arg) <= 3:
        return summaries[int(arg)].path, str(runs_dir)
    hits = [s.path for s in summaries if arg in s.name]
    if len(hits) == 1:
        return hits[0], str(runs_dir)
    die(f'「{arg}」对上 {len(hits)} 局, 用 list 看序号或写长一点: ' + ', '.join(os.path.basename(h) for h in hits[:8]))


def run_exports(media, runs_dir, name):
    result = []
    for folder in sorted(media.finished_exports(runs_dir)):
        try:
            with open(os.path.join(folder, 'info.json'), encoding='utf-8') as f:
                info = json.load(f)
        except (OSError, ValueError):
            continue
        if info.get('run') == name:
            result.append((folder, info))
    return result


def cmd_list(args, runs, media, runs_dir):
    summaries = runs.list_runs(str(runs_dir))[:args.n]
    exported = {}
    for folder in media.finished_exports(str(runs_dir)):
        try:
            with open(os.path.join(folder, 'info.json'), encoding='utf-8') as f:
                run_name = json.load(f).get('run')
            exported[run_name] = exported.get(run_name, 0) + 1
        except (OSError, ValueError):
            pass
    print(f'记录目录 {runs_dir}')
    for i, s in enumerate(summaries):
        stamp = s.name[:15]
        has_media = os.path.isfile(media.media_paths(s.path)[0])
        extras = ('画面' if has_media else '无画面') + (f' F8×{exported[s.name]}' if s.name in exported else '')
        ver = s.header.get('team_ver')
        print(f"{i:>2}  {stamp[4:6]}-{stamp[6:8]} {stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}  "
              f"{s.header.get('team_dir') or '/'.join(s.team)}{' v' + ver if ver else ''}  {s.duration:.1f}s  "
              f"{s.reason}  [{extras}]  {s.name}")


def lap_slot_of(run, lap):
    if lap is None:
        return run.default_lap_slot()
    if lap.isdigit():
        return int(lap)
    for slot in run.names:
        if run.char_name(slot).lower() == lap.lower():
            return slot
    die(f'没有叫 {lap} 的角色: ' + ', '.join(run.char_name(s) for s in sorted(run.names)))


def cmd_summary(args, runs, media, runs_dir):
    run = runs.RunData(args.path)
    slot = lap_slot_of(run, args.lap)
    print(os.path.basename(args.path))
    print(runs.headline(run, slot))
    for line in runs.detail_lines(run):
        print(line)
    if slot is not None:
        columns, laps = run.lap_breakdown(slot)
        if laps:
            baselines, _ = run.lap_baselines(columns, laps)
            labels = [run.segment_label(key, columns) for key in columns]
            print(f'\n分圈(按 {run.char_name(slot)} 上场切; * = 比同顺序圈的中位数慢 {LAP_SLOW:g}s 以上):')
            print('圈  开始     ' + '  '.join(f'{label:>10}' for label in labels) + '      整圈')
            slow_list = []
            for i, (t0, total, segments) in enumerate(laps):
                medians = baselines[i]
                cells = []
                for j, key in enumerate(columns):
                    if key not in segments:
                        cells.append(f'{"-":>10}')
                        continue
                    start, duration = segments[key]
                    slow = medians is not None and medians[j] is not None and duration - medians[j] > LAP_SLOW
                    cells.append(f'{duration:>9.2f}{"*" if slow else " "}')
                    if slow:
                        slow_list.append(f'L{i + 1} {labels[j]} {start:.2f}~{start + duration:.2f}s '
                                         f'用了 {duration:.2f}s(中位 {medians[j]:.2f})')
                slow_total = medians is not None and medians[-1] is not None and total - medians[-1] > LAP_SLOW
                print(f'L{i + 1:<2} {t0:>7.2f}  ' + '  '.join(cells) + f'  {total:>8.2f}{"*" if slow_total else ""}')
            for line in slow_list:
                print('  慢: ' + line)
    warns = [e for e in run.logs if (e.get('l') or 0) >= 30]
    if warns:
        print(f'\n警告/报错日志 {len(warns)} 条:')
        for e in warns[:20]:
            print(f"{e['t']:8.2f}  {runs.describe(run, e)[1][:200]}")
    index = media.MediaIndex(args.path)
    if index.frames:
        gaps = [(a, b - a) for a, b in zip(index.times, index.times[1:]) if b - a > FRAME_GAP]
        crops = sum(len(v) for v in index.crops.values())
        print(f'\n画面 {len(index.frames)} 帧, 读屏小块 {crops} 张; 轴没取帧的空档(>{FRAME_GAP}s) {len(gaps)} 段: '
              + ', '.join(f'{a:.1f}+{d:.1f}' for a, d in gaps[:12]) + (' …' if len(gaps) > 12 else ''))
    else:
        print('\n这局没有画面(没开「整局存画面」或已超出保留局数)')
    exports = run_exports(media, args.runs_dir, os.path.basename(args.path))
    if exports:
        print('F8 导出: ' + ', '.join(f"{info['frames'][0]['t']:.2f}~{info['frames'][-1]['t']:.2f}s"
                                     for _, info in exports if info.get('frames')) + '  (exports 命令看路径)')


def cmd_around(args, runs, media, runs_dir):
    run = runs.RunData(args.path)
    kinds = set(args.kinds.split(',')) if args.kinds else set(KINDS)
    lo, hi = args.t - args.span, args.t + args.span
    items, open_down, taps = [], {}, {}
    for e in run.events:
        t0 = e.get('t', 0)
        if e.get('e') not in kinds or t0 > hi or e.get('t2', t0) < lo:
            continue
        kind, text = runs.describe(run, e)
        item = {'t': t0, 'kind': kind, 'text': text, 'src': runs.source_text(e)}
        action = e.get('a') if e.get('e') == 'in' else None
        if action in ('md', 'kd', 'mu', 'ku') and not args.raw_keys:
            # 按下+松开不到 TAP_MAX 是一下点按; 同一处代码同一个键 REPEAT_GAP 内接着点合成 ×N, 一串普攻只占一行
            key = ('m' if action in ('md', 'mu') else 'k', e.get('k'))
            if action in ('md', 'kd'):
                open_down[key] = (e, item)
            else:
                down = open_down.pop(key, None)
                if down is not None and t0 - down[0]['t'] < runs.TAP_MAX:
                    first, row = down
                    label = run.input_label(first)
                    group = taps.get(label)
                    if group is not None and first['t'] - group['t1'] <= runs.REPEAT_GAP and group['src'] == row['src']:
                        group['n'] += 1
                        group['t1'] = first['t']
                        items.remove(row)
                    else:
                        row.update(text=f'点按 {label}', n=1, t1=first['t'])
                        taps[label] = row
                    continue
        items.append(item)
    rows = []
    for item in items:
        text = item['text'] + (f" ×{item['n']} 到 {item['t1']:.2f}s" if item.get('n', 1) > 1 else '')
        line = f"{item['t']:8.3f}  {run.field_label_at(item['t'])[:16]:<16}  {item['kind']}  {text}"
        if item['src']:
            line += f"   @{item['src']}"
        if args.grep and args.grep.lower() not in line.lower():
            continue
        rows.append(line)
    print(f'{os.path.basename(args.path)}  {lo:.2f}~{hi:.2f}s  共 {len(rows)} 条'
          + (f'(只列前 {args.max} 条, 缩小 --span 或加 --kinds/--grep)' if len(rows) > args.max else ''))
    for line in rows[:args.max]:
        print(line)
    index = media.MediaIndex(args.path)
    if index.frames:
        i = index.frame_index(args.t)
        nxt = index.times[i + 1] if i + 1 < len(index.times) else None
        note = f', 下一帧 {nxt:.2f}s' if nxt is not None else ''
        if nxt is not None and nxt - index.times[i] > FRAME_GAP:
            note += '(中间轴没取帧)'
        print(f'画面: {args.t:.2f}s 对应 {index.times[i]:.2f}s 那帧{note}')


def _ascii(text):
    text = str(text)
    return text if text.isascii() else text.encode('ascii', 'replace').decode()


def _draw_boxes(cv2, image, run, t, scale):
    for e in run.events:
        if e.get('e') not in ('read', 'mark'):
            continue
        t0 = e.get('t', 0)
        if not t0 - BOX_WINDOW <= t <= e.get('t2', t0) + BOX_WINDOW:
            continue
        box, found = e.get('box'), e.get('rb')
        value = e.get('v')
        value = f'{value:.2f}' if isinstance(value, float) else value
        if e.get('e') == 'mark':
            color, label = BOX_COLORS['mark'], f"{e.get('name')}={value}"
        elif e.get('k') == 'color':
            color, label = BOX_COLORS['color'], f"{e.get('name') or 'color'} {value}"
        elif e.get('ok'):
            color, label = BOX_COLORS['found'], f"{e.get('name')} {value}"
        else:
            color, label = BOX_COLORS['missed'], f"{e.get('name')} miss"
        for rect, rect_color in ((box, color), (found, BOX_COLORS['found'])):
            if isinstance(rect, list) and len(rect) == 4:
                x, y, w, h = (int(round(v * scale)) for v in rect)
                cv2.rectangle(image, (x, y), (x + max(w, 2), y + max(h, 2)), rect_color, 1)
                if label:
                    cv2.putText(image, _ascii(label)[:40], (x, max(10, y - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.38,
                                rect_color, 1, cv2.LINE_AA)
                    label = ''


def _out(args):
    folder = Path(args.out or Path(tempfile.gettempdir()) / 'okww_run_report')
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _decode(cv2, np, index, entry):
    return cv2.imdecode(np.frombuffer(index.read(entry), np.uint8), cv2.IMREAD_COLOR)


def cmd_frame(args, runs, media, runs_dir):
    import cv2
    import numpy as np
    run = runs.RunData(args.path)
    index = media.MediaIndex(args.path)
    if not index.frames:
        die('这局没有画面')
    entry = index.frames[index.frame_index(args.t)]
    image = _decode(cv2, np, index, entry)
    size = run.header.get('size') or [image.shape[1], image.shape[0]]
    if not args.raw:
        _draw_boxes(cv2, image, run, args.t, image.shape[1] / size[0])
    folder = _out(args)
    stem = os.path.basename(args.path)[:15]
    path = folder / f'{stem}_{entry["t"]:07.2f}s.png'
    cv2.imencode('.png', image)[1].tofile(str(path))
    print(f'画面 {entry["t"]:.2f}s({image.shape[1]}x{image.shape[0]}, 原图 {size[0]}x{size[1]}): {path}')
    seen = set()
    for e in run.events:
        t0 = e.get('t', 0)
        if e.get('e') not in ('read', 'mark') or not t0 - BOX_WINDOW <= args.t <= e.get('t2', t0) + BOX_WINDOW:
            continue
        crop, exact = index.crop_for(e)
        if crop is None or id(crop) in seen:
            continue
        seen.add(id(crop))
        name = ''.join(c if c.isalnum() or c in '_-' else '_' for c in str(e.get('name')))[:40]
        crop_path = folder / f'{stem}_{crop["t"]:07.2f}s_crop_{name}.png'
        with open(crop_path, 'wb') as f:
            f.write(index.read(crop))
        when = '' if exact else f'(这段读数没变, 用的是 {crop["t"]:.2f}s 存的)'
        print(f"  原图小块 {runs.describe(run, e)[1][:80]}  框 {crop.get('box')}{when}: {crop_path}")


def cmd_sheet(args, runs, media, runs_dir):
    import cv2
    import numpy as np
    index = media.MediaIndex(args.path)
    picked = [e for e in index.frames if args.t0 <= e['t'] <= args.t1]
    if not picked:
        die('这段没有画面')
    if len(picked) > args.max:
        step = (len(picked) - 1) / (args.max - 1)
        picked = [picked[round(i * step)] for i in range(args.max)]
    cell_w = 480
    cells = []
    for entry in picked:
        image = _decode(cv2, np, index, entry)
        cell = cv2.resize(image, (cell_w, round(image.shape[0] * cell_w / image.shape[1])), interpolation=cv2.INTER_AREA)
        cv2.rectangle(cell, (0, 0), (78, 20), (0, 0, 0), -1)
        cv2.putText(cell, f"{entry['t']:.2f}s", (4, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        cells.append(cell)
    cols = min(args.cols, len(cells))
    blank = np.zeros_like(cells[0])
    rows = [np.hstack(cells[i:i + cols] + [blank] * (cols - len(cells[i:i + cols]))) for i in range(0, len(cells), cols)]
    sheet = np.vstack(rows)
    path = _out(args) / f'{os.path.basename(args.path)[:15]}_sheet_{args.t0:.1f}-{args.t1:.1f}.png'
    cv2.imencode('.png', sheet)[1].tofile(str(path))
    print(f'{len(cells)} 帧({picked[0]["t"]:.2f}~{picked[-1]["t"]:.2f}s) 拼成 {sheet.shape[1]}x{sheet.shape[0]}: {path}')


def cmd_exports(args, runs, media, runs_dir):
    run = runs.RunData(args.path)
    exports = run_exports(media, args.runs_dir, os.path.basename(args.path))
    if not exports:
        print('这局没有 F8 导出的原图')
        return
    for folder, info in exports:
        frames = info.get('frames') or []
        span = f"{frames[0]['t']:.2f}~{frames[-1]['t']:.2f}s" if frames else '?'
        print(f"{span}  {len(frames)} 张 {info.get('size')}  {folder}")
    print(f"judge_test: judge_test.py at {run.header.get('team_dir') or '<队伍目录>'} --image <上面文件夹里的 png> "
          '-e "<表达式>"(会自己再缩到 1080 跑一遍)')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('list')
    p.add_argument('n', nargs='?', type=int, default=15)
    p = sub.add_parser('summary')
    p.add_argument('run')
    p.add_argument('--lap')
    p = sub.add_parser('around')
    p.add_argument('run')
    p.add_argument('t', type=float)
    p.add_argument('--span', type=float, default=2.0)
    p.add_argument('--kinds')
    p.add_argument('--grep')
    p.add_argument('--max', type=int, default=150)
    p.add_argument('--raw-keys', action='store_true')
    p = sub.add_parser('frame')
    p.add_argument('run')
    p.add_argument('t', type=float)
    p.add_argument('--out')
    p.add_argument('--raw', action='store_true')
    p = sub.add_parser('sheet')
    p.add_argument('run')
    p.add_argument('t0', type=float)
    p.add_argument('t1', type=float)
    p.add_argument('--out')
    p.add_argument('--cols', type=int, default=4)
    p.add_argument('--max', type=int, default=16)
    p = sub.add_parser('exports')
    p.add_argument('run')
    args = parser.parse_args()

    if getattr(args, 'run', None) and os.path.isfile(args.run):
        args.run = os.path.abspath(args.run)  # load_plugin 会切到 working 目录
    working = find_working()
    runs_dir = out_dir_of(working)
    runs, media = load_plugin(working)
    if args.cmd != 'list':
        args.path, args.runs_dir = resolve_run(args.run, runs_dir, runs)
    globals()['cmd_' + args.cmd](args, runs, media, runs_dir)


if __name__ == '__main__':
    main()
