"""找 ok-ww 的安装位置 —— skill 会分享给别人, 不能写死 F:\\ok-ww。

working 目录(里面有 src/char/CustomCharLoader.py)按这个顺序找:
  1. 环境变量 OKWW_WORKING
  2. 当前目录及其上级(在 working 或某个队伍目录里跑的时候)
  3. 当前目录下的 data/apps/ok-ww/working(在安装根目录跑的时候)
  4. 楽山机器上的默认位置 F:\\ok-ww\\data\\apps\\ok-ww\\working
"""
import os
import sys
from pathlib import Path

DEFAULT_WORKING = Path(r'F:\ok-ww\data\apps\ok-ww\working')
MARKER = Path('src') / 'char' / 'CustomCharLoader.py'


def _is_working(p):
    return p is not None and (p / MARKER).is_file()


def find_working(required=True, hint=None):
    """hint: 用户给的队伍目录之类, 先从它往上找。"""
    cands = []
    if hint and os.path.isdir(hint):
        h = Path(hint).resolve()
        cands += [h, *h.parents]
    env = os.environ.get('OKWW_WORKING')
    if env:
        cands.append(Path(env))
    cwd = Path.cwd().resolve()
    cands += [cwd, *cwd.parents]
    cands.append(cwd / 'data' / 'apps' / 'ok-ww' / 'working')
    cands.append(DEFAULT_WORKING)
    for c in cands:
        if _is_working(c):
            return c.resolve()
    if required:
        sys.exit('找不到 ok-ww 的 working 目录(里面应有 src/char/CustomCharLoader.py)。\n'
                 '设环境变量 OKWW_WORKING=<ok-ww 安装目录>\\data\\apps\\ok-ww\\working 再跑, '
                 '或者先 cd 到那个目录里。')
    return None


def teams_root(working):
    return working / 'configs' / 'custom_teams'


def install_root(working):
    """<安装根>/data/apps/ok-ww/working -> <安装根>; 不是这个结构就退到 working 的上一级。"""
    parts = working.parts
    if len(parts) >= 4 and [x.lower() for x in parts[-4:]] == ['data', 'apps', 'ok-ww', 'working']:
        return working.parents[3]
    return working.parent


def backup_root(working):
    env = os.environ.get('OKWW_BACKUP_ROOT')
    return Path(env) if env else install_root(working) / 'team_backup'


def bundled_python(working):
    """ok-ww 自带的 python(带 cv2/numpy/onnxocr), 打印用法时提示。"""
    return working.parent / 'python' / 'python.exe'
