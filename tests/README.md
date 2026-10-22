# 测试与数据校验

本目录为项目测试（标准库 `unittest`，无需额外依赖）。

## 运行

```bash
# 项目根目录
python -m unittest discover -s tests -v
```

当前覆盖 **50 项**：

| 文件 | 内容 |
|---|---|
| `test_data_integrity.py` | `data/*.json` 不变量：结构/空名/必填字段/公式一致性/跨文件引用（任务链、记录卡、因缘、英雄线、区域任务、词条 StatList、item_types CID、副本组等） |
| `test_logic.py` | 纯逻辑：i18n 英文回退与占位符、NameResolver、符文 `STAT_INFO_CID` 公式（含 25 个符文全量校验）、QuestManager 页面分组（8 章/5 因缘/6 英雄线/308xx 归位/90063/90064/30811 删除）、任务完成与进行中写库（CATEGORY/STEP） |
| `test_ui_smoke.py` | 合成最小 SQLite（**不含任何玩家存档**）实例化全部 16 个页面并 reload；异常修复三 tab 扫描；任务步骤修复越界检测；新增装备/道具对话框数据量；符文/使魔条目数 |

## 数据校验工具（游戏更新后使用）

```bash
# 对比 data/*.json 与 FModel 导出表（默认路径可用环境变量覆盖）
python tools/check_game_data.py
python tools/check_game_data.py --gamedata "D:\path\to\GameData"
python tools/check_game_data.py --write      # 有差异时自动重新生成
```

- 覆盖 13 个数据文件（id_names / stat_names / skill_names / character_data / vehicle_data /
  gem_stat / item_types / equip_items / equipment_exp / level_exp / dungeon_groups /
  quest_dungeon_map / quest_data）
- 输出新增/删除/字段变化样例；**有差异返回码 1**，一致返回 0
- `--write` 会按固定规则重新生成有差异的文件；`character_data.hidden` 为人工维护列表，生成时自动保留

## 约定

1. 测试**绝不读取/写入玩家存档**；UI 冒烟使用合成库
2. 游戏更新后的标准流程：
   1. FModel 重新导出表
   2. `python tools/check_game_data.py` 查看差异
   3. 确认差异合理后 `--write`（或手工调整）
   4. `python -m unittest discover -s tests -v` 确认全绿
   5. 启动源码/打包 exe 做一次人工冒烟
3. 新增数据依赖功能时，应同时补充对应的数据不变量与逻辑测试
