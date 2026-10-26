from src.char.BaseChar import SwitchPriority
from src.char.Suisui import Suisui as NativeSuisui


class Suisui(NativeSuisui):
    """心雷穗(心/雷主/穗穗)里的穗穗。非本队时整套走原版。

    【她不驱动任何一段轴】: 宏体在同目录的 Hsin.py。宏每一圈在她变奏入场、HUD 在场时返回,
    下一次框架调的就是她, 这里直接转给心的 drive(), 循环轴从她的 E 接上。
    """

    @property
    def is_healer(self):
        """【本队里不把穗穗算作奶妈】: 框架开战前的 switch_healer() 会先切给奶妈, 白切一次人。"""
        try:
            if self.is_in_xls:
                return False
        except Exception:
            pass  # __init__ 里会先读一次, 那时队伍还没加载
        return super().is_healer

    @property
    def is_in_xls(self) -> bool:
        members = 0
        for char in self.task.chars:
            if char and char.name in {'Hsin', 'Rover'}:
                members += 1
        return members == 2

    def macro(self):
        """持宏的心。心那份自定义没启用时返回 None, 走原版。"""
        for char in self.task.chars:
            if char is None or char is self:
                continue
            if hasattr(char, 'drive') and hasattr(char, 'quick_switch'):
                return char
        return None

    def reset_state(self):
        super().reset_state()
        self.check_f_on_switch = False

    def do_perform(self):
        if not self.is_in_xls:
            return super().do_perform()
        macro = self.macro()
        if macro is None:
            self.logger.warning('xls: Hsin custom code is off, falling back to the native rotation')
            return super().do_perform()
        macro.drive(self)

    def get_switch_priority(self, current_char=None, has_intro=False, target_low_con=False):
        """启动轴待跑时返回 MUST: 启动轴第一格就是她的 3A。【要写在 super() 之前】: 原版有自己的切人锁。"""
        if self.is_in_xls:
            macro = self.macro()
            if macro is not None and macro.opener_pending():
                return SwitchPriority.MUST
        return super().get_switch_priority(current_char, has_intro, target_low_con)
