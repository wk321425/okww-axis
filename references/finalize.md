# 定稿 / 导出 / 分享 / 备份

触发：用户说"可以了""就这样""定下来了""确认分享""导出"。这时候主动把下面的清单走完，汇报里逐项说做了什么。
**提醒备份的时机是用户说完成的那一刻**（不是我改完代码的那一刻，改完还要实机跑）；平时每轮改动别念叨。

## 清单

1. **关掉调试截图，并删掉已存的**（不用问）
   - 把截图总开关常量置 False；`check_team.py` 会列出所有 `screenshot( / imencode / tofile / imwrite` 调用，逐个确认都挂在开关下（每张 ~4MB，曾经有一处没开关、每局都往硬盘写）。
   - 删掉这一轮自己建的排查目录（`logs/<前缀>_debug/` 之类）和会话 scratchpad 里对录屏截的帧图。**只删这一轮自己建的**；别的轴的排查目录先问用户那条轴还调不调。
   - 纯文字日志（timeline/trace）照留。
2. **`check_team.py <队伍>` 0 error**，WARN 逐条确认。其中包括"裸导入椰果版专有模块"：分享出去的代码要椰果版和原版 OKWW 都能跑（见 `framework-pitfalls.md`「分享出去的兼容性」）。
3. **2K 和 1080p 都验过自算的读屏框**：拿 F8 导出的原图（`run_report.py exports`，`judge_test.py at --image` 两种分辨率一起跑）或用户 DVR 录屏（2560x1440）取几帧，用代码里同一个读屏函数分别读原图和 `cv2.resize` 到 1920x1080 的同一帧，读数要一致。
   做法：`types.SimpleNamespace(task=假task(frame), 常量…)` + 把 `ok.task.task.BaseTask.box_of_screen_scaled` 绑到假 task 上，直接调角色类的读屏方法。
   从攻略视频换算的框不算验证过（游戏区常不是全屏）。
4. **跨类调内置角色专有方法的地方过签名适配层**（别人的版本可能改了签名，改签名 `hasattr` 查不出来，到对方实机才 TypeError 停掉整条轴）：

   ```python
   import inspect

   def native_call(self, obj, name, *args, _default=None, **kwargs):
       """调内置角色的方法: 方法不在就返回默认值; 对方不认识的关键字参数丢掉(都打日志)。"""
       func = getattr(obj, name, None)
       if not callable(func):
           self.logger.warning(f'native_call: {type(obj).__name__}.{name}() 这个版本里不存在, 跳过')
           return _default
       if kwargs:
           try:
               params = inspect.signature(func).parameters
           except (TypeError, ValueError):
               params = None
           if params is not None and not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
               dropped = [k for k in kwargs if k not in params]
               if dropped:
                   self.logger.warning(f'native_call: {type(obj).__name__}.{name}() 不认识 {dropped}, '
                                       f'已丢掉 —— 退回内置默认值, 行为可能跟标定时不一样')
                   kwargs = {k: v for k, v in kwargs.items() if k in params}
       return func(*args, **kwargs)
   ```
   只调 `BaseChar` / task 通用方法的轴不需要；自己继承的那条链不用包（缺了就该炸得明显）。
   最好再拿一个故意少参数、少方法的假内置类跑一遍适配层。
5. **同步 `.import.py`**：导入过的队伍（目录里有 `<类名>.import.py`）导出的是 `.import.py` 那份，不是正在改的 `<类名>.py`。改过的文件两份都要一样（`export_team.py` 会 WARN 并按 `.import.py` 比对）。
6. **更新 team.json**：`version`（1.0.0 起，小改加次版本号 1.1.0）、`author`（楽山）、`team`（英文显示名按字母序逗号连接）、`description`。
   **description 用用户自己那种短格式**（照他写的爱琳莫 3.0.0 / 心锁莉 / 绯洛穗），用户给过旧版说明就在那份上面加，**不重写**：
   ```
   <轴名>
   样本：61爱00琳11莫
   共效：爱弥斯125 琳奈140 莫宁260
   位置：一号位… 二号位… 三号位…
   定位：【矩阵/深塔/…】（有的写「场景」，就是适用环境）
   实机已跑通/未跑通 + 实测表现（一圈多少秒、复现难度、起手建议）
   vX.Y.Z：这一版改了什么（一行，越短越好）
   提醒：画面16:9、默认键位、HUD不缩放 之类
   ```
   要简略（以前写过【流程】【本版修改】长段落，用户换回了短格式）。完整流程写进持宏者 docstring，不写进说明。
   没实机过的改动别写成"实测"。不知道的配置（链数、共效、声骸）别照视频作者的编，空着，汇报里问用户要不要补。
7. **导出 + 校验 + 备份**：
   ```bash
   F:/coco-ww/python/python.exe -X utf8 <skill>/scripts/export_team.py <队伍> 定稿v1.0 --copy-to <分享文件夹>
   ```
   它会：复制 .py（含 .import.py）+ team.json + dryrun.py.tool 到 `<安装目录>\team_backup\<日期>_<队伍>_<标签>\`（coco-ww 是 `F:\coco-ww\team_backup`）；
   用框架 `export_custom_team` 导出 zip（只含 team.json + 3 个 .py，MacroKit 自动内联）；用 `inspect_team_archive`（导入方那套校验）验；
   逐个比对 zip 和部署文件（内联过的先用框架的 `collapse_shared_modules` 收回成 import 再比）；查 zip 里有没有 coco-ww 专有模块的裸导入；有问题打 `[ERROR]` 返回 1。
   `--copy-to` 把 zip 再复制到用户放分享包的文件夹（楽山的在 memory 里记着），同名已存在就不覆盖 —— 先看那个文件夹里已有的版本，别重名。
   只想留版本不导出时加 `--no-zip`。标签别重名（脚本不覆盖已有备份）。
   **想确认原版 OKWW 能用**：解压 zip 里的持宏者文件，用原版 python（`-I`）、cwd/`sys.path` 指原版 repo，`importlib` 加载，看 `MacroKit` 和 `start_f_watch` 的 `__module__` 都是文件自己（不是 `src.combat.*`）。
8. **提醒用户备份**（具体地说）：备到 `configs/custom_teams/` **外面**（`team_backup` 已经有一份）。
   换代码的正确姿势：**把文件复制进已有文件夹，别整个文件夹搬**（整个搬过来带过一次坏 ACL，目录谁都读不了，只能 UAC 提权 `takeown`+`icacls` 拿回来；也覆盖丢过一整天的标定）。
9. **更新 memory**：这条轴的 memory（F--ok-ww 那边的 `ok-ww-*-axis.md`）记一行"<日期> 定稿分享 vX"：导出文件名、备份路径、最后几处改动是否实机过、给别人用时要改的开关。那边 MEMORY.md 索引行同步更新。
10. **不提交 configs/**：coco-ww 仓库里 `configs/` 下的队伍代码切换（内置/自定义）、测试配置、校准数据是用户本机的测试状态，定稿也不顺手提交，除非用户点名。

## 给别人用时的开关

在 team.json 描述和持宏者文件顶部写清楚哪些开关要按自己的配置改（例：`IU_QINGYUN` 只有尤诺带无常凶鹭才开、`JR_CHAIN2_OPENER` 二链才开、心要电磁模态）。
