r"""找 ok-ww / coco-ww 的安装位置 —— skill 会分享给别人, 不能写死 F:\ok-ww。

working 目录(里面有 src/char/CustomCharLoader.py)按这个顺序找:
  1. 环境变量 OKWW_WORKING
  2. 当前目录及其上级(在 working 或某个队伍目录里跑的时候)
  3. 当前目录下的 data/apps/ok-ww/working(在原版 OKWW 安装根目录跑的时候)
  4. 楽山机器上的默认位置: F:\coco-ww(平铺结构, 根目录就是 working), 再 F:\ok-ww\data\apps\ok-ww\working

两种目录结构:
  原版 OKWW   <安装根>/data/apps/ok-ww/working  + <安装根>/data/apps/ok-ww/python/python.exe
  coco-ww     <根> 直接就是 working(src/ ok/ configs/ logs/ python/ 都在根目录下)
"""
import os
import sys
from pathlib import Path

DEFAULT_WORKINGS = (Path(r'F:\coco-ww'), Path(r'F:\ok-ww\data\apps\ok-ww\working'))
# ffmpeg / PySceneDetect 装在旧版 OKWW 的 tools 下(coco-ww 的 tools/ 是代码, 没放这些)
LEGACY_TOOLS = Path(r'F:\ok-ww\tools')
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
    cands += DEFAULT_WORKINGS
    for c in cands:
        if _is_working(c):
            return c.resolve()
    if required:
        sys.exit('找不到 ok-ww 的 working 目录(里面应有 src/char/CustomCharLoader.py)。\n'
                 '设环境变量 OKWW_WORKING=<working 目录> 再跑(原版 OKWW 是 <安装目录>/data/apps/ok-ww/working, '
                 'coco-ww 就是安装目录本身), 或者先 cd 到那个目录里。')
    return None


def is_flat(working):
    """coco-ww 那种平铺结构: python/ 跟 src/ 在同一层。"""
    return (working / 'python' / 'python.exe').is_file()


def teams_root(working):
    return working / 'configs' / 'custom_teams'


def install_root(working):
    """原版 <安装根>/data/apps/ok-ww/working -> <安装根>; 其他结构(coco-ww、源码目录)就是 working 本身。"""
    parts = working.parts
    if len(parts) >= 4 and [x.lower() for x in parts[-4:]] == ['data', 'apps', 'ok-ww', 'working']:
        return working.parents[3]
    return working


def backup_root(working):
    env = os.environ.get('OKWW_BACKUP_ROOT')
    return Path(env) if env else install_root(working) / 'team_backup'


def tools_dirs(working):
    """找 ffmpeg.exe / pylib 的目录, 按顺序试。"""
    dirs = []
    if working:
        dirs.append(install_root(working) / 'tools')
    dirs.append(LEGACY_TOOLS)
    return dirs


def bundled_python(working):
    """自带的 python(带 cv2/numpy/onnxocr)。"""
    if is_flat(working):
        return working / 'python' / 'python.exe'
    return working.parent / 'python' / 'python.exe'
