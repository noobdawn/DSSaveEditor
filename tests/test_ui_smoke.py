# -*- coding: utf-8 -*-
"""UI 冒烟测试: 用合成最小数据库实例化全部页面, 断言 reload 不抛异常。

不依赖任何玩家存档。运行: python -m unittest discover -s tests -v
"""
import os
import sqlite3
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from PySide6.QtWidgets import QApplication  # type: ignore
    _HAS_QT = True
except Exception:      # pragma: no cover
    QApplication = None  # type: ignore
    _HAS_QT = False

from app import i18n                       # noqa: E402
from app.datasource import NameResolver, QuestManager   # noqa: E402

SCHEMA = {
    "tb_quest_complete": "USER_DBID INTEGER, QUEST_CID INTEGER, CATEGORY INTEGER, PRIMARY KEY (USER_DBID, QUEST_CID)",
    "tb_quest_hold": "USER_DBID INTEGER, QUEST_CID INTEGER, USE_TRACKING INTEGER, STEP_ID INTEGER, CNT INTEGER, FAILED_CNT INTEGER, PRIMARY KEY (USER_DBID, QUEST_CID)",
    "tb_quest_record_reward": "USER_DBID INTEGER, CARD_ID INTEGER, REWARD_ORDER INTEGER, PRIMARY KEY (USER_DBID, CARD_ID)",
    "tb_dynamic_quest_group": "USER_DBID INTEGER, GROUP_ID INTEGER, LAST_QUEST_ID INTEGER, QUEST_ID INTEGER, STEP INTEGER, CNT INTEGER, FAILED_CNT INTEGER, PRIMARY KEY (USER_DBID, GROUP_ID)",
    "tb_dynamic_quest_complete": "USER_DBID INTEGER, QUEST_ID INTEGER, COMPLETE_CNT INTEGER, PRIMARY KEY (USER_DBID, QUEST_ID)",
    "tb_active_dungeon": "USER_DBID INTEGER, DUNGEON_GROUP_CID INTEGER, PRIMARY KEY (USER_DBID, DUNGEON_GROUP_CID)",
    "tb_advent_status": "USER_DBID INTEGER, ADV_GRADE INTEGER, ADV_LEVEL INTEGER, ADV_EXP INTEGER, CUR_ADV_DIFFICULTY INTEGER, ORIGIN_ADV_DIFFICULTY INTEGER, RESTORE_ADV_DIFFICULTY_UTC_SEC INTEGER, NICK_NAME TEXT, PLAY_TIME INTEGER",
    "tb_user": "USER_DBID INTEGER, REGION_CID INTEGER, SECTION_UID INTEGER, LAST_LOGIN_TIME TEXT, LAST_LOGOUT_TIME TEXT, CREATE_DATE TEXT, NEXT_RESET_DAY INTEGER, NEXT_RESET_WEEK INTEGER, NEXT_RESET_MONTH INTEGER, USER_DB_VERSION INTEGER",
}


class DataStub:
    def __init__(self, path):
        self.db_path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

    def select_all(self, table, where=None, args=()):
        sql = "SELECT * FROM %s" % table
        if where:
            sql += " WHERE " + where
        return self.conn.execute(sql, args).fetchall()

    def execute(self, sql, params=()):
        self.conn.execute(sql, params)
        self.conn.commit()

    def fetchone(self, sql, params=()):
        return self.conn.execute(sql, params).fetchone()

    def list_tables(self):
        return [r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]

    def table_columns(self, table):
        return [(r[1], r[2], r[5]) for r in self.conn.execute("PRAGMA table_info(%s)" % table)]

    def update_cell(self, table, column, value, where, args=()):
        self.conn.execute("UPDATE %s SET %s=? WHERE %s" % (table, column, where), (value,) + tuple(args))
        self.conn.commit()

    def delete_row(self, table, where, args=()):
        self.conn.execute("DELETE FROM %s WHERE %s" % (table, where), args)
        self.conn.commit()


class MWStub:
    @staticmethod
    def set_status(msg):
        pass


@unittest.skipUnless(_HAS_QT, "PySide6 不可用")
class TestPagesSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        i18n.set_language("zh_CN")
        fd, cls.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = sqlite3.connect(cls.db_path)
        for name, cols in SCHEMA.items():
            conn.execute("CREATE TABLE %s (%s)" % (name, cols))
        # 一条进行中任务 + 一条越界步骤, 供任务步骤修复测试
        conn.execute("INSERT INTO tb_quest_hold VALUES (1000, 10055, 0, 7, 0, 0)")
        conn.execute("INSERT INTO tb_quest_hold VALUES (1000, 29001, 0, 99, 0, 0)")
        conn.execute("INSERT INTO tb_advent_status VALUES (1000,1,1,0,1,1,0,'测试',3067)")
        conn.execute("INSERT INTO tb_user VALUES (1000,100,2022090000100,'2026-01-01 00:00:00','2026-01-01 00:00:00','2026-01-01 00:00:00',0,0,0,1)")
        conn.commit()
        conn.close()
        cls.data = DataStub(cls.db_path)
        cls.names = NameResolver()
        cls.qm = QuestManager(cls.data)

    @classmethod
    def tearDownClass(cls):
        cls.data.conn.close()
        os.remove(cls.db_path)

    def _page_classes(self):
        from app.ui_overview import OverviewPage
        from app.ui_character import CharacterPage
        from app.ui_karma import KarmaPage
        from app.ui_vehicle import VehiclePage
        from app.ui_rune import RunePage
        from app.ui_equipment import EquipmentPage
        from app.ui_inventory import InventoryPage
        from app.ui_quest import QuestPage, RegionQuestPage
        from app.ui_tools import DataToolsPage
        from app.ui_repair import RepairPage
        return [
            ("overview", lambda: OverviewPage(self.data, self.names, MWStub())),
            ("character", lambda: CharacterPage(self.data, self.names, MWStub())),
            ("karma", lambda: KarmaPage(self.data, self.names, MWStub())),
            ("vehicle", lambda: VehiclePage(self.data, self.names, MWStub())),
            ("rune", lambda: RunePage(self.data, self.names, MWStub())),
            ("equipment", lambda: EquipmentPage(self.data, self.names, MWStub())),
            ("inventory", lambda: InventoryPage(self.data, self.names, MWStub())),
            ("quest_main", lambda: QuestPage(self.data, self.names, MWStub(), self.qm, "main")),
            ("quest_epic", lambda: QuestPage(self.data, self.names, MWStub(), self.qm, "epic")),
            ("quest_character", lambda: QuestPage(self.data, self.names, MWStub(), self.qm, "character")),
            ("quest_region", lambda: RegionQuestPage(self.data, self.names, MWStub(), self.qm)),
            ("quest_grade", lambda: QuestPage(self.data, self.names, MWStub(), self.qm, "grade")),
            ("quest_other", lambda: QuestPage(self.data, self.names, MWStub(), self.qm, "other")),
            ("quest_unreleased", lambda: QuestPage(self.data, self.names, MWStub(), self.qm, "unreleased")),
            ("tools", lambda: DataToolsPage(self.data, self.names, MWStub())),
            ("repair", lambda: RepairPage(self.data, self.names, MWStub())),
        ]

    def test_all_pages_construct_and_reload(self):
        for key, ctor in self._page_classes():
            with self.subTest(page=key):
                page = ctor()
                page.reload()

    def test_repair_tabs_scan(self):
        from app.ui_repair import RepairPage
        page = RepairPage(self.data, self.names, MWStub())
        page.time_tab._scan()
        page.dungeon_tab._scan()
        page.quest_tab._scan()
        self.assertEqual(page.tabs.count(), 3)

    def test_quest_step_repair_detection(self):
        from app.ui_repair import QuestRepairTab
        tab = QuestRepairTab(self.data, MWStub())
        tab._scan()
        by_qid = {row[0]: row for row in tab._rows}
        self.assertIn(10055, by_qid)
        self.assertIn(29001, by_qid)
        self.assertEqual(by_qid[10055][5], "ok")       # step 7 在 1~7
        self.assertEqual(by_qid[29001][5], "bad")      # step 99 越界

    def test_add_dialogs_data(self):
        from app.ui_equipment import EquipmentPage, AddEquipmentDialog
        from app.ui_inventory import InventoryPage, AddItemDialog
        eq = EquipmentPage(self.data, self.names, MWStub())
        dlg = AddEquipmentDialog(self.names, eq.stat_names, eq.equip_items, eq)
        self.assertEqual(len(dlg.equip_items), 240)
        self.assertEqual(dlg.series_combo.count(), 4)
        self.assertEqual(dlg.part_combo.count(), 5)
        self.assertGreater(dlg.main_combo.count(), 0)
        self.assertTrue(all(c.count() > 0 for c in dlg.sub_combos))

        inv = InventoryPage(self.data, self.names, MWStub())
        ad = AddItemDialog(self.data, self.names, inv)
        self.assertGreater(ad.item_list.count(), 0)
        ad.type_combo.setCurrentIndex(1)      # 料理
        self.assertGreater(ad.item_list.count(), 0)

    def test_rune_and_vehicle_counts(self):
        from app.ui_rune import RunePage
        from app.ui_vehicle import VehiclePage
        rune = RunePage(self.data, self.names, MWStub())
        self.assertEqual(len(rune.rune_cids), 25)
        self.assertEqual(len(rune.gem_stat), 120)
        vp = VehiclePage(self.data, self.names, MWStub())
        self.assertEqual(len(vp.vehicles), 30)


if __name__ == "__main__":
    unittest.main()
