# 已有的轴：去哪抄

详细历史在 memory 目录的 `ok-ww-*-axis.md`（MEMORY.md 有一行索引）。这里只列"新轴要复用某个角色/某段写法时去哪找"。
状态以 memory 为准，下面是 2026-10-06 的快照。目录名是 `configs/custom_teams/` 下的。
**除了标"skill 自带"的，这些目录只在楽山的 ok-ww 里**；别人用这个 skill 时手里只有自己导入过的队伍（而且导入的 zip 里没有干跑工具），找不到就以 skill 自带的那份为准。

## 引擎从哪抽

| 要什么 | 抄这份 |
|---|---|
| 分段判据型引擎（最新、最全：tap / quick_switch / handoff / switch_retry / fire_r / ensure_r / wait_hud_* / read_con / wait_con_full / press_key_until_cd / HUD 看门狗 / enable+F 监视 / SendInput） | skill 自带 `assets/reference_team/Hsin__Rover__Suisui/Hsin.py`（心雷穗 v1.0.0） |
| 干跑工具模板 | skill 自带 `assets/reference_team/Hsin__Rover__Suisui/dryrun.py.tool`（队伍 zip 里没有它） |
| 宏表回放型（`OPENER_MACRO`/`LOOP_MACRO`、`run_macro`/`play_rows`/`macro_key`/`macro_switch`、SAFETY、MACRO_SPEED、动作词） | `Chisa__Suisui__YangYangSp/YangYangSp.py`（秧千穗 v4.1） |
| 宏 + 手动段混合、宏里不读屏、`E#`/`E+`/`R!` | `Changli__Jinhsi__Verina/Changli.py`（龙凤维 v2.0） |
| 按绝对时刻排程回放宏、SendInput 发键 | `Cartethyia__Chisa__Ciaccona/`（卡夏千，目录现在 ACL 读不了，备份在 `team_backup/2026-09-17_Cartethyia__Chisa__Ciaccona_*`） |
| 跨版本签名适配 `native_call` | `Phoebe__Verina__Zani/Zani.py`（赞菲维 v3.6.9 适配版） |
| 单人刷声骸（不切人、怪死每帧看锁定） | `Chixia__Hiyuki__Youhu/`（绯雪单人 v1.0） |

## 角色判据/段落从哪抄

| 角色（类名） | 队伍目录（持宏者） | 可复用 | memory |
|---|---|---|---|
| 心（Hsin） | `Hsin__Rover__Suisui`（心）、`Douling__Hsin__Suisui`（心）、`Hsin__Jinhsi__ShoreKeeper`（心） | 应世心满 `hsin_h1`、转相=清空+2.06s、`hsin_lib2`、进统御众机 `xn_tongyu`、照世心打空 `XN_READY_GLYPH`、8 颗雕像 `xn_statue_count`、转相补救 `xn_r1_rescue`；电磁 vs 同奏是两条轴；**同奏**下 4A 后先按住、照世心空的那一刻直接出临寰宇（人像来不及显示，雕像计数在同奏录屏上读不准），按住期间人像出来 0.6s 没出手 = 按住被打断要重按（心汐守 `xn_hold_until_gone(watch_ready)`） | xinleisui / xinbusui / xinxishou |
| 穗穗（Suisui） | 同上、`Chisa__Suisui__YangYangSp` | `suisui_e1`（醒春潮）、`suisui_forte3`（芳菲信 600）、大招前补协奏 `su_con_before_r`、濯雨时 15s 墙钟、烟岚=翾舞1 时在场的人 | xinbusui / yangqiansui |
| 雷主·导电（Rover） | `Hsin__Rover__Suisui` | 电涌满=[E] 小框白字、空中=Q 图标变灰、超负荷只短按 | xinleisui |
| 卜灵（Douling） | `Douling__Lucy__Rebecca`（露西 `Lucy.py`）、`Douling__Hsin__Suisui`（心） | **卦象栏 `bl_gua()`**（心卜穗 10-08：角色栏上方 4 格艮/震全读出来，2K~720 验过，~1ms）、按卦象少两个判重击结算 `bl_heavy_gua`、凑一阴一阳的补法规划 `bl_gua_plan`（带协奏账）；旧的：重击外圈黄(少阳)/蓝(少阴)、`bl1_heavies` | lulibu / xinbusui |
| 守岸人（ShoreKeeper） | `Hsin__Jinhsi__ShoreKeeper`（心 `Hsin.py` 的 `sk_*`）、`Lucy__Rebecca__ShoreKeeper`、`Iuno__JingRan__ShoreKeeper`、`Augusta__Iuno__ShoreKeeper` | 自闭启动、回路格数 `sk_forte_segs`、`sk_clear`（不满不重击，不满按重击=化蝶）、`sk_hop_clear`（E≈+2 格，刚清空时按不给）、`sk_dodge_forward`（W+前闪贴怪，打中才回回路） | xinxishou / luolishou / jingyueshou |
| 今汐（Jinhsi） | `Hsin__Jinhsi__ShoreKeeper`（新机制）、`Changli__Jinhsi__Verina`（旧） | E 位图标模板 `jx_e_icon`（5 类）、神霓飞芒 5s 窗口、随时处决 `break_tick`/`jx_do_break`；变奏切进来 E 有 ~1.8s 冷却、冷却数字会让图标认成惊龙破空，先读冷却数字再判图标 | xinxishou / longfeng |
| 景燃 / 尤诺（JingRan / Iuno） | `Iuno__JingRan__ShoreKeeper`（景燃） | 景燃整段按住左键只点 E/闪/F（按住期间发键走不带 activate 的 `key_na`）、形态徽记、尤诺跳=换形态 `iu_jump` | jingyueshou |
| 秧秧玄翎（YangYangSp） / 千咲（Chisa） | `Chisa__Suisui__YangYangSp`（秧秧） | 剑式奇偶、聆风祀声普攻替换、千咲电锯 +0.17s、处决只按 F | yangqiansui |
| 莫宁（Mornye） | `Denia__Mornye__Qingxiao`（达尼娅，`Denia.py` 的 `mor_hold_burst`）、`Cantarella__Mornye__Phrolova`（`Phrolova.py` 的 `mor_hold_heavy`） | `lead` 判据（读屏滞后的标准解法：核心满+按住=必然出手）；用户要求莫宁段直接用现成的，别自己写 | qingxiao / phrolova |
| 清宵（Qingxiao） | `Denia__Mornye__Qingxiao` | 强化重击隐藏 HUD 3s 会骗过 fire_lib | qingxiao |
| 达尼娅 / 爱弥斯 / 琳奈 | `Aemeath__Chisa__Denia`（达尼娅）、`Aemeath__Linnai__Mornye` | 老引擎（`intro_pending` 那份还没加 TTL） | denia / aemeath |
| 绯雪（Hiyuki） | `Chixia__Hiyuki__Youhu`、`Changli__Hiyuki__Jinhsi`、`Hiyuki__Lucilla__Suisui` | 居合链、`hiyuki_right/left` 阈值 0.75、R2 长按不能重发 | hiyuki-solo / longfengxue |
| 洛瑟菈（Lucilla） | `Hiyuki__Lucilla__Suisui`（各自驱动） | 长按 E 是松手判定：录屏量的金色窗口按下后 0.86~1.10s（取 0.95，精确计时；帧表的 30~45F/60F 不准），失败(补光)只给一半印象、E 冷却减 8s → 松手后读冷却 ≥11 才是成功；大招不吃能量、3 张照片(150 印象)解锁、冷却 25s，变奏入场 +100 印象（帧表写 50 不对）；追光的 50 印象 + 20 协奏松手后 ~0.9s 才到账，**0.9s 之前别按 R**（剩照片时会打断追光丢协奏），放出判据 `check_r_fired` = HUD 连续消失 0.5s（2 帧会被特效骗）；大招后进追忆状态，E/R 都放不了，没收掉会带到下一轮（`finish_zhuiyi`：长按攻击等断舍离） | feiluosui |
| 长离（Changli） | `Changli__Jinhsi__Verina`（长离）、`Brant__Changli__Lupa`（长离） | 离火 `is_mouse_forte_full`、焚身以火"按住等条件"（可重按） | longfeng / sanhuo |
| 布兰特 / 露帕 | `Brant__Changli__Lupa` | `press_anchor` 必须用满整格 | sanhuo |
| 赞妮 / 菲比 / 维里奈 | `Phoebe__Verina__Zani`（赞妮） | 宏发大招后补内置大招状态、菲比一圈上场两次、`native_call` | zanfeiwei |
| 西格莉卡 / 仇远 / 嘉贝莉娜 | `Qiuyuan__ShoreKeeper__Xigelika`、`Galbrena__Qiuyuan__ShoreKeeper` | 强化重击黄=可放（`is_mouse_forte_full` 模板，别用颜色）、heavy_loop 一个循环跑到底 | xichoushou / jiachoushou |
| 卡提希娅 / 夏空 / 风主 | `Cartethyia__Ciaccona__Rover`、`Cartethyia__Chisa__Ciaccona` | 夏空回路只能下落后 A 给、芙露德莉斯决意没满不按 R | cartethyia / kaxiaqian |
| 珂莱塔 / 折枝 | `Carlotta__Douling__Zhezhi` | 折枝没有输入缓存（连段按早就丢）、珂莱塔派生下落长度不定 | kezhebu |
| 弗洛洛 / 坎特蕾拉 | `Cantarella__Mornye__Phrolova`、`Cantarella__Douling__Phrolova` | 坎预输入重击压在处决演出上、坎/莫两个奶关 is_healer | phrolova / fukanbu |
| 奥古斯塔 | `Augusta__Iuno__ShoreKeeper`（宏在 Augusta.py，入口守岸人；目录现在 ACL 读不了） | 重击一个输入四种结果，宏只管长按/点按时刻 | augusta |
| 锁暝（Suoming） | `Hsin__ShoreKeeper__Suoming`（宏在 Hsin.py，未实机）、`Sanhua__Suoming__Verina`（宏在 Suoming.py） | 妄执条和心应世心同一行，但出招时被自己的粉色特效污染、不能拿来判；念深解伞形 A4 要 A3 后按住（A2 后按住=旋雷破）；念深里妄执满 E=无舍念、按住刻心念不能切人；R 演完声骸要按到进 CD；**框架 `suoming_forte_e` 只认无舍念、不认锁妄念**（念起妄执满的紫圈旋涡伞面），锁散维用自己的 16x16 字形 `SO_WN_GLYPH`/`so_wangnian_score`；按住普攻挨打硬直后不续连段，读自己血条 `so_hp_fill` 掉了就重按 | xinsuoshou |
| 露西 / 丽贝卡（Lucy / Rebecca） | `Lucy__Rebecca__ShoreKeeper`、`Lucy__Rebecca__Verina`、`Lucy__Mornye__Rebecca`、`Douling__Lucy__Rebecca` | 露西大招面板左键按顺序点选 | luolishou / luliwei / lumoli / lulibu |

**一个角色在两条队里是两份拷贝**，抄之前看两份哪份更新（memory 里有日期）。
同一份引擎的老拷贝里还有已知没修的问题（`intro_pending` 无 TTL：`Qiuyuan__ShoreKeeper__Xigelika` / `Aemeath__Chisa__Denia` / `Hiyuki__Lucilla__Suisui`），别从那几份抄引擎。
