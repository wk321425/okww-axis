"""定稿: 用框架自己的 export_custom_team 导出分享包, 用 inspect_team_archive 按导入方的规矩校验,
再把 zip + 三个 .py + team.json + dryrun.py.tool 备份到 <安装目录>/team_backup/<日期>_<队伍>_<标签>/
(原版 OKWW 是 <安装根>/team_backup, coco-ww 是 <根>/team_backup; 环境变量 OKWW_BACKUP_ROOT 可以改到别处)。

备份放在 custom_teams 【外面】: 2026-08-27 整个队伍文件夹被覆盖过一次, 同目录的 .bak 跟着一起没了。

用法(用自带 python):
  python export_team.py <队伍目录 或 队伍key> <标签, 如 定稿v1.0> [--no-zip] [--copy-to 目录]
  --no-zip         只备份不导出(还没到分享那一步, 只是想留个版本)
  --copy-to 目录   导出后把 zip 再复制一份到这个目录(用户放分享包的文件夹); 同名文件已存在就不覆盖
导出前会读 team.json 里的 name/description/author/version —— 先把版本号和描述改成现行流程再跑。

coco-ww 的队伍代码会 import 公共模块(src/combat/MacroKit.py), 导出时框架把它内联进 zip(原版 OKWW 才能用),
所以 zip 里的 .py 跟部署文件不是逐字节一样: 这里用框架的 collapse_shared_modules 收回成 import 再比。
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

# 原版 OKWW 没有的 coco-ww 模块: zip 里出现裸导入 = 原版用户加载失败、整队退回内置循环
COCO_ONLY = ('src.combat.MacroKit', 'src.combat.AxisWatch', 'src.combat.FKeyStart', 'src.recorder')


def option(name):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        sys.exit(f'{name} 后面要跟一个目录')
    return None


def bare_coco_imports(code):
    """顶层(不在 try 里)的 coco-ww 专有导入。"""
    import ast
    bad = []
    for node in ast.parse(code).body:
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module \
                and node.module.startswith(COCO_ONLY):
            bad.append(f'{node.lineno}: from {node.module} import ...')
        elif isinstance(node, ast.Import):
            bad += [f'{node.lineno}: import {a.name}' for a in node.names if a.name.startswith(COCO_ONLY)]
    return bad


def main():
    copy_to = option('--copy-to')
    skip = {copy_to} if copy_to else set()
    args = [a for a in sys.argv[1:] if not a.startswith('--') and a not in skip]
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
    from src.char import CustomCharLoader as loader
    from src.char.CustomCharLoader import export_custom_team, inspect_team_archive, team_code_state, \
        TEAM_CODE_STATE_NONE
    collapse = getattr(loader, 'collapse_shared_modules', None)   # 原版 OKWW 没有, 也不会内联

    class_names = [n.split('.')[0] for n in copied if n.endswith('.py') and not n.endswith('.import.py')]
    manifest = json.loads((folder / 'team.json').read_text(encoding='utf-8'))
    imported = team_code_state(class_names) != TEAM_CODE_STATE_NONE
    if imported:
        print('[WARN] 这个队有导入过的代码(.import.py), 导出的是导入那一份, 不一定是你正在改的 <类名>.py')
    zip_path = export_custom_team(class_names, dest, manifest['name'], manifest['description'],
                                  manifest['author'], manifest['version'])
    print(f'导出 -> {zip_path}')
    inspect_team_archive(zip_path)
    print('inspect_team_archive 校验通过(导入方那套规矩)')

    bad_any = False
    with zipfile.ZipFile(zip_path) as z:
        names = sorted(z.namelist())
        print(f'  zip 内容: {names}')
        for n in names:
            if not n.endswith('.py'):
                continue
            src = folder / (n[:-3] + '.import.py' if imported else n)
            data, local = z.read(n), src.read_bytes()
            text = data.decode('utf-8')
            bad = bare_coco_imports(text)
            if bad:
                bad_any = True
                print(f'  {n}: 【有 coco-ww 专有模块的裸导入, 原版 OKWW 会加载失败】 {bad}')
            if data == local:
                print(f'  {n}: 跟 {src.name} 逐字节一致')
            elif collapse is not None and collapse(text).encode('utf-8') == local:
                print(f'  {n}: 内联了公共模块(MacroKit), 收回成 import 后跟 {src.name} 一致')
            else:
                bad_any = True
                print(f'  {n}: 【跟 {src.name} 不一致】')
    if bad_any:
        print('[ERROR] 有问题, 先别分享')
        return 1

    if copy_to:
        target_dir = Path(copy_to)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / zip_path.name
        if target.exists():
            print(f'[WARN] {target} 已存在, 没覆盖(改 team.json 的版本号再导, 或者先跟用户确认)')
        else:
            shutil.copy2(zip_path, target)
            print(f'复制 -> {target}')
    return 0


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
    sys.exit(main())
