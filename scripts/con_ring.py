"""con_ring.py — 从录屏/攻略视频读当前角色的协奏环填充比例, 两边逐格对"谁带着多少协奏进场/离场"。

用法(自带 python 跑, 结果写 UTF-8 文件再 Read):
  con_ring.py <video> <起秒> <止秒> -o out.txt [--fps 10] [--offset 0] [--edge]
    --offset: 输出时间减去它(录屏秒 -> 跑轴记录秒)
    --edge:   按 2K 解码、1° 一格, 每行多给缺口边缘角度 edge 和按它算的比例 —— 判"差 1% 到底满没满"用这个
  输出两段: 每帧一行(时间 颜色 比例 72格亮灭图), 然后按颜色连续段汇总(进场/离场/最高/第一次满)。

原理: 协奏环框和框架 get_con_box 同一个(4K 1431,1942-1557,2068, hcenter), 片源先缩到 1080;
环带半径 21~27px, 按 72 个角度格看"这一格有没有环的颜色"(色相 + 饱和度 + 亮度), 3/6/9/12 点的十字刻度格跳过。
颜色按元素: yel=衍射(今汐) red=热熔(长离) ice=冷凝(绯雪); 别的元素在 HUES 里加。

环从 3 点钟【逆时针】涨: 缺口 = 3 点钟顺时针到边缘(edge)那一段, 满 = edge 贴着 3 点刻度(~93°)。
--edge 下每格涨了多少度/360 就是协奏回收(%), 可以直接跟帧表「协奏回收」列加总对:
龙凤雪 17->26 今汐涨 ~63° = 17.4%, 和帧表 17.39 一分不差 -> 差的 0.8% 是帧表本来就不够, 不是点慢了(2026-11-12)。

坑:
- 比例接近 1 时以放大图或 --edge 为准: 缺口刚好落在 3 点刻度旁会被跳过, 读成 1.00(2026-11-12 龙凤雪 26 格实际差 ~1%)。
  要判"真满没满", 用 contile 式放大图看右侧那个小黑口还在不在。
- 协奏≈0 时读不到颜色(显示 ?), 不等于没在场; 切人时刻用 HP 数字/头像牌补。
- 切人那一两帧(环换颜色、淡入)会乱读, 甚至读成 1.000 / edge 93°; 进场离场看连续几帧, 别信单帧。
- 大招/龙喷藏 HUD、红色特效铺满时会乱读, 那几秒跳过。
- 框架 get_current_con 在特效多的格子会低读(同一刻框架 0.91、环实际 0.98), 别拿它当真值。
"""
import argparse
import subprocess
import sys

import cv2
import numpy as np

sys.path.insert(0, __import__('os').path.dirname(__file__))
from video_tool import find_ffmpeg  # 和 video_tool 同一套找 ffmpeg 的顺序(OKWW_FFMPEG -> PATH -> 安装目录 tools)

X0, Y0, X1, Y1 = 690, 947, 802, 1059
CX, CY = 746.5, 1002.5
HUES = {'yel': (18, 40, 35), 'red': (0, 14, 70), 'ice': (88, 108, 90)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('video')
    ap.add_argument('start', type=float)
    ap.add_argument('end', type=float)
    ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--fps', type=float, default=10)
    ap.add_argument('--offset', type=float, default=0.0)
    ap.add_argument('--edge', action='store_true')
    a = ap.parse_args()
    FF = find_ffmpeg() or sys.exit("找不到 ffmpeg, 设 OKWW_FFMPEG=<ffmpeg.exe>")
    k = 4 / 3 if a.edge else 1.0                      # --edge: 2K 解码, 环带半径 28~36px, 1 度一格
    sw, sh = (2560, 1440) if a.edge else (1920, 1080)
    x0, y0, x1, y1 = (int(round(v * k)) for v in (X0, Y0, X1, Y1))
    cx, cy = CX * k, CY * k
    W, H = x1 - x0, y1 - y0
    raw = subprocess.run([FF, '-v', 'error', '-ss', f'{a.start:.3f}', '-i', a.video, '-t', f'{a.end - a.start:.3f}',
                          '-vf', f'fps={a.fps},scale={sw}:{sh},crop={W}:{H}:{x0}:{y0}',
                          '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'], capture_output=True).stdout
    n = len(raw) // (W * H * 3)
    fr = np.frombuffer(raw[:n * W * H * 3], np.uint8).reshape(n, H, W, 3)
    yy, xx = np.mgrid[0:H, 0:W]
    rr = np.hypot(xx - (cx - x0), yy - (cy - y0))
    ang = (np.degrees(np.arctan2(xx - (cx - x0), -(yy - (cy - y0)))) + 360) % 360
    band = (rr >= 21.0 * k) & (rr <= 27.0 * k)
    nb = 360 if a.edge else 72
    bins = (ang // (360 / nb)).astype(int)
    tick = 2 if a.edge else 1
    skip = {int((c * nb / 360 + d) % nb) for c in (0, 90, 180, 270) for d in range(-tick, tick + 1)}
    use = [k for k in range(nb) if k not in skip]
    wedge = {b: (bins == b) & band for b in use}
    use = [b for b in use if wedge[b].any()]          # 2K 下个别 1° 格落不到像素, 跳过不算
    rows, lines = [], []
    for i in range(n):
        hsv = cv2.cvtColor(fr[i], cv2.COLOR_BGR2HSV)
        h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        best = None
        for nm, (h0, h1, s0) in HUES.items():
            m = band & (s > s0) & (v > 140) & (h >= h0) & (h <= h1)
            if nm == 'red':
                m |= band & (s > s0) & (v > 140) & (h >= 170)
            lit = [m[wedge[b]].mean() > 0.25 for b in use]
            frac = sum(lit) / len(use)
            if best is None or frac > best[1]:
                best = (nm, frac, lit)
        nm, frac, lit = best
        t = a.start + i / a.fps - a.offset
        if frac < 0.03:
            nm = '?'
        extra = ''
        if a.edge and nm != '?':
            on = dict(zip(use, lit))
            e = next((d for d in range(93, 93 + 300) if bool(on.get(d % 360, False))), None)
            if e is not None:
                frac = 1.0 - (e - 93) / 360.0          # 用边缘角度算的比例比数亮格准
                extra = f'edge {e:3d}°  '
        rows.append((t, nm, frac))
        bar = ''.join('#' if x else '.' for x in lit)
        lines.append(f'{t:7.2f}  {nm:3s}  {frac:5.3f}  {extra}' + (bar[60:200] if a.edge else bar))
    # 按颜色连续段汇总(单帧 ? 并进前一段)
    segs = []
    for t, c, f in rows:
        if c == '?' and segs:
            segs[-1][3].append((t, f))
            continue
        if segs and segs[-1][0] == c:
            segs[-1][2] = t
            segs[-1][3].append((t, f))
        else:
            segs.append([c, t, t, [(t, f)]])
    summ = ['', '== 按颜色连续段 ==']
    for c, t0, t1, vs in segs:
        v = [x for _, x in vs if x >= 0.03] or [0.0]
        full = next((t for t, x in vs if x >= 0.995), None)
        summ.append(f'{t0:7.2f}-{t1:7.2f} {c:3s} 进场 {v[0]:.2f} 离场前 {v[-1]:.2f} 最高 {max(v):.2f}'
                    + (f' 满@{full:.2f}' if full is not None else ''))
    open(a.out, 'w', encoding='utf-8').write('\n'.join(lines + summ) + '\n')
    print(a.out, n)


if __name__ == '__main__':
    main()
