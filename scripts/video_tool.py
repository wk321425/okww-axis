"""扒攻略视频/录屏的工具箱。

解码有两套后端(--decoder auto|ffmpeg|cv2, 默认 auto = 找得到完整版 ffmpeg 就用它):
  ffmpeg  -ss 精确跳帧(跳到第 290 秒只要零点几秒), 裁剪/缩放在 ffmpeg 里做完再传过来;
          时间 = 帧的 PTS - 文件起点, 也就是播放器里看到的时间(开头有空档的 DVR 也对)。
          找的顺序: 环境变量 OKWW_FFMPEG -> PATH 里的 ffmpeg -> <ok-ww 安装目录>/tools/ffmpeg.exe;
          必须带 select/crop/scale/showinfo 滤镜(D:\\Bili23 Downloader 那个精简版不行)。
  cv2     顺序解码 —— cv2 按 CAP_PROP_POS_FRAMES 跳帧会偏(实测早 ~22 帧)。时间 = 帧号/fps。
  视频从 0 开始的文件两套时间一致(2K60 DVR 实测 PTS 和 帧号/60 差 <=2ms)。
中文路径: cv2.imwrite 写不了, 这里一律 imencode + tofile。

用法(用 ok-ww 自带 python, 它带 cv2 + numpy + onnxocr):
  info   <视频>                                         分辨率/fps/时长
  frame  <视频> <秒> [-o a.png]                          整帧原图(先看一眼字幕/浮层/HUD 在哪, 再写裁剪)
  sheet  <视频> --start 10 --end 20 --step 0.2 [--crop x1,y1,x2,y2] [--scale 2.4] [--cols 5] -o s.png
         抽帧拼成一张带时间戳的长图, 一次 Read 读几十帧(倒计时/技能栏 CD/字幕都这么人眼读)
  freeze <视频> [--start --end] [--diff 1.0] [--min 4]   找整帧定格(作者停下来打字幕), 打印定格区间
  ocr    <视频> --crop x1,y1,x2,y2 [--step 0.2] [--scale 2.5] [--thresh 168] [--invert] [--countdown] -o o.csv
         PP-OCR 逐帧读文字; --countdown 把 MM:SS:CC 解析成秒并用【最长非增子序列】剔除错读
  keys   <视频> --layout layout.json [--ratio 0.35] -o keys.csv
         键盘/鼠标浮层: layout = {"1":[x,y,半宽], "E":[...], "LMB":[...]}; 黄色占比超过 ratio 算按下,
         同一帧 >=3 个键同时黄 = 画面泛黄(变奏闪光/大招特效), 整帧作废。输出每个键的按下/松开时刻
  slots  <视频> --boxes "x1,y1,x2,y2;x1,y1,x2,y2;x1,y1,x2,y2" [--gray 190] [--confirm 2] -o slots.csv
         右侧队伍头像的数字牌: 在场的那个【没有数字牌】, gray>阈值 占比最小的就是在场角色 -> 切人时间线
  cuts   <视频> [--crop 游戏区] [--detector adaptive|content] [--threshold X] [--countdown cd.csv] -o cuts.csv
         PySceneDetect 找剪辑点。给了 ocr --countdown 的 csv 就逐个核对倒计时: 跳了 = 真剪辑,
         连续 = 大招/变奏闪光之类的假阳性。需要 scenedetect(装在 <ok-ww 安装目录>/tools/pylib, 或 OKWW_PYLIB 指定)

通用: --start/--end 秒(默认全片), 坐标是视频像素(先 frame 看一眼; 攻略视频的游戏区常常不是全屏)。
"""
import argparse
import csv
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DECODER = 'auto'   # main() 按 --decoder 改
_FF = None         # 找过的 ffmpeg 路径, '' = 没有
_PROBE = {}


def _ff_usable(exe):
    try:
        out = subprocess.run([exe, '-hide_banner', '-filters'], capture_output=True, timeout=30).stdout
    except Exception:
        return False
    out = out.decode('utf-8', 'replace')
    return all(re.search(rf'\s{f}\s', out) for f in ('select', 'crop', 'scale', 'showinfo'))


def _okww_tools_dir():
    try:
        import okww_paths
        w = okww_paths.find_working(required=False)
        return okww_paths.install_root(w) / 'tools' if w else None
    except Exception:
        return None


def find_ffmpeg():
    global _FF
    if _FF is None:
        cands = [os.environ.get('OKWW_FFMPEG'), shutil.which('ffmpeg')]
        tools = _okww_tools_dir()
        if tools:
            cands.append(str(tools / 'ffmpeg.exe'))
        _FF = next((c for c in cands if c and os.path.isfile(c) and _ff_usable(c)), '')
    return _FF or None


def use_ffmpeg():
    if DECODER == 'cv2':
        return False
    if find_ffmpeg():
        return True
    if DECODER == 'ffmpeg':
        sys.exit('找不到能用的 ffmpeg(要带 select/crop/scale/showinfo 滤镜), 设 OKWW_FFMPEG=<ffmpeg.exe> 或改用 --decoder cv2')
    return False


def ff_probe(path):
    """{w, h, fps, duration, start(文件起点), first(第一帧视频时间)}"""
    if path in _PROBE:
        return _PROBE[path]
    if not os.path.isfile(path):
        sys.exit(f'打不开视频 {path}')
    r = subprocess.run([find_ffmpeg(), '-hide_banner', '-nostats', '-copyts', '-i', path, '-map', '0:v:0',
                        '-vf', 'showinfo', '-frames:v', '1', '-f', 'null', '-'], capture_output=True, timeout=120)
    err = r.stderr.decode('utf-8', 'replace')
    m = re.search(r'Duration: (\d+):(\d+):([\d.]+), start: (-?[\d.]+)', err)
    v = re.search(r'Stream #\S+.*?Video: (.*)', err)
    if not m or not v:
        sys.exit(f'ffmpeg 读不了 {path}:\n{err[-800:]}')
    size = re.search(r'[ ,](\d{2,5})x(\d{2,5})\b', v.group(1))
    fps = re.search(r'([\d.]+) fps', v.group(1)) or re.search(r'([\d.]+) tbr', v.group(1))
    tb = re.search(r'time_base: (\d+)/(\d+)', err)
    pts = re.search(r'\bpts: *(-?\d+)', err)
    start = float(m.group(4))
    info = {
        'w': int(size.group(1)), 'h': int(size.group(2)),
        'fps': float(fps.group(1)) if fps else 30.0,
        'duration': int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)),
        'start': start,
        'first': int(pts.group(1)) * int(tb.group(1)) / int(tb.group(2)) - start if tb and pts else 0.0,
    }
    _PROBE[path] = info
    return info


def _clamp_box(box, w, h):
    x1, y1, x2, y2 = box
    x1, x2 = max(0, min(x1, w)), max(0, min(x2, w))
    y1, y2 = max(0, min(y1, h)), max(0, min(y2, h))
    if x2 <= x1 or y2 <= y1:
        sys.exit(f'裁剪框 {box} 不在画面 {w}x{h} 里')
    return x1, y1, x2, y2


def _out_size(w, h, size, scale):
    if size:
        return int(size[0]), int(size[1])
    if scale != 1.0:
        return max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    return w, h


def _read_exact(stream, n):
    buf = bytearray(n)
    view = memoryview(buf)
    got = 0
    while got < n:
        k = stream.readinto(view[got:])
        if not k:
            return None
        got += k
    return buf


def ff_frames(path, start=0.0, end=None, step=None, crop=None, size=None, scale=1.0):
    info = ff_probe(path)
    fps = info['fps']
    x1, y1, x2, y2 = _clamp_box(crop, info['w'], info['h']) if crop else (0, 0, info['w'], info['h'])
    ow, oh = _out_size(x2 - x1, y2 - y1, size, scale)
    vf = []
    if step and step > 1.5 / fps:
        # 网格 start + k*step 上各取最近的一帧(±半帧); 选帧之后才打 showinfo, 时间一一对应
        g0 = info['start'] + start - 0.5 / fps
        vf.append(f"select='gte(t,{g0:.6f})*lt(mod(t-{g0:.6f},{step}),{1.0 / fps:.6f})'")
    if crop:
        # exact=1: 不加的话 yuv420 片子的奇数宽高/坐标会被 crop 悄悄舍成偶数, 输出比 ow*oh 小一行,
        # 按 ow*oh 读帧就错位, 时间戳一帧帧往前漂(2026-10-25 心锁守 11w 视频 35s 起扫到 170s 漂了 3.9s)
        vf.append(f'crop={x2 - x1}:{y2 - y1}:{x1}:{y1}:exact=1')
    if (ow, oh) != (x2 - x1, y2 - y1):
        flags = 'area' if ow < x2 - x1 else 'bicubic'
        vf.append(f'scale={ow}:{oh}:flags={flags}')
    vf.append('showinfo')
    args = [find_ffmpeg(), '-hide_banner', '-nostats', '-loglevel', 'info', '-copyts']
    if start > 0:
        # 提前半帧: DVR 的 PTS 有 ±1ms 抖动, 正好落在 start 上的那帧可能早一点点
        args += ['-ss', f'{max(0.0, start - 0.5 / fps):.6f}']
    args += ['-i', path, '-map', '0:v:0', '-an', '-sn', '-vf', ','.join(vf),
             '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'bgr24', 'pipe:1']
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    q = queue.Queue()
    tail = []

    def pump():
        tb = None
        for raw in proc.stderr:
            line = raw.decode('utf-8', 'replace')
            if 'Parsed_showinfo' not in line:
                tail.append(line)
                del tail[:-20]
                continue
            if tb is None:
                m = re.search(r'time_base: (\d+)/(\d+)', line)
                if m:
                    tb = int(m.group(1)) / int(m.group(2))
                    continue
            m = re.search(r'\bn: *\d+ pts: *(-?\d+)', line)
            if m and tb is not None:
                s = re.search(r'\bs: *(\d+)x(\d+)', line)
                if s and (int(s.group(1)), int(s.group(2))) != (ow, oh):
                    # 帧尺寸跟按字节切帧用的不一样 = 每一帧都错位, 时间戳会漂; 宁可停下来
                    tail.append(f'ffmpeg 出的帧是 {s.group(1)}x{s.group(2)}, 不是 {ow}x{oh}\n')
                    q.put(None)
                    return
                q.put(int(m.group(1)) * tb)
        q.put(None)

    threading.Thread(target=pump, daemon=True).start()
    n = ow * oh * 3
    got = 0
    try:
        while True:
            buf = _read_exact(proc.stdout, n)
            if buf is None:
                break
            pts = q.get(timeout=60)
            if pts is None:
                break
            t = pts - info['start']
            if end is not None and t > end + 0.5 / fps:
                break
            got += 1
            yield t, np.frombuffer(buf, np.uint8).reshape(oh, ow, 3)
    finally:
        proc.kill()
        proc.wait()
    if got == 0 and tail:
        print('ffmpeg 没出帧:\n' + ''.join(tail[-6:]), file=sys.stderr)


def frames(path, start=0.0, end=None, step=None, crop=None, size=None, scale=1.0):
    """统一入口: 产出 (秒, 帧)。crop=(x1,y1,x2,y2) 原片像素; size=(w,h) 或 scale 缩放裁剪后的图。"""
    if use_ffmpeg():
        yield from ff_frames(path, start, end, step, crop, size, scale)
        return
    for t, f in iter_frames(path, start, end, step):
        if crop:
            x1, y1, x2, y2 = crop
            f = f[y1:y2, x1:x2]
        ow, oh = _out_size(f.shape[1], f.shape[0], size, scale)
        if (ow, oh) != (f.shape[1], f.shape[0]):
            interp = cv2.INTER_AREA if ow < f.shape[1] else cv2.INTER_CUBIC
            f = cv2.resize(f, (ow, oh), interpolation=interp)
        yield t, f


def video_fps(path):
    if use_ffmpeg():
        return ff_probe(path)['fps']
    cap, fps, _ = open_video(path)
    cap.release()
    return fps


def video_size(path):
    if use_ffmpeg():
        i = ff_probe(path)
        return i['w'], i['h']
    cap, _, _ = open_video(path)
    size = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return size


def union_box(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def open_video(path):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        sys.exit(f'打不开视频 {path}')
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    return cap, fps, n


def iter_frames(path, start=0.0, end=None, step=None):
    """顺序解码, 产出 (秒, 帧)。step=None 每帧都要; 否则只 retrieve 需要的帧(其余 grab 跳过)。"""
    cap, fps, n = open_video(path)
    end = n / fps if end is None else end
    idx = 0
    next_t = start
    while True:
        t = idx / fps
        if t > end:
            break
        want = t >= start and (step is None or t + 0.5 / fps >= next_t)
        if want:
            ok, frame = cap.read()
            if not ok:
                break
            if step is not None:
                next_t += step
                while next_t <= t:
                    next_t += step
            yield t, frame
        else:
            if not cap.grab():
                break
        idx += 1
    cap.release()


def parse_box(s):
    x1, y1, x2, y2 = (int(float(v)) for v in s.split(','))
    return x1, y1, x2, y2


def save_png(img, path):
    ok, buf = cv2.imencode('.png', img)
    if not ok:
        sys.exit('编码 png 失败')
    buf.tofile(path)
    print(path)


def cmd_info(a):
    if use_ffmpeg():
        i = ff_probe(a.video)
        print(f"{i['w']}x{i['h']} {i['fps']:.3f}fps {i['duration']:.2f}s  第一帧在 {i['first']:.3f}s  (ffmpeg)")
        return
    cap, fps, n = open_video(a.video)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f'{w}x{h} {fps:.3f}fps {n} 帧 {n / fps:.2f}s  (cv2)')


def cmd_frame(a):
    for t, f in frames(a.video, a.t, a.t + 1.0):
        save_png(f, a.out or f'frame_{a.t:.2f}.png')
        print(f'实际取到 {t:.3f}s')
        return
    sys.exit('没读到帧')


def label(img, text):
    cv2.rectangle(img, (0, 0), (min(img.shape[1], 12 + 11 * len(text)), 20), (0, 0, 0), -1)
    cv2.putText(img, text, (4, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
    return img


def cmd_sheet(a):
    tiles = []
    crop = parse_box(a.crop) if a.crop else None
    for t, f in frames(a.video, a.start, a.end, a.step, crop=crop, scale=a.scale):
        tiles.append(label(f.copy(), f'{t:.2f}'))
        if len(tiles) >= a.max:
            print(f'到了 {a.max} 帧上限, 截断(调 --max 或缩小区间)')
            break
    if not tiles:
        sys.exit('区间里没有帧')
    h = max(x.shape[0] for x in tiles)
    w = max(x.shape[1] for x in tiles)
    rows = []
    for i in range(0, len(tiles), a.cols):
        row = [cv2.copyMakeBorder(x, 0, h - x.shape[0] + 2, 0, w - x.shape[1] + 2, cv2.BORDER_CONSTANT, value=(40, 40, 40))
               for x in tiles[i:i + a.cols]]
        while len(row) < a.cols:
            row.append(np.full((h + 2, w + 2, 3), 40, np.uint8))
        rows.append(np.hstack(row))
    save_png(np.vstack(rows), a.out or 'sheet.png')
    print(f'{len(tiles)} 帧, {a.cols} 列')


def cmd_freeze(a):
    prev = None
    run_start = None
    run_len = 0
    segs = []
    last_t = 0.0
    for t, f in frames(a.video, a.start, a.end, size=(160, 80)):
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
        if prev is not None:
            d = float(np.mean(np.abs(g - prev)))
            if d < a.diff:
                if run_start is None:
                    run_start = last_t
                run_len += 1
            else:
                if run_start is not None and run_len >= a.min:
                    segs.append((run_start, last_t))
                run_start, run_len = None, 0
        prev = g
        last_t = t
    if run_start is not None and run_len >= a.min:
        segs.append((run_start, last_t))
    total = sum(e - s for s, e in segs)
    for s, e in segs:
        print(f'定格 {s:8.2f} -> {e:8.2f}  ({e - s:.2f}s)')
    print(f'共 {len(segs)} 段, {total:.2f}s(算时长要扣掉; 定格期间键盘浮层一直亮着, 一次点击会读成长按)')


def prep_ocr(img, a):
    if a.scale != 1.0:
        img = cv2.resize(img, None, fx=a.scale, fy=a.scale, interpolation=cv2.INTER_CUBIC)
    if a.thresh > 0:
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, b = cv2.threshold(g, a.thresh, 255, cv2.THRESH_BINARY)
        if a.invert:
            b = 255 - b
        img = cv2.cvtColor(b, cv2.COLOR_GRAY2BGR)
    return img


CD_FULL = re.compile(r'(\d{1,2})\D(\d{2})\D(\d{2})')
CD_SHORT = re.compile(r'(\d{2})\D(\d{2})$')


def parse_countdown(text, last_minute):
    m = CD_FULL.search(text)
    if m:
        mm, ss, cc = (int(x) for x in m.groups())
        if ss < 60:
            return mm * 60 + ss + cc / 100.0, mm
    m = CD_SHORT.search(text.strip())
    if m and last_minute is not None:
        ss, cc = (int(x) for x in m.groups())
        if ss < 60:
            # 丢了分钟位(01:53:66 读成 0:53:66 / 53:66): 借上一条的分钟
            return last_minute * 60 + ss + cc / 100.0, last_minute
    return None, last_minute


def longest_non_increasing(vals):
    """倒计时必然单调不增, 破坏单调性的一定是错读 —— 别用局部中位数(会把整段正确读数误删)。"""
    import bisect
    neg = [-v for v in vals]
    tails, tails_idx, parent = [], [], [-1] * len(vals)
    for i, v in enumerate(neg):
        j = bisect.bisect_right(tails, v)
        if j == len(tails):
            tails.append(v)
            tails_idx.append(i)
        else:
            tails[j] = v
            tails_idx[j] = i
        parent[i] = tails_idx[j - 1] if j > 0 else -1
    keep = set()
    k = tails_idx[-1] if tails_idx else -1
    while k >= 0:
        keep.add(k)
        k = parent[k]
    return keep


def cmd_ocr(a):
    from onnxocr.onnx_paddleocr import ONNXPaddleOcr
    ocr = ONNXPaddleOcr(use_openvino=True)   # 环境里没装 onnxruntime, 不传会 ImportError
    rows = []
    last_minute = None
    for t, f in frames(a.video, a.start, a.end, a.step, crop=parse_box(a.crop)):
        img = prep_ocr(f, a)
        try:
            res = ocr.ocr(img)
            text = ' '.join(item[1][0] for item in (res[0] or [])) if res else ''
        except Exception:
            text = ''
        val = None
        if a.countdown:
            val, last_minute = parse_countdown(text, last_minute)
        rows.append([round(t, 3), text, val])
    if a.countdown:
        idx = [i for i, r in enumerate(rows) if r[2] is not None]
        keep = longest_non_increasing([rows[i][2] for i in idx])
        kept = {idx[k] for k in keep}
        for i, r in enumerate(rows):
            r.append(1 if i in kept else 0)
        print(f'倒计时: {len(rows)} 帧, 解析出 {len(idx)}, 单调保留 {len(kept)}')
    out = a.out or 'ocr.csv'
    with open(out, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['t_video', 'text'] + (['game_sec', 'kept'] if a.countdown else []))
        for r in rows:
            w.writerow(r if a.countdown else r[:2])
    print(out)


def yellow_ratio(patch):
    b, g, r = (patch[..., i].astype(np.int16) for i in range(3))
    m = (r > 120) & (g > 120) & (b < r - 40) & (b < g - 40)
    return float(m.mean()) if m.size else 0.0


def cmd_keys(a):
    layout = json.load(open(a.layout, encoding='utf-8'))
    state = {k: False for k in layout}
    since = {k: None for k in layout}
    events = []
    dropped = 0
    ox, oy, ox2, oy2 = union_box([(x - hw, y - hw, x + hw, y + hw) for x, y, hw in layout.values()])
    for t, f in frames(a.video, a.start, a.end, crop=(ox, oy, ox2, oy2)):
        lit = {}
        for k, (x, y, hw) in layout.items():
            lit[k] = yellow_ratio(f[y - hw - oy:y + hw - oy, x - hw - ox:x + hw - ox]) > a.ratio
        kb = [k for k, v in lit.items() if v and k not in ('LMB', 'RMB')]
        if len(kb) >= 3:
            dropped += 1
            continue
        for k, v in lit.items():
            if v and not state[k]:
                state[k], since[k] = True, t
            elif not v and state[k]:
                events.append((since[k], t, k))
                state[k] = False
    for k, v in state.items():
        if v:
            events.append((since[k], None, k))
    events.sort()
    out = a.out or 'keys.csv'
    with open(out, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['down', 'up', 'key', 'held'])
        for s, e, k in events:
            w.writerow([round(s, 3), '' if e is None else round(e, 3), k, '' if e is None else round(e - s, 3)])
    print(f'{len(events)} 次按键, 作废 {dropped} 帧(画面泛黄) -> {out}')
    print('提醒: 定格期间浮层一直亮, 先用 freeze 找定格再扣; 作者压暗画面做高亮时浮层会漏键, 关键几秒拿技能栏 CD 交叉核对')


def cmd_slots(a):
    boxes = [parse_box(s) for s in a.boxes.split(';')]
    out = a.out or 'slots.csv'
    last = None
    cand, cand_n, cand_t = None, 0, 0.0
    changes = []
    with open(out, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['t_video'] + [f'slot{i + 1}' for i in range(len(boxes))] + ['on_field'])
        ox, oy, ox2, oy2 = union_box(boxes)
        for t, f in frames(a.video, a.start, a.end, a.step, crop=(ox, oy, ox2, oy2)):
            ratios = []
            for x1, y1, x2, y2 in boxes:
                g = cv2.cvtColor(f[y1 - oy:y2 - oy, x1 - ox:x2 - ox], cv2.COLOR_BGR2GRAY)
                ratios.append(float((g > a.gray).mean()))
            on = int(np.argmin(ratios)) + 1
            # 三个都低(过场/HUD 不在)就记 0
            if sorted(ratios)[1] < a.min_other:
                on = 0
            w.writerow([round(t, 3)] + [round(r, 3) for r in ratios] + [on])
            # 连续 confirm 个采样都一样才认(切人瞬间/特效闪光会抖一两帧)
            if on == cand:
                cand_n += 1
            else:
                cand, cand_n, cand_t = on, 1, t
            if cand != last and cand_n >= a.confirm:
                changes.append((cand_t, cand))
                last = cand
    for t, on in changes:
        print(f'{t:8.2f}  -> {"HUD 不在" if on == 0 else f"{on} 号位在场"}')
    print(out)


def import_scenedetect():
    cands = [os.environ.get('OKWW_PYLIB')]
    tools = _okww_tools_dir()
    if tools:
        cands.append(str(tools / 'pylib'))
    for c in cands:
        if c and os.path.isdir(c) and c not in sys.path:
            sys.path.append(c)
    try:
        import scenedetect
        return scenedetect
    except ImportError:
        sys.exit('没装 scenedetect。装到 ok-ww 环境外面:\n'
                 '  <自带python> -m pip install --no-deps --target <ok-ww 安装目录>/tools/pylib '
                 'scenedetect "click~=8.0,!=8.3.0" platformdirs tqdm\n'
                 '(--no-deps 是为了不再装一份 opencv-python, 自带的 cv2 够用)')


def load_countdown(path):
    # 用全部解析出的读数, 不看 kept: 多段录像拼起来的视频倒计时会往上跳, 全片最长非增子序列会把别的段整段扔掉
    rows = []
    with open(path, encoding='utf-8-sig') as fh:
        for r in csv.DictReader(fh):
            if r.get('game_sec'):
                rows.append((float(r['t_video']), float(r['game_sec'])))
    return rows


def extrapolate(near, t):
    """一侧的读数: 先量倍速(两两斜率取中位数, 个别错读压得住), 再按这个倍速把每个读数推到 t 时刻取中位数。
    攻略视频常 0.25x~1x 混着剪, 按 1 倍速硬推会把慢放误判成剪辑。返回 (t 时刻的倒计时, 倍速)。"""
    g, rate, _ = extrapolate_fit(near, t)
    return g, rate


def extrapolate_fit(near, t):
    slopes = [(g1 - g2) / (t2 - t1) for i, (t1, g1) in enumerate(near) for t2, g2 in near[i + 1:] if t2 - t1 >= 0.2]
    rate = float(np.clip(np.median(slopes), 0.0, 2.0)) if len(slopes) >= 2 else 1.0
    at = [g - rate * (t - tv) for tv, g in near]
    g0 = float(np.median(at))
    return g0, rate, float(np.median(np.abs(np.array(at) - g0)))   # 最后一个 = 这一侧读数离直线多远


def countdown_jumps(cd, tol, n=6, min_gap=0.5):
    """倒计时序列自己的断点: 相邻两个读数之间, 左右各 n 个读数推到中点对不上。
    同场景接着剪(画面几乎不变)只有这条路找得到。返回 [(时刻, 跳过的游戏秒, 左倍速, 右倍速)]。
    一侧读数不在一条直线上(混进了另一段/错读多) 或倍速 >1.6(攻略视频不会快放, 是错读) 就不认。"""
    cands = []
    for i in range(4, len(cd) - 3):
        before, after = cd[max(0, i - n):i], cd[i:i + n]
        if len(before) < 4 or len(after) < 4 or after[0][0] - before[-1][0] > 3.0:
            continue
        tm = (before[-1][0] + after[0][0]) / 2
        gb, rb, sb = extrapolate_fit(before, tm)
        ga, ra, sa = extrapolate_fit(after, tm)
        if abs(gb - ga) > tol and max(sb, sa) < tol / 2 and max(rb, ra) < 1.6:
            cands.append((abs(gb - ga), tm, gb - ga, rb, ra))
    kept = []
    for c in sorted(cands, reverse=True):
        if all(abs(c[1] - k[0]) >= min_gap for k in kept):
            kept.append(c[1:])
    return sorted(kept)


def countdown_at(cd, t, window, side, n=10):
    if side < 0:
        near = [(tv, g) for tv, g in cd if t - window <= tv < t][-n:]
    else:
        near = [(tv, g) for tv, g in cd if t <= tv <= t + window][:n]
    return extrapolate(near, t) if len(near) >= 2 else (None, None)


def speed_str(rb, ra):
    return f'{rb:.2f}x' if abs(rb - ra) < 0.1 else f'{rb:.2f}x->{ra:.2f}x'


def jump_verdict(skipped, rb, ra):
    if skipped > 0:
        s = f'剪掉了 {skipped:.2f}s 游戏时间 [{speed_str(rb, ra)}]'
    else:
        s = f'倒计时多了 {-skipped:.2f}s -> 回放/换了另一段录像 [{speed_str(rb, ra)}]'
    # 1 秒以内的多半是闪光那几帧读错/读漏, 用 sheet 看一眼倒计时再信
    return s + (' (小, 可能是错读)' if abs(skipped) < 1.0 else '')


def cmd_cuts(a):
    sd = import_scenedetect()
    fps = video_fps(a.video)
    min_len = max(1, int(round(a.min_len * fps)))
    if a.detector == 'content':
        det = sd.ContentDetector(threshold=a.threshold or 27.0, min_scene_len=min_len)
    else:
        det = sd.AdaptiveDetector(adaptive_threshold=a.threshold or 3.0, min_scene_len=min_len)
    crop = parse_box(a.crop) if a.crop else None
    times, cut_idx = [], []
    n = 0
    src_w = crop[2] - crop[0] if crop else video_size(a.video)[0]
    for t, f in frames(a.video, a.start, a.end, crop=crop, scale=min(1.0, a.width / src_w)):
        times.append(t)
        cut_idx += [tc.frame_num for tc in det.process_frame(sd.FrameTimecode(n, fps=fps), f)]
        n += 1
    if n and hasattr(det, 'post_process'):
        cut_idx += [tc.frame_num for tc in det.post_process(sd.FrameTimecode(n - 1, fps=fps))]
    cuts = [times[i] for i in sorted(set(cut_idx)) if 0 <= i < len(times)]
    cd = load_countdown(a.countdown) if a.countdown else []
    jumps = [j for j in countdown_jumps(cd, a.tol) if a.start <= j[0] <= (a.end if a.end is not None else 1e9)]
    used = set()
    events = []   # (时刻, 来源, 跳过的游戏秒, 左倍速, 右倍速, 结论)
    for t in cuts:
        near = [k for k, j in enumerate(jumps) if abs(j[0] - t) <= a.match and k not in used]
        if near:
            k = min(near, key=lambda k: abs(jumps[k][0] - t))
            used.add(k)
            tj, skipped, rb, ra = jumps[k]
            events.append((t, f'画面+倒计时({tj:.2f})', skipped, rb, ra, jump_verdict(skipped, rb, ra)))
            continue
        gb, rb = countdown_at(cd, t, a.window, -1) if cd else (None, None)
        ga, ra = countdown_at(cd, t, a.window, +1) if cd else (None, None)
        if gb is None or ga is None:
            events.append((t, '画面', None, None, None, '附近没读到倒计时(片头/字幕卡/演出)' if cd else ''))
        else:
            # 附近没有倒计时断点 -> 画面变了但游戏时间是连着的
            events.append((t, '画面', gb - ga, rb, ra, f'倒计时连续 -> 不是剪辑(特效/镜头切换) [{speed_str(rb, ra)}]'))
    for k, (tj, skipped, rb, ra) in enumerate(jumps):
        if k not in used:
            events.append((tj, '只有倒计时', skipped, rb, ra, jump_verdict(skipped, rb, ra) + ' 画面看不出来(同场景接着剪)'))
    events.sort(key=lambda e: e[0])
    out = a.out or 'cuts.csv'
    with open(out, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['t_video', 'source', 'skipped', 'speed_before', 'speed_after', 'verdict'])
        for t, src, skipped, rb, ra, verdict in events:
            r2 = lambda x: '' if x is None else round(x, 2)
            w.writerow([round(t, 3), src, r2(skipped), r2(rb), r2(ra), verdict])
            print(f'{t:8.2f}  {src:<18} {verdict}')
    print(f'画面剪辑点 {len(cuts)} 个 ({a.detector}, {n} 帧)' +
          (f', 倒计时断点 {len(jumps)} 个(其中 {len(jumps) - len(used)} 个画面看不出来)' if cd else '') + f' -> {out}')
    if not cd:
        print('提醒: 打斗画面里大招/变奏闪光也会被当成剪辑点, 同场景接着剪又看不出来;'
              ' 先跑 ocr --countdown 再用 --countdown 核对')


def main():
    global DECODER
    ap = argparse.ArgumentParser()
    ap.add_argument('--decoder', choices=('auto', 'ffmpeg', 'cv2'), default='auto')
    sub = ap.add_subparsers(dest='cmd', required=True)

    def common(p, step_default=None):
        p.add_argument('video')
        p.add_argument('--start', type=float, default=0.0)
        p.add_argument('--end', type=float, default=None)
        p.add_argument('-o', '--out', default=None)
        if step_default is not False:
            p.add_argument('--step', type=float, default=step_default)

    p = sub.add_parser('info'); p.add_argument('video')
    p = sub.add_parser('frame'); p.add_argument('video'); p.add_argument('t', type=float); p.add_argument('-o', '--out')
    p = sub.add_parser('sheet'); common(p, 0.2)
    p.add_argument('--crop'); p.add_argument('--scale', type=float, default=1.0)
    p.add_argument('--cols', type=int, default=5); p.add_argument('--max', type=int, default=120)
    p = sub.add_parser('freeze'); common(p, False)
    p.add_argument('--diff', type=float, default=1.0); p.add_argument('--min', type=int, default=4)
    p = sub.add_parser('ocr'); common(p, 0.2)
    p.add_argument('--crop', required=True); p.add_argument('--scale', type=float, default=2.5)
    p.add_argument('--thresh', type=int, default=168); p.add_argument('--invert', action='store_true')
    p.add_argument('--countdown', action='store_true')
    p = sub.add_parser('keys'); common(p, False)
    p.add_argument('--layout', required=True); p.add_argument('--ratio', type=float, default=0.35)
    p = sub.add_parser('slots'); common(p, 0.1)
    p.add_argument('--boxes', required=True); p.add_argument('--gray', type=int, default=190)
    p.add_argument('--min-other', type=float, default=0.05, dest='min_other')
    p.add_argument('--confirm', type=int, default=2, help='连续几个采样一致才认切人')
    p = sub.add_parser('cuts'); common(p, False)
    p.add_argument('--crop', help='只看游戏区(攻略视频边上的字幕/浮层会干扰)')
    p.add_argument('--detector', choices=('adaptive', 'content'), default='adaptive')
    p.add_argument('--threshold', type=float, default=None, help='adaptive 默认 3.0, content 默认 27')
    p.add_argument('--min-len', type=float, default=0.5, dest='min_len', help='两个剪辑点至少隔几秒')
    p.add_argument('--width', type=int, default=320, help='缩到多宽再比(越小越快)')
    p.add_argument('--countdown', help='ocr --countdown 产出的 csv, 用来核对每个剪辑点倒计时有没有跳')
    p.add_argument('--window', type=float, default=3.0, help='剪辑点前后多少秒内找倒计时读数')
    p.add_argument('--tol', type=float, default=0.3, help='两侧推算的倒计时差多少秒以内算连续')
    p.add_argument('--match', type=float, default=1.0, help='画面剪辑点和倒计时断点相距多少秒以内算同一个')
    a = ap.parse_args()
    DECODER = a.decoder
    {'info': cmd_info, 'frame': cmd_frame, 'sheet': cmd_sheet, 'freeze': cmd_freeze,
     'ocr': cmd_ocr, 'keys': cmd_keys, 'slots': cmd_slots, 'cuts': cmd_cuts}[a.cmd](a)


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
    main()
