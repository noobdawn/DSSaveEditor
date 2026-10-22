# -*- coding: utf-8 -*-
"""游戏数据对照校验器。

用途: 游戏更新后重新导出 GameData 表, 运行本脚本对比 data/*.json,
     发现 新增/删除/名称变化/字段变化, 必要时用 --write 重新生成。

用法:
    python tools/check_game_data.py                     # 只对比, 有差异返回码 1
    python tools/check_game_data.py --write             # 对比并重新生成有差异的文件
    python tools/check_game_data.py --gamedata "D:\\path\\GameData"

依赖:
    FModel 导出的 *.table (JSON)。默认路径可用环境变量 DSSAVE_GAMEDATA 覆盖。
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

LANGS = [("ko_KR", "SourceString"), ("en", "En"), ("ja", "Ja"), ("zh_CN", "Zh_CN"),
         ("zh_TW", "Zh_TW"), ("de", "De"), ("fr", "Fr"), ("es_ES", "Es_ES"),
         ("pt_BR", "Pt_BR"), ("ru", "Ru"), ("th", "Th")]
DB_CATEGORY = {"MAIN": 1, "EPIC": 3, "CHARACTER": 14, "ADVENT_GRADE": 7, "TUTORIAL": 12, "SUB": 0}
STACK_TYPES = {"COMMON", "ACHIEVEMENT_POINT", "CHARACTER_EXP", "KARMA_EXP", "EQUIPMENT_EXP",
               "COOKING_INGREDIENT", "QUEST", "GEM_SOCKET_MATERIAL", "CHANGE_EQUIPMENT_SUB_STAT",
               "CHARACTER_MASTER_SOUL", "MAP"}
SKILL_MAX_LEVEL = {1: 10, 2: 10, 3: 10, 4: 10, 5: 7, 6: 7, 7: 7, 8: 1, 801: 1}
DEFAULT_GAMEDATA = r"D:\UE_Extracted\FModel\Output\Exports\DS\Content\Design\GameData"


# ---------------------------------------------------------------- 基础
class Tables:
    def __init__(self, path):
        self.path = path
        self.cache = {}
        self.missing = []

    def get(self, name):
        if name in self.cache:
            return self.cache[name]
        p = os.path.join(self.path, name + ".table")
        if not os.path.exists(p):
            self.missing.append(name)
            self.cache[name] = {}
            return {}
        with open(p, "r", encoding="utf-8-sig") as f:
            data = json.load(f).get("Data", {})
        self.cache[name] = data
        return data


def loc(entry):
    """StringData/StringQuestData 条目 -> {语言: 文本} (只保留非空)。"""
    if not entry:
        return None
    out = {}
    for key, field in LANGS:
        v = entry.get(field)
        if isinstance(v, str) and v.strip():
            out[key] = v
    return out or None


def loc_id(sd, nid):
    return loc(sd.get(str(nid))) if nid else None


def fallback_name(sd, cid, entry):
    n = loc_id(sd, entry.get("Name"))
    if n:
        return n
    memo = entry.get("Memo")
    if isinstance(memo, str) and memo.strip():
        return {"ko_KR": memo}
    return {"zh_CN": str(cid), "en": str(cid)}


# ---------------------------------------------------------------- 各文件生成规则
def build_id_names(t):
    gd = t.get("GameItemData")
    pc = t.get("PCCharacterData")
    ms = t.get("MonsterCharacterData")
    npc = t.get("NPCCharacterData")
    veh = t.get("VehicleCharacterData")
    sd = t.get("StringData")
    out = {"item": {}, "character": {}, "monster": {}, "npc": {}, "vehicle": {}, "desc": {}}
    for cid, v in gd.items():
        out["item"][cid] = loc_id(sd, v.get("Name")) or {"zh_CN": cid, "en": cid}
        if v.get("Desc"):
            d = loc_id(sd, v.get("Desc"))
            if d:
                out["desc"][cid] = d
    for cid, v in pc.items():
        out["character"][cid] = loc_id(sd, v.get("Name")) or {"zh_CN": cid, "en": cid}
    for cid, v in ms.items():
        out["monster"][cid] = fallback_name(sd, cid, v)
    for cid, v in npc.items():
        out["npc"][cid] = fallback_name(sd, cid, v)
    for cid in veh:
        g = gd.get(cid, {})
        out["vehicle"][cid] = loc_id(sd, g.get("Name")) or {"zh_CN": cid, "en": cid}
    return out


def build_stat_names(t):
    sl = t.get("StatListData")
    ems = t.get("EquipmentMainStatData")
    ess = t.get("EquipmentSubStatData")
    sd = t.get("StringData")
    sl_upper = {k.upper(): v for k, v in sl.items()}
    out = {"stat_key": {}, "main_stat": {}, "sub_stat": {}}
    for k, v in sl.items():
        name = loc_id(sd, v.get("Name"))
        if not name:
            continue
        out["stat_key"][k] = {"name": name, "stat_value": v.get("StatValue"),
                              "is_percentage": bool(v.get("IsPercentage"))}
    for k, v in ems.items():
        st = v.get("StatList")
        src = sl.get(st) or sl_upper.get(str(st).upper()) or {}
        out["main_stat"][k] = {"stat": st, "name": loc_id(sd, src.get("Name")),
                               "ratio": v.get("StatRatio"), "weight": v.get("Weight")}
    for k, v in ess.items():
        st = v.get("StatList")
        src = sl.get(st) or sl_upper.get(str(st).upper()) or {}
        out["sub_stat"][k] = {"stat": st, "name": loc_id(sd, src.get("Name")),
                              "ratio": v.get("StatRatio"), "weight": v.get("Weight"),
                              "memo": v.get("Memo")}
    return out


def build_skill_names(t):
    sg = t.get("PCSkillGrowthData")
    sd = t.get("StringData")
    out = {}
    for ch, v in sg.items():
        d = {}
        for e in v.get("Data", []):
            tv = e.get("TypeValue")
            key = str(tv)
            if key in d or e.get("SlotLevel") not in (None, 1):
                continue
            d[key] = {"name": loc_id(sd, e.get("Name")),
                      "slot_order": e.get("SlotOrder"), "slot_type": e.get("SlotType"),
                      "skill_type": e.get("SkillType"),
                      "max_level": SKILL_MAX_LEVEL.get(tv, 10)}
        out[ch] = d
    return out


def build_character_data(t, hidden=None):
    pc = t.get("PCCharacterData")
    cc = t.get("CharCollectionData")
    sd = t.get("StringData")
    hidden = hidden or set()
    out = {}
    for cid, v in pc.items():
        if not v.get("IsUserCharacter"):
            continue
        if "팀대체" in (v.get("Memo") or ""):
            continue
        out[cid] = {"name": loc_id(sd, v.get("Name")) or {"zh_CN": cid, "en": cid},
                    "hidden": cid in hidden,
                    "default_hp": int(round((v.get("Default_Value") or 0) * (v.get("HP_Value_Ratio") or 0))),
                    "in_collection": cid in cc}
    return out


def build_vehicle_data(t):
    veh = t.get("VehicleCharacterData")
    gd = t.get("GameItemData")
    sd = t.get("StringData")
    out = {}
    for cid, v in veh.items():
        g = gd.get(cid, {})
        cat = g.get("Category") or 0
        out[cid] = {"id": int(cid), "name": loc_id(sd, g.get("Name")),
                    "type": loc_id(sd, 11103 + (cat - 1102)) if cat else None,
                    "desc": loc_id(sd, g.get("Desc")),
                    "dlc": v.get("DLCAppID") or 0, "category": cat}
    return out


def build_gem_stat(t):
    return {k: {"stat": v["StatList"], "ratio": v["StatRatio"]}
            for k, v in t.get("GemNewStatData").items()}


def build_item_types(t):
    gd = t.get("GameItemData")
    out = {"stackable": [], "cook": [], "gem": [], "karma": []}
    for cid, v in gd.items():
        ty = v.get("ItemType")
        if ty in STACK_TYPES:
            out["stackable"].append(int(cid))
        elif ty == "COOKING":
            out["cook"].append(int(cid))
        elif ty == "GEM":
            out["gem"].append(int(cid))
        elif ty == "KARMA":
            out["karma"].append(int(cid))
    for k in out:
        out[k] = [str(x) for x in sorted(out[k])]
    return out


def build_equip_items(t):
    gd = t.get("GameItemData")
    out = {}
    for cid, v in gd.items():
        if v.get("ItemType") != "EQUIPMENT":
            continue
        out[cid] = {"series": str(int(str(cid)[:3]) - 134),
                    "grade": v.get("Grade"), "category": v.get("Category")}
    return {"item": out}


def build_equipment_exp(t):
    out = {}
    for grade, g in t.get("EquipmentLevelData").items():
        out[grade] = {str(k): int(v["LevelMaxExp"])
                      for k, v in (g.get("EquipmentLevelDataMap") or {}).items()}
    return out


def build_level_exp(t):
    src = t.get("PCCharacterLevelData")
    out = {}
    for lv in range(1, 101):
        out[str(lv)] = 0 if lv == 1 else int(src.get(str(lv - 1), {}).get("CharacterExp_EPIC") or 0)
    return out


def build_dungeon_groups(t):
    gdg = t.get("MapDungeonGroupData")
    sd = t.get("StringData")
    out = {}
    for k, v in gdg.items():
        name = (loc_id(sd, v.get("Name")) or {}).get("zh_CN") or v.get("Memo", "")
        out[k] = {"id": int(k), "memo": v.get("Memo", ""), "name": name,
                  "open_type": v.get("OpenType", "TYPE_NONE"),
                  "open_value": v.get("OpenValue01", 0) or 0}
    return out


def build_quest_dungeon_map(t):
    steps = t.get("QuestStepData")
    gdg = t.get("MapDungeonGroupData")
    out = {}
    for qid, v in steps.items():
        for st in v.get("QuestStepDataArray", []):
            if st.get("StepType") == "ENTER_DUNGEON":
                out.setdefault(qid, []).append(int(st["StepValue1"]))
    for k, v in gdg.items():
        if v.get("OpenType") == "QUEST_CLEAR" and v.get("OpenValue01"):
            out.setdefault(str(v["OpenValue01"]), []).append(int(k))
    for q in out:
        out[q] = sorted(set(out[q]))
    return out


def build_quest_data(t):
    qm = t.get("QuestMainData")
    qstep = t.get("QuestStepData")
    qstep_x = t.get("QuestStepData_Export")
    sq = t.get("StringQuestData")
    sd = t.get("StringData")
    qr = t.get("QuestRecordData")
    qep = t.get("QuestEpisodeData")
    dqm = t.get("DynamicQuestMainData")
    dqg = t.get("DynamicQuestGroupData")
    dqs = t.get("DynamicQuestStepData")

    def steps_meta(qid):
        src = qstep.get(qid) or qstep_x.get(qid)
        if not src:
            return None
        arr = src.get("QuestStepDataArray") or []
        if not arr:
            return None
        ids = [int(x["StepID"]) for x in arr]
        cnts = [int(x.get("StepCnt") or 1) for x in arr]
        return {"min": min(ids), "max": max(ids), "count": len(ids), "max_cnt": max(cnts)}

    quests = {}
    for qid, v in qm.items():
        name = loc(sq.get(str(v.get("QuestName"))))
        if name is None and v.get("Memo"):
            name = {"ko_KR": v["Memo"]}
        quests[str(qid)] = {
            "id": int(qid), "category": v.get("Category"),
            "db_category": DB_CATEGORY.get(v.get("Category"), 0),
            "name": name, "group": v.get("QuestGroup"),
            "accept_type": v.get("AcceptType"),
            "pre": [int(x) for x in (v.get("PreQuestID") or [])],
            "next": int(v.get("NextQuestID") or 0),
            "hide": v.get("HideQuest") or 0,
            "giveup": bool(v.get("GiveUpQuest")),
            "adv_level": v.get("AdvLevel") or 0,
            "steps": steps_meta(str(qid)),
        }

    def build_cards(group_key):
        g = qr.get(str(group_key))
        if not g:
            return []
        cards = []
        for k, card in g.get("RecordCardDataMap", {}).items():
            entries = card.get("RecordDataArray") or []
            if not entries:
                continue
            first = entries[0]
            cards.append({
                "card_id": int(k) * 1000 + int(g.get("CardGroupID") or group_key),
                "title": loc(sd.get(str(first.get("TitleName")))),
                "subtitle": loc(sd.get(str(first.get("SubTitleStirng")))),
                "group_name": loc(sd.get(str(first.get("CardGroupName")))),
                "quests": [int(e["QuestID"]) for e in entries],
                "max_order": max(int(e.get("CardOrder") or 0) for e in entries),
                "reward_item": first.get("RewardItemID"),
                "reward_cnt": first.get("RewardItemCnt"),
            })
        cards.sort(key=lambda c: c["card_id"])
        return cards

    record_groups = {"1": build_cards(1), "101": build_cards(101)}
    epic_lines = {str(c["card_id"]): {"title": c.get("title"), "subtitle": c.get("subtitle"),
                                     "quests": c["quests"], "max_order": c["max_order"]}
                  for c in record_groups["101"]}
    episodes = {}
    for _ch, v in qep.items():
        for e in v.get("QuestEpisodeDataArray") or []:
            episodes[str(e["ID"])] = {"char_id": e.get("CharacterID"), "episode_id": int(e["ID"]),
                                      "order": e.get("Order"), "group_id": e.get("GroupID"),
                                      "char_name": None}
    dynamic = {}
    for gid, g in dqm.items():
        gmeta = dqg.get(str(gid)) or {}
        for qid, q in (g.get("DynamicQuestMainDataMap") or {}).items():
            sdata = dqs.get(str(qid)) or {}
            arr = sdata.get("DynamicQuestStepDataArray") or []
            ids = [int(x["StepID"]) for x in arr]
            button = next((x.get("ButtonName") for x in arr if x.get("ButtonName")), 0)
            entry = sq.get(str(button)) if button else None
            dynamic[str(qid)] = {
                "id": int(qid), "group": q.get("GroupID"), "name": loc(entry),
                "memo_ko": (entry or {}).get("SourceString") or q.get("Memo"),
                "trigger": gmeta.get("ActiveTimingType"),
                "reward_id": q.get("ClearRewardID"),
                "steps": {"min": min(ids), "max": max(ids), "count": len(ids)} if ids else None,
            }
    return {"quests": quests, "record_groups": record_groups,
            "episodes": episodes, "dynamic": dynamic, "epic_lines": epic_lines}


# ---------------------------------------------------------------- diff / 写盘
def diff_dict(old, new, show=5):
    add = sorted(set(new) - set(old))
    rem = sorted(set(old) - set(new))
    chg = [k for k in set(old) & set(new) if old[k] != new[k]]
    return {"add": add, "rem": rem, "chg": chg}


def report(name, old, new):
    if old == new:
        print("[OK]   %s" % name)
        return False
    print("[DIFF] %s" % name)
    if isinstance(old, dict) and isinstance(new, dict):
        d = diff_dict(old, new)
        print("       新增 %d, 删除 %d, 变化 %d" % (len(d["add"]), len(d["rem"]), len(d["chg"])))
        if d["add"]:
            print("       新增样例:", [str(x) for x in d["add"][:6]])
        if d["rem"]:
            print("       删除样例:", [str(x) for x in d["rem"][:6]])
        for k in d["chg"][:3]:
            o, n = old[k], new[k]
            if isinstance(o, dict) and isinstance(n, dict):
                fields = {kk: (o.get(kk), n.get(kk)) for kk in set(o) | set(n)
                          if o.get(kk) != n.get(kk)}
                print("       变化 %s: %s" % (k, str(fields)[:200]))
            else:
                print("       变化 %s: %r -> %r" % (k, o, n))
    elif isinstance(old, list) and isinstance(new, list):
        so, sn = set(map(str, old)), set(map(str, new))
        print("       新增 %d, 删除 %d" % (len(sn - so), len(so - sn)))
    return True


def write_json(name, obj, indent=None):
    p = os.path.join(DATA, name)
    if indent is None:
        text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(obj, ensure_ascii=False, indent=indent)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description="对比/重建 data/*.json 与 FModel 导出表")
    ap.add_argument("--gamedata", default=os.environ.get("DSSAVE_GAMEDATA", DEFAULT_GAMEDATA))
    ap.add_argument("--write", action="store_true", help="重新生成有差异的数据文件")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.gamedata):
        print("GameData 目录不存在: %s" % args.gamedata)
        return 2

    t = Tables(args.gamedata)
    builders = [
        ("id_names.json", lambda: build_id_names(t), None),
        ("stat_names.json", lambda: build_stat_names(t), None),
        ("skill_names.json", lambda: build_skill_names(t), None),
        ("character_data.json", lambda: build_character_data(t, _hidden_set()), None),
        ("vehicle_data.json", lambda: build_vehicle_data(t), None),
        ("gem_stat.json", lambda: build_gem_stat(t), 2),
        ("item_types.json", lambda: build_item_types(t), 1),
        ("equip_items.json", lambda: build_equip_items(t), 1),
        ("equipment_exp.json", lambda: build_equipment_exp(t), 1),
        ("level_exp.json", lambda: build_level_exp(t), 1),
        ("dungeon_groups.json", lambda: build_dungeon_groups(t), 1),
        ("quest_dungeon_map.json", lambda: build_quest_dungeon_map(t), 1),
        ("quest_data.json", lambda: build_quest_data(t), 1),
    ]

    dirty = False
    for name, builder, indent in builders:
        try:
            new = builder()
        except Exception as e:
            print("[ERR]  %s 生成失败: %s" % (name, e))
            dirty = True
            continue
        if not new:
            print("[SKIP] %s (缺少源表或为空)" % name)
            continue
        old = _load_data(name)
        changed = report(name, old, new)
        dirty = dirty or changed
        if changed and args.write:
            write_json(name, new, indent)
            print("       已写入 %s" % name)

    if t.missing:
        print()
        print("缺少的源表 (%d): %s" % (len(set(t.missing)), sorted(set(t.missing))[:12]))
    print()
    print("结果:", "存在差异" if dirty else "与游戏数据一致")
    return 1 if dirty else 0


def _load_data(name):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _hidden_set():
    """保留现有 character_data.json 中人工维护的 hidden 列表。"""
    cur = _load_data("character_data.json")
    return {k for k, v in cur.items() if isinstance(v, dict) and v.get("hidden")}


if __name__ == "__main__":
    sys.exit(main())
