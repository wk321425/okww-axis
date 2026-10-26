"""自定义队伍代码的静态检查 —— 改完代码、干跑之前/分享之前跑一遍。

查的都是【实机才会炸、或者静默失效】的东西:
  1. 目录名 = 三个类名 casefold 排序后用 __ 连接(排错了框架直接忽略这个队, 不报错)
  2. 每个 .py 有顶层 class <文件名>, 能编译, 加载后是 BaseChar 子类
  3. 名字解析: 文件里出现的每个 self.X 都能在类/父类/实例赋值里找到
     (ast.parse 挡不住"删方法时把隔壁方法一起删了", 实机跑到那一行才 AttributeError)
  4. 自定义 __init__ 里改了内置也有的字段、但 reset_state 没重申 -> 换类时会被 __dict__.update 打回内置值
  5. 存图调用(screenshot / imencode / tofile / imwrite)和调试开关 —— 定稿前要全部关掉
  6. 写死的像素坐标(frame[123:456] / Box(数字...)) —— 2K/1K 都要能跑
  7. team.json 字段齐全、team 字段是英文显示名按字母序
  8. 引用了别的角色的内置专有方法 -> 提示加签名适配层(别人的版本可能改了签名)

用法(用 ok-ww 自带 python):
  python check_team.py <队伍目录 或 队伍key, 如 Hsin__Rover__Suisui>
退出码: 有 ERROR 返回 1。WARN 要人看一眼, 不一定是错。
"""
import ast
import importlib.util
import inspect
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import okww_paths  # noqa: E402

errors, warns, infos = [], [], []


def err(msg):
    errors.append(msg)


def warn(msg):
    warns.append(msg)


def info(msg):
    infos.append(msg)


def self_attr_names(tree, ctx_type):
    """所有 self.X(按 ctx 过滤)的 (X, 行号)。"""
    out = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id == 'self' and isinstance(node.ctx, ctx_type)):
            out.append((node.attr, node.lineno))
    return out


def stores_in_func(func_node):
    return {n for n, _ in self_attr_names(func_node, ast.Store)}


def class_init_stores(cls):
    """cls 自己的 __init__ 源码里 self.X = 的名字(只看这一层)。"""
    init = cls.__dict__.get('__init__')
    if init is None:
        return set()
    try:
        src = inspect.getsource(init)
        tree = ast.parse(inspect.cleandoc('\n' + src) if src.startswith((' ', '\t')) else src)
    except Exception:
        try:
            import textwrap
            tree = ast.parse(textwrap.dedent(inspect.getsource(init)))
        except Exception:
            return set()
    return stores_in_func(tree)


def mro_instance_attrs(cls):
    """沿 MRO 把每一层 __init__ 里赋值的实例字段都收集起来。"""
    names = set()
    for k in cls.__mro__:
        if k is object:
            continue
        names |= class_init_stores(k)
        # 别的方法里也可能挂实例字段(reset_state 之类), 粗略收一遍
        try:
            import textwrap
            tree = ast.parse(textwrap.dedent(inspect.getsource(k)))
            names |= {n for n, _ in self_attr_names(tree, ast.Store)}
        except Exception:
            pass
    return names


def load_class(path, class_name):
    spec = importlib.util.spec_from_file_location(f'okww_check_{class_name}', str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, class_name)


def check_file(path, base_char_cls, task_cls):
    name = path.stem
    text = path.read_text(encoding='utf-8')
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as e:
        err(f'{path.name}: 语法错误 {e}')
        return None
    top_classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    if name not in top_classes:
        err(f'{path.name}: 没有顶层 class {name}(框架校验会拒绝加载)')
        return None
    try:
        compile(tree, str(path), 'exec')
    except Exception as e:
        err(f'{path.name}: 编译失败 {e}')
        return None

    try:
        cls = load_class(path, name)
    except Exception as e:
        err(f'{path.name}: 加载失败 {type(e).__name__}: {e}')
        return None
    if base_char_cls is not None and not issubclass(cls, base_char_cls):
        err(f'{path.name}: {name} 不是 BaseChar 子类')

    # ---- 名字解析 ----
    file_stores = {n for n, _ in self_attr_names(tree, ast.Store)}
    inst_attrs = mro_instance_attrs(cls)
    cnode = top_classes[name]
    missing = {}
    for attr, line in self_attr_names(cnode, ast.Load):
        if hasattr(cls, attr) or attr in file_stores or attr in inst_attrs:
            continue
        missing.setdefault(attr, line)
    for attr, line in sorted(missing.items(), key=lambda x: x[1]):
        err(f'{path.name}:{line}: self.{attr} 在类/父类/实例赋值里都找不到(删方法时连带删掉了? 常量只在方法里赋值?)')

    # ---- self.task.X ----
    if task_cls is not None:
        task_stores = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
                v = node.value
                if (isinstance(v, ast.Attribute) and v.attr == 'task') or (isinstance(v, ast.Name) and v.id == 'task'):
                    task_stores.add(node.attr)
        task_attrs = mro_instance_attrs(task_cls)
        seen = set()
        for node in ast.walk(cnode):
            if (isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load)
                    and isinstance(node.value, ast.Attribute) and node.value.attr == 'task'
                    and isinstance(node.value.value, ast.Name) and node.value.value.id == 'self'):
                a = node.attr
                if a in seen or hasattr(task_cls, a) or a in task_stores or a in task_attrs:
                    continue
                seen.add(a)
                warn(f'{path.name}:{node.lineno}: self.task.{a} 在 AutoCombatTask 上没找到(框架改名了? 动态挂的字段要用 getattr 带默认值)')

    # ---- __init__ 里改了内置字段, reset_state 没重申 ----
    funcs = {n.name: n for n in cnode.body if isinstance(n, ast.FunctionDef)}
    if '__init__' in funcs:
        mine = stores_in_func(funcs['__init__'])
        native = set()
        for k in cls.__mro__[1:]:
            if k is object:
                continue
            native |= class_init_stores(k)
        restated = stores_in_func(funcs['reset_state']) if 'reset_state' in funcs else set()
        for attr in sorted((mine & native) - restated):
            warn(f'{path.name}: __init__ 里改了内置也有的字段 self.{attr}, 但 reset_state 没重申 '
                 f'-> 换类时 __dict__.update 会把它打回内置值(值跟内置一样就无所谓)')

    # ---- 存图 / 调试开关 / 写死像素 ----
    for i, line in enumerate(text.splitlines(), 1):
        code = line.split('#', 1)[0]
        if not code.strip():
            continue
        if re.search(r'\bscreenshot\s*\(|imencode\s*\(|\.tofile\s*\(|imwrite\s*\(', code):
            warn(f'{path.name}:{i}: 存图调用 -> 定稿前确认挂在总开关下且开关已关: {line.strip()[:100]}')
        m = re.match(r'\s*([A-Z][A-Z0-9_]*(?:SNAP|SHOT|DEBUG|DUMP|SAVE_IMG|SAVE_FRAME)[A-Z0-9_]*)\s*=\s*True\b', code)
        if m:
            warn(f'{path.name}:{i}: 调试开关 {m.group(1)} = True(定稿要关)')
        if re.search(r'frame\s*\[\s*\d{2,}\s*:\s*\d{2,}', code) or re.search(r'\bBox\(\s*\d{2,}\s*,\s*\d{2,}', code):
            warn(f'{path.name}:{i}: 疑似写死像素坐标 -> 改用 box_of_screen_scaled(3840, 2160, ...) / 相对坐标: {line.strip()[:100]}')

    # ---- 跨类调内置专有方法 ----
    generic = set(dir(base_char_cls)) if base_char_cls is not None else set()
    for node in ast.walk(cnode):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = node.func.value
            meth = node.func.attr
            if isinstance(owner, ast.Name) and owner.id not in ('self', 'task', 'cls', 'super') and \
                    owner.id in ('cl', 'jx', 'sk', 'ph', 'za', 'ver', 'mate', 'other') and meth not in generic:
                info(f'{path.name}:{node.lineno}: {owner.id}.{meth}(...) 像是调队友的内置专有方法 -> 分享前确认走了签名适配层')
    return cls


def check_manifest(folder, class_names):
    p = folder / 'team.json'
    if not p.is_file():
        warn('team.json 不存在(日常加载不读它, 但导出/分享会报错)')
        return
    try:
        m = json.loads(p.read_text(encoding='utf-8'))
    except Exception as e:
        err(f'team.json 不是合法 JSON: {e}')
        return
    for f in ('name', 'description', 'author', 'version', 'team'):
        if not isinstance(m.get(f), str) or not m[f].strip():
            err(f'team.json 缺 {f}(导出校验会拒绝)')
    try:
        from src.char.CustomCharLoader import get_english_char_name
        want = ', '.join(sorted((get_english_char_name(c) for c in class_names), key=str.casefold))
        if m.get('team') != want:
            err(f'team.json 的 team 应为 "{want}", 现在是 "{m.get("team")}"')
    except Exception as e:
        warn(f'没法核对 team 字段({e})')
    info(f'team.json: version={m.get("version")} author={m.get("author")}')


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    arg = sys.argv[1]
    WORKING = okww_paths.find_working(hint=arg)
    folder = Path(arg) if os.path.isdir(arg) else okww_paths.teams_root(WORKING) / arg
    folder = folder.resolve()
    if not folder.is_dir():
        print(f'找不到队伍目录 {folder}')
        return 2

    sys.path.insert(0, str(WORKING))
    os.chdir(WORKING)
    base_char_cls = task_cls = None
    try:
        from src.char.BaseChar import BaseChar as base_char_cls
        from src.task.AutoCombatTask import AutoCombatTask as task_cls
        from src.char.CharFactory import char_dict
        registered = {info_['cls'].__name__ for info_ in char_dict.values()}
    except Exception as e:
        warn(f'框架导入失败, 只做语法级检查: {e}')
        registered = None

    pys = sorted(p for p in folder.glob('*.py') if not p.name.endswith('.import.py'))
    names = [p.stem for p in pys]
    if len(pys) != 3:
        err(f'目录里有 {len(pys)} 个 .py(要正好 3 个, 少一个框架就不列出这个队): {names}')
    want_dir = '__'.join(sorted(names, key=str.casefold))
    if folder.name != want_dir:
        err(f'目录名应为 {want_dir}, 现在是 {folder.name}(排错了框架静默忽略这个队)')
    if registered is not None:
        for n in names:
            if n not in registered:
                err(f'{n} 不是框架注册的类名(上游改名了? 比如 HavocRover -> Rover)')

    for p in pys:
        check_file(p, base_char_cls, task_cls)
    check_manifest(folder, names)

    for f in ('dryrun.py.tool',):
        if not (folder / f).is_file():
            info(f'没有 {f}(干跑工具建议留在队伍目录, 导出 zip 不会带上它)')

    print(f'== {folder.name} ==')
    for tag, items in (('ERROR', errors), ('WARN', warns), ('INFO', infos)):
        for m in items:
            print(f'[{tag}] {m}')
    print(f'-- {len(errors)} error, {len(warns)} warn, {len(infos)} info')
    return 1 if errors else 0


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
    sys.exit(main())
