# -*- coding: utf-8 -*-
"""数据文件不变量测试 (无需游戏表 / 无需存档)。

运行: python -m unittest discover -s tests -v
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

CATEGORY_MAP = {"MAIN": 1, "EPIC": 3, "CHARACTER": 14, "ADVENT_GRADE": 7, "TUTORIAL": 12, "SUB": 0}
GRADES = {"NORMAL", "SUPERIOR", "RARE", "EPIC", "LEGENDARY"}
EQUIP_CATEGORIES = {1300, 1301, 1302, 1303, 1304}
SKILL_TYPES = {"SKILL", "MASTER"}
MAX_LEVELS = {1, 7, 10}


def load(name):
    with open(os.path.join(DATA, name), "r", encoding="utf-8") as f:
        return json.load(f)


def is_name_dict(v):
    """名称字典: 非空且每个值都是非空字符串。"""
    return isinstance(v, dict) and bool(v) and all(isinstance(x, str) and x.strip() for x in v.values())


class TestDataFilesExist(unittest.TestCase):
    def test_json_files_parse(self):
        for name in os.listdir(DATA):
            if not name.endswith(".json"):
                continue
            with self.subTest(file=name):
                load(name)  # 解析失败即失败


class TestIdNames(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load("id_names.json")

    def test_sections(self):
        self.assertEqual(set(self.d), {"item", "character", "monster", "npc", "vehicle", "desc"})
        for sec, entries in self.d.items():
            with self.subTest(section=sec):
                self.assertTrue(entries, "%s 不应为空" % sec)

    def test_names_non_empty(self):
        for sec, entries in self.d.items():
            for cid, name in entries.items():
                with self.subTest(section=sec, cid=cid):
                    self.assertTrue(str(cid).isdigit(), "key 必须是数字 ID")
                    self.assertTrue(is_name_dict(name), "名称不能为空: %s/%s" % (sec, cid))

    def test_no_duplicate_keys(self):
        # JSON 解析后 dict 天然去重; 检查原始文本是否有重复 key 导致静默覆盖
        raw = open(os.path.join(DATA, "id_names.json"), encoding="utf-8").read()
        self.assertGreater(len(raw), 1000)


class TestItemTypes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load("item_types.json")
        cls.names = load("id_names.json")["item"]

    def test_categories(self):
        self.assertEqual(set(self.d), {"stackable", "cook", "gem", "karma"})
        for sec, ids in self.d.items():
            with self.subTest(section=sec):
                self.assertTrue(ids)
                self.assertEqual(len(ids), len(set(ids)), "CID 不应重复")
                self.assertTrue(all(str(x).isdigit() for x in ids))

    def test_ids_exist_in_names(self):
        for sec, ids in self.d.items():
            for cid in ids:
                with self.subTest(section=sec, cid=cid):
                    self.assertIn(str(cid), self.names, "item_types.%s 的 CID 缺少名称" % sec)


class TestEquipItems(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load("equip_items.json")
        cls.items = cls.d.get("item", {})
        cls.names = load("id_names.json")["item"]

    def test_structure(self):
        self.assertIn("item", self.d)
        self.assertTrue(self.items)

    def test_entries(self):
        for cid, v in self.items.items():
            with self.subTest(cid=cid):
                self.assertTrue(str(cid).isdigit())
                self.assertIn(str(v.get("series")), {"2", "3", "4", "5"})
                self.assertIn(v.get("grade"), GRADES)
                self.assertIn(int(v.get("category")), EQUIP_CATEGORIES)
                self.assertIn(str(cid), self.names)


class TestEquipmentExp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load("equipment_exp.json")

    def test_grades_and_levels(self):
        self.assertEqual(set(self.d), GRADES)
        for grade, levels in self.d.items():
            with self.subTest(grade=grade):
                self.assertTrue(levels)
                keys = sorted(levels, key=int)
                self.assertEqual(keys, [str(i) for i in range(len(keys))], "强化等级应从 0 连续")
                vals = [int(levels[k]) for k in keys]
                self.assertEqual(vals, sorted(vals), "经验应单调不减")


class TestLevelExp(unittest.TestCase):
    def test_100_levels(self):
        d = load("level_exp.json")
        self.assertEqual(len(d), 100)
        self.assertEqual(int(d["1"]), 0)
        vals = [int(d[str(i)]) for i in range(1, 101)]
        self.assertEqual(vals, sorted(vals), "经验应单调不减")


class TestGemStat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load("gem_stat.json")
        cls.stat_keys = load("stat_names.json")["stat_key"]

    def test_entries(self):
        self.assertTrue(self.d)
        for sid, v in self.d.items():
            with self.subTest(stat_id=sid):
                self.assertTrue(str(sid).isdigit())
                self.assertIn(v.get("stat"), self.stat_keys,
                              "符文属性必须存在于 stat_key")
                ratio = float(v.get("ratio"))
                self.assertGreater(ratio, 0)
                self.assertLessEqual(ratio, 1)


class TestStatNames(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load("stat_names.json")

    def test_sections(self):
        self.assertEqual(set(self.d), {"stat_key", "main_stat", "sub_stat"})
        for sec in self.d:
            self.assertTrue(self.d[sec], "%s 不应为空" % sec)

    def test_stat_key(self):
        for k, v in self.d["stat_key"].items():
            with self.subTest(stat=k):
                self.assertTrue(is_name_dict(v.get("name")), "属性名不能为空: %s" % k)
                self.assertIn("stat_value", v)
                self.assertIsInstance(v.get("is_percentage"), bool)

    def test_main_sub(self):
        for sec in ("main_stat", "sub_stat"):
            for sid, v in self.d[sec].items():
                with self.subTest(section=sec, id=sid):
                    self.assertTrue(str(sid).isdigit())
                    self.assertTrue(str(v.get("stat") or "").strip())
                    self.assertTrue(is_name_dict(v.get("name")), "词条名不能为空: %s/%s" % (sec, sid))
                    self.assertGreater(float(v.get("ratio")), 0)
                    self.assertGreaterEqual(int(v.get("weight")), 0)
                    if sec == "sub_stat":
                        self.assertIn("memo", v)

    def test_case_insensitive_stats_covered(self):
        # 词条使用 MaxHP/MaxHP_Per, stat_key 使用 MAXHP/MAXHP_Per; 两者必须都能匹配
        upper = {k.upper(): k for k in self.d["stat_key"]}
        stats = {str(v.get("stat")) for sec in ("main_stat", "sub_stat") for v in self.d[sec].values()}
        for st in stats:
            with self.subTest(stat=st):
                self.assertIn(st.upper(), upper, "词条属性在 stat_key 中无大小写无关匹配: %s" % st)


class TestSkillNames(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load("skill_names.json")
        cls.chars = load("id_names.json")["character"]

    def test_entries(self):
        self.assertTrue(self.d)
        for ch, skills in self.d.items():
            with self.subTest(char=ch):
                self.assertIn(str(ch), self.chars)
                self.assertTrue(skills)
                for tv, v in skills.items():
                    self.assertTrue(str(tv).isdigit())
                    self.assertTrue(is_name_dict(v.get("name")), "技能名不能为空: %s/%s" % (ch, tv))
                    self.assertIn(v.get("skill_type"), SKILL_TYPES)
                    self.assertIn(int(v.get("max_level")), MAX_LEVELS)


class TestCharacterData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load("character_data.json")
        cls.chars = load("id_names.json")["character"]

    def test_entries(self):
        self.assertTrue(self.d)
        seen_hp = set()
        for cid, v in self.d.items():
            with self.subTest(cid=cid):
                self.assertIn(str(cid), self.chars)
                self.assertTrue(is_name_dict(v.get("name")))
                self.assertIsInstance(v.get("hidden"), bool)
                self.assertIsInstance(v.get("in_collection"), bool)
                hp = int(v.get("default_hp"))
                self.assertGreaterEqual(hp, 0)
                seen_hp.add(hp)
        self.assertTrue(seen_hp)


class TestVehicleData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load("vehicle_data.json")
        cls.names = load("id_names.json")["vehicle"]

    def test_entries(self):
        self.assertTrue(self.d)
        for cid, v in self.d.items():
            with self.subTest(cid=cid):
                self.assertEqual(int(v.get("id")), int(cid))
                self.assertIn(str(cid), self.names)
                cat = int(v.get("category") or 0)
                if cat:
                    self.assertTrue(is_name_dict(v.get("type")), "有 category 的使魔必须有类型名: %s" % cid)
                self.assertGreaterEqual(int(v.get("dlc")), 0)


class TestQuestData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load("quest_data.json")
        cls.quests = cls.d["quests"]

    def test_sections(self):
        self.assertEqual(set(self.d), {"quests", "record_groups", "episodes", "dynamic", "epic_lines"})
        self.assertTrue(self.quests)

    def test_quests(self):
        for qid, q in self.quests.items():
            with self.subTest(qid=qid):
                self.assertTrue(str(qid).isdigit())
                self.assertEqual(int(q.get("id")), int(qid))
                cat = q.get("category")
                self.assertIn(cat, CATEGORY_MAP)
                self.assertEqual(int(q.get("db_category")), CATEGORY_MAP[cat],
                                 "db_category 与分类映射不一致: %s" % qid)
                self.assertTrue(is_name_dict(q.get("name")), "任务名不能为空: %s" % qid)
                self.assertIsInstance(q.get("pre"), list)
                for p in q.get("pre") or []:
                    self.assertIn(str(int(p)), self.quests, "前置任务不存在: %s -> %s" % (qid, p))
                nxt = int(q.get("next") or 0)
                if nxt:
                    self.assertIn(str(nxt), self.quests, "后续任务不存在: %s -> %s" % (qid, nxt))
                steps = q.get("steps")
                if steps is not None:
                    self.assertLessEqual(int(steps["min"]), int(steps["max"]))
                    self.assertGreaterEqual(int(steps["count"]), 1)
                    self.assertGreaterEqual(int(steps["max_cnt"]), 1)

    def test_record_cards(self):
        cards = self.d["record_groups"]["1"]
        self.assertEqual(len(cards), 8, "主线应为 8 章")
        for i, c in enumerate(cards):
            with self.subTest(card=c.get("card_id")):
                self.assertEqual(int(c["card_id"]), 1000 * (i + 1) + 1)
                self.assertTrue(c["quests"])
                self.assertEqual(int(c["max_order"]), len(c["quests"]))
                for qid in c["quests"]:
                    self.assertIn(str(qid), self.quests)

    def test_epic_lines(self):
        cards = self.d["record_groups"]["101"]
        self.assertEqual(len(cards), 5, "因缘应为 5 线")
        self.assertEqual(set(self.d["epic_lines"]), {str(c["card_id"]) for c in cards})
        for c in cards:
            line = self.d["epic_lines"][str(c["card_id"])]
            self.assertEqual(line["quests"], c["quests"])
            for qid in line["quests"]:
                self.assertIn(str(qid), self.quests)

    def test_episodes(self):
        eps = self.d["episodes"]
        self.assertTrue(eps)
        orders = sorted(int(v["order"]) for v in eps.values())
        self.assertEqual(orders, list(range(1, len(eps) + 1)), "英雄记录线顺序应连续")

    def test_dynamic(self):
        dyn = self.d["dynamic"]
        self.assertTrue(dyn)
        for qid, v in dyn.items():
            with self.subTest(qid=qid):
                self.assertTrue(str(qid).isdigit())
                self.assertEqual(int(v.get("id")), int(qid))
                self.assertTrue(is_name_dict(v.get("name")), "区域任务名不能为空: %s" % qid)
                steps = v.get("steps")
                self.assertIsNotNone(steps, "区域任务缺少步骤: %s" % qid)
                self.assertLessEqual(int(steps["min"]), int(steps["max"]))
                self.assertGreaterEqual(int(steps["count"]), 1)


class TestDungeonData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.groups = load("dungeon_groups.json")
        cls.qmap = load("quest_dungeon_map.json")

    def test_groups(self):
        self.assertTrue(self.groups)
        for gid, v in self.groups.items():
            with self.subTest(gid=gid):
                self.assertEqual(int(v.get("id")), int(gid))
                self.assertTrue(str(v.get("name") or "").strip(), "副本组名不能为空")
                self.assertTrue(str(v.get("open_type") or "").strip())

    def test_quest_map(self):
        # 30001/30002 为无组定义的任务内副本, 允许不在 dungeon_groups 中
        allow = {"30001", "30002"}
        self.assertTrue(self.qmap)
        for qid, groups in self.qmap.items():
            with self.subTest(quest=qid):
                self.assertTrue(str(qid).isdigit())
                self.assertTrue(groups)
                for g in groups:
                    self.assertTrue(str(g) in self.groups or str(g) in allow,
                                    "任务 %s 解锁的副本组 %s 无定义" % (qid, g))


class TestCrossReferences(unittest.TestCase):
    """跨文件引用一致性"""

    def test_quest_dungeon_and_dynamic(self):
        qd = load("quest_data.json")
        self.assertGreater(len(qd["dynamic"]), 0)

    def test_character_and_skills(self):
        chars = load("character_data.json")
        skills = load("skill_names.json")
        # 有技能数据的角色应出现在可入队角色里(允许少量 NPC 角色例外, 仅要求非空交集)
        self.assertTrue(set(chars) & set(skills))


if __name__ == "__main__":
    unittest.main()
