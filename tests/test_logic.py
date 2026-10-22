# -*- coding: utf-8 -*-
"""纯逻辑单元测试 (不需要存档 / 游戏表)。

运行: python -m unittest discover -s tests -v
"""
import json
import os
import sqlite3
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import i18n                      # noqa: E402
from app.datasource import NameResolver, QuestManager   # noqa: E402
from app.ui_rune import gem_stat_cid      # noqa: E402

DATA = os.path.join(ROOT, "data")


def load(name):
    with open(os.path.join(DATA, name), "r", encoding="utf-8") as f:
        return json.load(f)


class TestI18nFallback(unittest.TestCase):
    def test_missing_language_falls_back_to_en(self):
        tr = i18n.I18n("not_a_language")
        self.assertEqual(tr.tr("nav.overview"), "Overview")

    def test_missing_key_returns_key(self):
        tr = i18n.I18n("en")
        self.assertEqual(tr.tr("no.such.key.exists"), "no.such.key.exists")

    def test_placeholder_format(self):
        tr = i18n.I18n("en")
        val = tr.tr("quest_page.steps_fmt", min=1, max=3, count=3)
        self.assertIn("1", val)
        self.assertIn("3", val)


class TestNameResolver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        i18n.set_language("zh_CN")
        cls.nr = NameResolver()

    def test_item_name(self):
        self.assertEqual(self.nr.resolve("ITEM_CID", 1000001), "金币")

    def test_character_name(self):
        self.assertEqual(self.nr.resolve("CHARACTER_CID", 10001), "艾琳")

    def test_unknown_returns_none(self):
        self.assertIsNone(self.nr.resolve("ITEM_CID", 999999999))

    def test_format(self):
        self.assertEqual(self.nr.format("ITEM_CID", 1000001), "1000001 (金币)")


class TestGemStatFormula(unittest.TestCase):
    """符文 STAT_INFO_CID 公式回归 (曾出现组错误/写 0)。"""

    def test_known_values(self):
        cases = {
            1310001: 10001,   # 破损斗志 -> 组100 100%
            1310003: 10201,   # 破损活力 -> 组102
            1310004: 10301,   # 破损专注 -> 组103
            1310104: 20301,   # 完整专注 -> 组203
            1310204: 30301,   # 精炼专注 -> 组303
            1310404: 50301,   # 完美专注 -> 组503
            1310405: 50401,   # 完美增幅 -> 组504
        }
        for cid, expect in cases.items():
            with self.subTest(cid=cid):
                self.assertEqual(gem_stat_cid(cid), expect)

    def test_all_gem_items_map_to_known_stats(self):
        gem_stat = load("gem_stat.json")
        for cid in load("item_types.json")["gem"]:
            with self.subTest(cid=cid):
                sid = gem_stat_cid(int(cid))
                self.assertIn(str(sid), gem_stat, "计算的 STAT_INFO_CID 不在 gem_stat 中")
                self.assertNotEqual(sid, 0)


class TestQuestManagerMeta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        i18n.set_language("zh_CN")
        cls.qm = QuestManager(_NoDb())

    def test_quest_and_steps(self):
        q = self.qm.q(10055)
        self.assertTrue(q)
        self.assertEqual(q["steps"], {"min": 1, "max": 7, "count": 7, "max_cnt": 7})
        # 旧数据缺失步骤的任务 (来自 QuestStepData_Export) 必须已补齐
        q29001 = self.qm.q(29001)
        self.assertTrue(q29001.get("steps"), "29001 步骤数据应已补齐")
        self.assertEqual(q29001["steps"]["min"], 1)

    def test_removed_and_new_quests(self):
        self.assertFalse(self.qm.q(30811), "30811 已被游戏删除, 不应存在")
        self.assertTrue(self.qm.q(90063))
        self.assertTrue(self.qm.q(90064))
        # 教程/测试任务应隐藏
        self.assertTrue(self.qm.is_hidden(90063))

    def test_page_grouping(self):
        self.assertEqual(len(self.qm.lines_of("main")), 8)
        self.assertEqual(len(self.qm.lines_of("epic")), 5)
        char_lines = self.qm.lines_of("character")
        self.assertEqual(len(char_lines), 6, "英雄记录应有 6 条线(含 30800 奥赛罗)")
        names = [name for _key, name, _ids in char_lines]
        self.assertIn("奥赛罗", names)
        # 308xx 应归入英雄记录, 不再出现在「其他」
        other_ids = [q for q, _ in self.qm.quests_by_page("other")]
        self.assertFalse([q for q in other_ids if q.startswith("308")])

    def test_unreleased_main(self):
        self.assertTrue(self.qm.is_main_unreleased(11001))
        self.assertFalse(self.qm.is_main_unreleased(10001))

    def test_dynamic_meta(self):
        self.assertEqual(len(self.qm.dynamic), 147)
        d = self.qm.dynamic["1101201"]
        self.assertEqual(d["group"], 101201)
        self.assertIn("zh_CN", d["name"])


class TestQuestManagerWrites(unittest.TestCase):
    """任务完成/进行中的写库逻辑 (CATEGORY 映射 / STEP 写入)。"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("CREATE TABLE tb_quest_complete (USER_DBID INTEGER, QUEST_CID INTEGER, CATEGORY INTEGER, PRIMARY KEY (USER_DBID, QUEST_CID))")
        self.conn.execute("CREATE TABLE tb_quest_hold (USER_DBID INTEGER, QUEST_CID INTEGER, USE_TRACKING INTEGER, STEP_ID INTEGER, CNT INTEGER, FAILED_CNT INTEGER, PRIMARY KEY (USER_DBID, QUEST_CID))")
        self.conn.commit()
        i18n.set_language("zh_CN")
        self.qm = QuestManager(_Stub(self.conn))

    def tearDown(self):
        self.conn.close()

    def test_set_complete_writes_category(self):
        # 10055 = MAIN -> CATEGORY 1
        self.qm.set_complete(10055, 1)
        row = self.conn.execute("SELECT QUEST_CID, CATEGORY FROM tb_quest_complete").fetchone()
        self.assertEqual((row[0], row[1]), (10055, 1))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM tb_quest_hold").fetchone()[0], 0)

    def test_set_hold_writes_step(self):
        self.qm.set_hold(10055, 6, 0)
        row = self.conn.execute("SELECT QUEST_CID, STEP_ID, CNT FROM tb_quest_hold").fetchone()
        self.assertEqual((row[0], row[1], row[2]), (10055, 6, 0))
        self.qm.set_hold(10055, 7, 0, tracking=1)
        row = self.conn.execute("SELECT STEP_ID, USE_TRACKING FROM tb_quest_hold").fetchone()
        self.assertEqual((row[0], row[1]), (7, 1))

    def test_reset_quest(self):
        self.qm.set_complete(10055, 1)
        self.qm.reset_quest(10055)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM tb_quest_complete").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM tb_quest_hold").fetchone()[0], 0)


class _Stub:
    """QuestManager 写操作所需的最小 data 接口。"""

    def __init__(self, conn):
        self.conn = conn
        self.db_path = ""

    def select_all(self, table, where=None, args=()):
        sql = "SELECT * FROM %s" % table
        if where:
            sql += " WHERE " + where
        return self.conn.execute(sql, args).fetchall()

    def execute(self, sql, params=()):
        self.conn.execute(sql, params)
        self.conn.commit()


class _NoDb:
    conn = None
    db_path = None


if __name__ == "__main__":
    unittest.main()
