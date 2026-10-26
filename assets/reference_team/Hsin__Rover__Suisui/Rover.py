from src.char.BaseChar import SwitchPriority
from src.char.Rover import Rover as NativeRover


class Rover(NativeRover):
    """心雷穗(心/雷主/穗穗)里的雷主(漂泊者·导电)。非本队时整套走原版。

    【他不驱动任何一段轴】: 宏体在同目录的 Hsin.py, 他全程由宏按数字键切进切出(一圈上场两次)。
    走到 do_perform 说明宏散了(切人失败/脱战重进), 转给心的 drive() —— 它会先把场子交给穗穗再接循环轴。
    自定义角色文件互相 import 不到, 用 task.chars 里的实例按能力找。
    """

    @property
    def is_in_xls(self) -> bool:
        members = 0
        for char in self.task.chars:
            if char and char.name in {'Hsin', 'Suisui'}:
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
        # 【必须写在 reset_state 里】: 换类时内置实例的字段会整体拷过来, 改过的值被打回内置值
        self.check_f_on_switch = False

    def do_perform(self):
        if not self.is_in_xls:
            return super().do_perform()
        self.check_f_on_switch = False
        macro = self.macro()
        if macro is None:
            self.logger.warning('xls: Hsin custom code is off, falling back to the native rotation')
            return super().do_perform()
        macro.drive(self)

    def get_switch_priority(self, current_char=None, has_intro=False, target_low_con=False):
        """启动轴待跑时返回 NO(宏自己切人)。"""
        if self.is_in_xls:
            macro = self.macro()
            if macro is not None and macro.opener_pending():
                return SwitchPriority.NO
        return super().get_switch_priority(current_char, has_intro, target_low_con)
