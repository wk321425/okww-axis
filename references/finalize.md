# 定稿 / 导出 / 分享 / 备份

触发：用户说"可以了""就这样""定下来了""确认分享""导出"。这时候主动把下面的清单走完，汇报里逐项说做了什么。
**提醒备份的时机是用户说完成的那一刻**（不是我改完代码的那一刻，改完还要实机跑）；平时每轮改动别念叨。

## 清单

1. **关掉调试截图，并删掉已存的**（不用问）
   - 把截图总开关常量置 False；`check_team.py` 会列出所有 `screenshot( / imencode / tofile / imwrite` 调用，逐个确认都挂在开关下（每张 ~4MB，曾经有一处没开关、每局都往硬盘写）。
   - 删掉这一轮自己建的排查目录（`logs/<前缀>_debug/` 之类）和会话 scratchpad 里对录屏截的帧图。**只删这一轮自己建的**；别的轴的排查目录先问用户那条轴还调不调。
   - 纯文字日志（timeline/trace）照留。
2. **`check_team.py <队伍>` 0 error**，WARN 逐条确认。
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
5. **更新 team.json**：`version`（1.0.0 起，小改 1.1.0）、`description` 改成**现行流程**（启动轴/循环轴/保底各一段，写清对用户配置的要求：共鸣模态、链数、声骸、16:9、默认键位、"切人按角色不按编队"）、`author`、`team`（英文显示名按字母序逗号连接）。
   也把同样的流程写进持宏者 docstring。
6. **导出 + 校验 + 备份**：
   ```bash
   F:/ok-ww/data/apps/ok-ww/python/python.exe ~/.claude/skills/okww-axis/scripts/export_team.py <队伍> 定稿v1.0
   ```
   它会：复制三个 .py + team.json + dryrun.py.tool 到 `F:\ok-ww\team_backup\<日期>_<队伍>_<标签>\`；
   用框架 `export_custom_team` 导出 zip（只含 team.json + 3 个 .py）；用 `inspect_team_archive`（导入方那套校验）验；逐字节比对 zip 和部署文件。
   只想留版本不导出时加 `--no-zip`。标签别重名（脚本不覆盖已有备份）。
7. **提醒用户备份**（具体地说）：备到 `configs/custom_teams/` **外面**（他习惯 `F:\ok-ww-备份-<日期>\`；`team_backup` 已经有一份）。
   换代码的正确姿势：**把文件复制进已有文件夹，别整个文件夹搬**（整个搬过来带过一次坏 ACL，目录谁都读不了，只能 UAC 提权 `takeown`+`icacls` 拿回来；也覆盖丢过一整天的标定）。
8. **更新 memory**：这条轴的 memory 记一行"<日期> 定稿分享 vX"：导出文件名、备份路径、最后几处改动是否实机过、给别人用时要改的开关。MEMORY.md 索引行同步更新。

## 给别人用时的开关

在 team.json 描述和持宏者文件顶部写清楚哪些开关要按自己的配置改（例：`IU_QINGYUN` 只有尤诺带无常凶鹭才开、`JR_CHAIN2_OPENER` 二链才开、心要电磁模态）。
