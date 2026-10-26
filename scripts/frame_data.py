"""《鸣潮动作数据汇总.xlsx》查询 —— 官方动作帧表, 做轴时所有窗口的事实依据。

环境里没有 openpyxl, 直接解 xlsx 的 xml。终端码页会把中文变乱码, 所以结果【一律写 UTF-8 文件】再用 Read 看。

用法(用 ok-ww 自带 python):
  python frame_data.py find  <关键词>              [-o out.txt]   哪些 sheet / 哪些行命中
  python frame_data.py block <角色名>              [-o out.txt] [--all]   整个角色块(到下一个角色为止)
  python frame_data.py rows  <sheet序号> <起> <止> [-o out.txt] [--all]   指定行区间

  默认只输出做轴用得上的列; --all 输出全部列。
  角色名用表里的写法: 尤诺(不是优诺)、雷主/风主、男角色在「角色-男」(block 会两张表都找)。

关键列: 发生帧 / 持续帧(-1 = 长度不定) / 派生帧(什么时候能接下一个动作 —— 做轴要的是它) / 动作结束帧(演完) /
        大招回收 / 协奏回收 / 核心回收1(每个角色是不同的资源, 看块末尾「特殊能量」那格) / 中断优先级 / 位置状态。
60fps, 帧/60 = 秒。「备注」列里藏着硬规则: 「第85F前不响应输入」「隐藏HUD 持续203F」「无敌期间不能切人」...
角色块里有没有「输入缓存」这一节决定能不能预输入: 没有的角色连段按早了直接丢, 不排队。
"""
import argparse
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

XLSX_NAME = '鸣潮动作数据汇总.xlsx'   # 默认在 <working>/configs/ 下; 这张表不随 ok-ww 发, 要自己准备
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
T = '{%s}t' % NS['m']

# 第 1 列里夹着的小节标签(不是角色名)
SECTION_LABELS = {'技能类型', '伤害计算', '牵引', '输入缓存', '偏谐机制', '快速反应', '名称'}
# 做轴用得上的列(1-based, 跟表头一致)
KEY_COLS = [1, 3, 4, 5, 6, 12, 13, 14, 16, 20, 21, 22, 23, 26, 27, 28]


def col2n(c):
    n = 0
    for ch in c:
        n = n * 26 + ord(ch) - 64
    return n


class Book:
    def __init__(self, path):
        self.z = zipfile.ZipFile(path)
        self.ss = []
        root = ET.fromstring(self.z.read('xl/sharedStrings.xml'))
        for si in root.findall('m:si', NS):
            self.ss.append(''.join(t.text or '' for t in si.iter(T)))
        wb = ET.fromstring(self.z.read('xl/workbook.xml'))
        self.sheets = [s.get('name') for s in wb.find('m:sheets', NS)]
        self._cache = {}

    def load(self, i):
        if i in self._cache:
            return self._cache[i]
        r = ET.fromstring(self.z.read(f'xl/worksheets/sheet{i}.xml'))
        rows = {}
        for row in r.iter('{%s}row' % NS['m']):
            rn = int(row.get('r'))
            cells = {}
            for c in row.findall('m:c', NS):
                col = col2n(re.match(r'[A-Z]+', c.get('r')).group())
                v = c.find('m:v', NS)
                if v is None:
                    isv = c.find('m:is', NS)
                    val = ''.join(x.text or '' for x in isv.iter(T)) if isv is not None else ''
                else:
                    val = self.ss[int(v.text)] if c.get('t') == 's' else v.text
                if val not in ('', None):
                    cells[col] = val
            rows[rn] = cells
        self._cache[i] = rows
        return rows


def fmt_row(rn, cells, header, all_cols):
    cols = sorted(cells) if all_cols else [c for c in KEY_COLS if c in cells]
    parts = []
    for c in cols:
        v = str(cells[c]).replace('\n', ' / ')
        name = header.get(c, str(c))
        parts.append(f'{name}={v}')
    return f'r{rn}  ' + ' | '.join(parts)


def frames_note(cells):
    """派生帧/结束帧顺手换算成秒, 省得每次心算。"""
    out = []
    for c, label in ((12, '派生'), (14, '结束')):
        try:
            f = float(cells.get(c, ''))
            out.append(f'{label}{f / 60:.2f}s')
        except ValueError:
            pass
    return ('   (' + ', '.join(out) + ')') if out else ''


def cmd_find(book, kw, out):
    print(f'sheets: {book.sheets}', file=out)
    for i, name in enumerate(book.sheets, 1):
        try:
            rows = book.load(i)
        except KeyError:
            continue
        hits = [rn for rn, c in rows.items() if any(kw in str(v) for v in c.values())]
        if hits:
            print(f'[{i}] {name}: {len(hits)} 行, 前 30 个: {hits[:30]}', file=out)


def find_block(book, name):
    for i, sheet in enumerate(book.sheets, 1):
        if not sheet.startswith('角色-'):
            continue
        rows = book.load(i)
        seq = sorted(rows)
        start = next((rn for rn in seq if rows[rn].get(1) == name), None)
        if start is None:
            continue
        end = start
        for rn in seq:
            if rn <= start:
                continue
            first = rows[rn].get(1)
            if first and first not in SECTION_LABELS:
                break
            end = rn
        return i, start, end
    return None


def dump(book, si, a, b, out, all_cols):
    rows = book.load(si)
    header = rows.get(1, {})
    print(f'sheet [{si}] {book.sheets[si - 1]}  r{a}-r{b}', file=out)
    for rn in range(a, b + 1):
        cells = rows.get(rn)
        if not cells:
            continue
        print(fmt_row(rn, cells, header, all_cols) + frames_note(cells), file=out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['find', 'block', 'rows'])
    ap.add_argument('args', nargs='+')
    ap.add_argument('-o', '--out', default=None, help='输出文件(UTF-8)。默认 frame_data_out.txt 放在当前目录')
    ap.add_argument('--all', action='store_true', help='输出全部列')
    ap.add_argument('--xlsx', default=None, help=f'默认 <working>/configs/{XLSX_NAME}')
    a = ap.parse_args()
    out_path = a.out or os.path.abspath('frame_data_out.txt')
    xlsx = a.xlsx
    if xlsx is None:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import okww_paths
        working = okww_paths.find_working(required=False)
        xlsx = str(working / 'configs' / XLSX_NAME) if working else XLSX_NAME
    if not os.path.isfile(xlsx):
        sys.exit(f'找不到帧表 {xlsx}。这张表不随 ok-ww 发, 要自己准备一份放到 working/configs/ 下, 或者用 --xlsx 指定路径')
    book = Book(xlsx)
    with open(out_path, 'w', encoding='utf-8') as out:
        if a.cmd == 'find':
            cmd_find(book, a.args[0], out)
        elif a.cmd == 'block':
            hit = find_block(book, a.args[0])
            if hit is None:
                print(f'没找到角色块「{a.args[0]}」(第 1 列要逐字相同; 先用 find 看看表里怎么写)', file=out)
            else:
                si, s, e = hit
                dump(book, si, s, e, out, a.all)
        else:
            si, s, e = int(a.args[0]), int(a.args[1]), int(a.args[2])
            dump(book, si, s, e, out, a.all)
    print(out_path)


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
    sys.exit(main())
