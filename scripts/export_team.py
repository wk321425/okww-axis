"""定稿: 用框架自己的 export_custom_team 导出分享包, 用 inspect_team_archive 按导入方的规矩校验,
再把 zip + 三个 .py + team.json + dryrun.py.tool 备份到 <ok-ww 安装目录>/team_backup/<日期>_<队伍>_<标签>/
(楽山机器上是 F:/ok-ww/team_backup; 环境变量 OKWW_BACKUP_ROOT 可以改到别处)。

备份放在 custom_teams 【外面】: 2026-08-27 整个队伍文件夹被覆盖过一次, 同目录的 .bak 跟着一起没了。

用法(用 ok-ww 自带 python):
  python export_team.py <队伍目录 或 队伍key> <标签, 如 定稿v1.0> [--no-zip]
  --no-zip   只备份不导出(还没到分享那一步, 只是想留个版本)
导出前会读 team.json 里的 name/description/author/version —— 先把版本号和描述改成现行流程再跑。
"""
import datetime
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import okww_paths  # noqa: E402


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    no_zip = '--no-zip' in sys.argv
    if len(args) < 2:
        print(__doc__)
        return 2
    arg, label = args[0], args[1]
    WORKING = okww_paths.find_working(hint=arg)
    BACKUP_ROOT = okww_paths.backup_root(WORKING)
    folder = Path(arg) if os.path.isdir(arg) else okww_paths.teams_root(WORKING) / arg
    folder = folder.resolve()
    if not folder.is_dir():
        print(f'找不到队伍目录 {folder}')
        return 2
    key = folder.name
    dest = BACKUP_ROOT / f'{datetime.date.today():%Y-%m-%d}_{key}_{label}'
    if dest.exists():
        print(f'备份目录已存在, 不覆盖: {dest}(换个标签)')
        return 2
    dest.mkdir(parents=True)

    copied = []
    for p in sorted(folder.iterdir()):
        if p.is_file() and (p.suffix == '.py' or p.name in ('team.json', 'dryrun.py.tool') or p.name.endswith('.tool')):
            shutil.copy2(p, dest / p.name)
            copied.append(p.name)
    print(f'备份 -> {dest}')
    print(f'  文件: {copied}')
    if no_zip:
        return 0

    sys.path.insert(0, str(WORKING))
    os.chdir(WORKING)
    from src.char.CustomCharLoader import export_custom_team, inspect_team_archive, team_code_state, \
        TEAM_CODE_STATE_NONE

    class_names = [n.split('.')[0] for n in copied if n.endswith('.py') and not n.endswith('.import.py')]
    manifest = json.loads((folder / 'team.json').read_text(encoding='utf-8'))
    if team_code_state(class_names) != TEAM_CODE_STATE_NONE:
        print('[WARN] 这个队有导入过的代码(.import.py), 导出的是导入那一份, 不一定是你正在改的 <类名>.py')
    zip_path = export_custom_team(class_names, dest, manifest['name'], manifest['description'],
                                  manifest['author'], manifest['version'])
    print(f'导出 -> {zip_path}')
    inspect_team_archive(zip_path)
    print('inspect_team_archive 校验通过(导入方那套规矩)')

    with zipfile.ZipFile(zip_path) as z:
        names = sorted(z.namelist())
        print(f'  zip 内容: {names}')
        for n in names:
            if n.endswith('.py'):
                same = z.read(n) == (folder / n).read_bytes()
                print(f'  {n}: {"跟部署文件逐字节一致" if same else "【跟部署文件不一致】"}')
    return 0


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
    sys.exit(main())
