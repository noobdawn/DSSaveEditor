# -*- coding: utf-8 -*-
"""异常修复页 (RepairPage): QTabWidget 容器, 子功能 tab 承载各类存档异常修复。

子功能:
  1. 时间修复 (TimeRepairTab) —— 检测并修复存档时间字段异常,
     如 PLAY_TIME 被写成负巨值导致游戏显示 -25 亿小时/无法打开存档。
  2. 副本修复 (DungeonRepairTab) —— 主线/讨伐任务已完成但对应副本组
     未写入 tb_active_dungeon (修改器完成主线时只写 quest_complete),
     导致游戏内副本无法进入; 按 quest_dungeon_map 补齐缺失副本组。
后续存档问题修复均在此页面新增子 tab。
"""

import os
import json
import re
import time
import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QSpinBox,
)

from . import i18n
from .config import DATA_DIR
from .datasource import QuestManager, USER_DBID
from .ui_common import make_card


# ============================================================
# 时间修复子页
# ============================================================
class TimeRepairTab(QWidget):
    """检测并修复存档时间字段异常。

    时间字段两类:
      - INTEGER 时间戳/时长: tb_advent_status.PLAY_TIME (游玩秒数),
        各表 CREATED_DATE/DELETED_DATE (Unix 秒)
      - TEXT 日期: tb_user.LAST_LOGIN_TIME / LAST_LOGOUT_TIME / CREATE_DATE
    """

    # (表名, 列名, 类型, 允许值说明, 正常判定)
    # 类型: "int"=Unix秒/时长, "text"=YYYY-MM-DD[ HH:MM:SS]
    # 正常范围: int 时间戳 1973-01-01 (1e8) ~ 2100-01-01 (4.1e9);
    #           PLAY_TIME 时长: 0 ~ 10 年秒数; text 需可解析
    _INT_TIME_MIN = 100_000_000        # 1973-01-01
    _INT_TIME_MAX = 4_102_444_800      # 2100-01-01
    _PLAY_TIME_MAX = 315_360_000       # 10 年秒数
    _TEXT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?$")

    FIELDS = [
        # (表, 列, 类型, i18n key 后缀)
        ("tb_advent_status", "PLAY_TIME", "play", "time_play_time"),
        ("tb_user", "LAST_LOGIN_TIME", "text", "time_last_login"),
        ("tb_user", "LAST_LOGOUT_TIME", "text", "time_last_logout"),
        ("tb_user", "CREATE_DATE", "text", "time_create_date"),
        ("tb_character", "CREATED_DATE", "int", "time_char_created"),
        ("tb_equipment", "CREATED_DATE", "int", "time_eq_created"),
        ("tb_equipment", "DELETED_DATE", "int0", "time_eq_deleted"),
        ("tb_gem", "CREATED_DATE", "int", "time_gem_created"),
        ("tb_gem", "DELETED_DATE", "int0", "time_gem_deleted"),
        ("tb_vehicle", "CREATED_DATE", "int", "time_veh_created"),
        ("tb_karma", "CREATED_DATE", "int", "time_karma_created"),
        ("tb_karma", "DELETED_DATE", "int0", "time_karma_deleted"),
        ("tb_costume", "CREATED_DATE", "int", "time_costume_created"),
        ("tb_cook_item", "CREATED_DATE", "int", "time_cook_created"),
        ("tb_cook_item", "DELETED_DATE", "int0", "time_cook_deleted"),
    ]

    def __init__(self, data, main_window):
        super().__init__()
        self.data = data
        self.main_window = main_window
        self._issues = []      # [(table, col, kind, row_key, value)]
        self._build()

    # ---------- 布局 ----------
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        card, lay = make_card(str(i18n.tr("repair_page.time_title")))
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        hint = QLabel(str(i18n.tr("repair_page.time_hint")))
        hint.setStyleSheet("color: #7f849c; font-size: 9pt;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.scan_btn = QPushButton(str(i18n.tr("repair_page.btn_scan")))
        self.scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scan_btn.clicked.connect(self._scan)
        btn_row.addWidget(self.scan_btn)
        self.fix_btn = QPushButton(str(i18n.tr("repair_page.btn_fix")))
        self.fix_btn.setObjectName("primaryBtn")
        self.fix_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fix_btn.setEnabled(False)
        self.fix_btn.clicked.connect(self._fix)
        btn_row.addWidget(self.fix_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        self.summary_lbl = QLabel(str(i18n.tr("repair_page.scan_pending")))
        self.summary_lbl.setStyleSheet("font-size: 9pt;")
        lay.addWidget(self.summary_lbl)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            str(i18n.tr("repair_page.col_field")),
            str(i18n.tr("repair_page.col_value")),
            str(i18n.tr("repair_page.col_status")),
            str(i18n.tr("repair_page.col_fix")),
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table, 1)

        outer.addWidget(card)

    # ---------- 扫描 ----------
    def reload(self):
        """页面切换/存档打开时自动刷新。"""
        self._scan()

    def _scan(self):
        self._issues = []
        self.fix_btn.setEnabled(False)
        if not self.data.db_path:
            self.summary_lbl.setText(str(i18n.tr("status.no_db")))
            self.table.setRowCount(0)
            return
        rows_out = []
        for table, col, kind, key in self.FIELDS:
            try:
                rows = self.data.select_all(table)
            except Exception:
                rows = []
            if not rows:
                # 空表: 显示一条"无数据"行 (不算异常)
                rows_out.append((f"{table}.{col}", "-", "ok", "-", False))
                continue
            for r in rows:
                val = r[col]
                issue, fix_val = self._check(kind, val)
                display = self._fmt_value(kind, val)
                if issue:
                    rows_out.append((f"{table}.{col}", display, "bad",
                                     self._fmt_fix(kind, fix_val), True))
                    self._issues.append((table, col, kind, r, fix_val))
                else:
                    rows_out.append((f"{table}.{col}", display, "ok", "-", False))
        self._fill_table(rows_out)
        n = len(self._issues)
        if n:
            self.summary_lbl.setText(str(i18n.tr("repair_page.scan_bad", n=n)))
            self.fix_btn.setEnabled(True)
        else:
            self.summary_lbl.setText(str(i18n.tr("repair_page.scan_ok")))

    def _check(self, kind, val):
        """返回 (是否异常, 建议修复值)。"""
        if kind == "text":
            if val is None:
                return True, self._now_text()
            s = str(val).strip()
            if not self._TEXT_RE.match(s):
                return True, self._now_text()
            try:
                datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return True, self._now_text()
            return False, None
        try:
            num = int(val)
        except (TypeError, ValueError):
            return True, int(time.time())
        if kind == "play":
            # PLAY_TIME 是游玩时长(秒), 正常应为 0~数万秒量级;
            # 异常 (负值/int64溢出) 归零即可, 不能填当前时间戳 (会显示成 50 万小时)。
            if num < 0 or num > self._PLAY_TIME_MAX:
                return True, 0
            return False, None
        if kind == "int0" and num == 0:
            return False, None          # DELETED_DATE 0 = 未删除, 正常
        if num < self._INT_TIME_MIN or num > self._INT_TIME_MAX:
            return True, int(time.time())
        return False, None

    def _fmt_value(self, kind, val):
        if val is None:
            return "-"
        if kind == "text":
            return str(val)
        try:
            num = int(val)
        except (TypeError, ValueError):
            return str(val)
        if kind == "play":
            return self._fmt_play(num)
        if num == 0:
            return "0"
        try:
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(num))
        except Exception:
            return str(num)

    def _fmt_fix(self, kind, val):
        if kind == "play":
            return self._fmt_play(val)
        if kind == "text":
            return str(val)
        if val == 0:
            return "0"
        try:
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(val))
        except Exception:
            return str(val)

    @staticmethod
    def _fmt_play(sec):
        sec = max(int(sec), 0)
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        return str(i18n.tr("repair_page.play_fmt", h=h, m=m, s=s))

    @staticmethod
    def _now_text():
        return time.strftime("%Y-%m-%d %H:%M:%S")

    def _fill_table(self, rows_out):
        self.table.setRowCount(len(rows_out))
        ok_text = str(i18n.tr("repair_page.status_ok"))
        bad_text = str(i18n.tr("repair_page.status_bad"))
        for i, (field, val, status, fix, is_bad) in enumerate(rows_out):
            self.table.setItem(i, 0, QTableWidgetItem(field))
            self.table.setItem(i, 1, QTableWidgetItem(val))
            item = QTableWidgetItem(bad_text if is_bad else ok_text)
            if is_bad:
                item.setForeground(Qt.GlobalColor.red)
            self.table.setItem(i, 2, item)
            self.table.setItem(i, 3, QTableWidgetItem(fix))
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, max(self.table.columnWidth(0), 220))

    # ---------- 修复 ----------
    def _fix(self):
        if not self._issues:
            return
        if QMessageBox.question(
                self, str(i18n.tr("dialogs.confirm")),
                str(i18n.tr("repair_page.fix_confirm", n=len(self._issues)))
        ) != QMessageBox.StandardButton.Yes:
            return
        done = 0
        try:
            for table, col, kind, row, fix_val in self._issues:
                # 用主键定位 (user_dbid + 首列 id); 退化: 全表更新
                pk = "USER_DBID"
                try:
                    self.data.execute(
                        "UPDATE {0} SET {1}=? WHERE {2}=?".format(table, col, pk),
                        (fix_val, row[pk]))
                except Exception:
                    self.data.execute(
                        "UPDATE {0} SET {1}=?".format(table, col), (fix_val,))
                done += 1
        except Exception as ex:
            QMessageBox.critical(self, str(i18n.tr("status.error")), str(ex))
            return
        self.main_window.set_status(str(i18n.tr("repair_page.fixed", n=done)))
        self._scan()


# ============================================================
# 副本修复子页
# ============================================================
class DungeonRepairTab(QWidget):
    """检测并修复副本组激活缺失。

    真实游玩时, 主线任务的 ENTER_DUNGEON 步骤/讨伐任务通关 (组级 QUEST_CLEAR)
    会把对应副本组写入 tb_active_dungeon; 修改器直接完成主线时只写了
    tb_quest_complete, 导致副本组缺失, 游戏内副本无法进入。
    规则: 已完成任务 -> quest_dungeon_map.json 对应副本组 -> 补齐。
    排除: 无组定义 (晋升专用 30001/30002) 与剧情副本 10002 (攻城战,
    真实游玩存档验证不进 active)。
    """

    # 剧情/一次性副本组: 真实游玩存档验证不常驻 active, 修复时跳过
    SKIP_GROUPS = {10002}

    def __init__(self, data, main_window):
        super().__init__()
        self.data = data
        self.main_window = main_window
        self.dungeon_groups = self._load_json("dungeon_groups.json")     # id -> {name,...}
        self.quest_map = self._load_json("quest_dungeon_map.json")       # quest -> [groups]
        self._missing = []      # [(group_id, quest_cid)]
        self._build()

    @staticmethod
    def _load_json(name):
        """加载 data 下 JSON; 失败返回 {}。"""
        try:
            path = os.path.join(DATA_DIR, name)
            if not os.path.exists(path):
                return {}
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        card, lay = make_card(str(i18n.tr("repair_page.dungeon_title")))
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        hint = QLabel(str(i18n.tr("repair_page.dungeon_hint")))
        hint.setStyleSheet("color: #7f849c; font-size: 9pt;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.scan_btn = QPushButton(str(i18n.tr("repair_page.btn_scan")))
        self.scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scan_btn.clicked.connect(self._scan)
        btn_row.addWidget(self.scan_btn)
        self.fix_btn = QPushButton(str(i18n.tr("repair_page.btn_fix")))
        self.fix_btn.setObjectName("primaryBtn")
        self.fix_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fix_btn.setEnabled(False)
        self.fix_btn.clicked.connect(self._fix)
        btn_row.addWidget(self.fix_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        self.summary_lbl = QLabel(str(i18n.tr("repair_page.dungeon_pending")))
        self.summary_lbl.setStyleSheet("font-size: 9pt;")
        lay.addWidget(self.summary_lbl)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([
            str(i18n.tr("repair_page.col_group")),
            str(i18n.tr("repair_page.col_unlock")),
            str(i18n.tr("repair_page.col_status")),
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table, 1)

        outer.addWidget(card)

    def reload(self):
        """页面切换/存档打开时自动刷新。"""
        self._scan()

    # ---------- 扫描 ----------
    def _scan(self):
        self._missing = []
        self.fix_btn.setEnabled(False)
        if not self.data.db_path:
            self.summary_lbl.setText(str(i18n.tr("status.no_db")))
            self.table.setRowCount(0)
            return
        if not self.quest_map:
            self.summary_lbl.setText(str(i18n.tr("repair_page.dungeon_no_data")))
            self.table.setRowCount(0)
            return
        try:
            done = set(r["QUEST_CID"] for r in self.data.select_all("tb_quest_complete"))
        except Exception:
            done = set()
        try:
            active = set(r["DUNGEON_GROUP_CID"] for r in self.data.select_all("tb_active_dungeon"))
        except Exception:
            active = set()

        # 期望激活的副本组: 已完成任务 -> quest_map
        expect = set()
        for quest_cid, groups in self.quest_map.items():
            if int(quest_cid) not in done:
                continue
            for g in groups:
                g = int(g)
                if g in self.SKIP_GROUPS:
                    continue
                if str(g) not in self.dungeon_groups:
                    continue       # 无组定义 (晋升专用等)
                expect.add(g)

        # 缺失列表 (排序: 期望顺序 -> id)
        ordered = []
        for quest_cid, groups in self.quest_map.items():
            if int(quest_cid) not in done:
                continue
            for g in groups:
                g = int(g)
                if g in expect and g not in active and g not in [x[0] for x in ordered]:
                    ordered.append((g, quest_cid))
        self._missing = ordered

        rows_out = []
        for g, q in ordered:
            info = self.dungeon_groups.get(str(g), {})
            rows_out.append((g, info.get("name") or info.get("memo") or f"#{g}", q, "bad"))
        n = len(rows_out)
        self.table.setRowCount(n)
        ok_text = str(i18n.tr("repair_page.status_bad"))
        for i, (g, name, q, _st) in enumerate(rows_out):
            self.table.setItem(i, 0, QTableWidgetItem(f"{g}  {name}"))
            self.table.setItem(i, 1, QTableWidgetItem(str(i18n.tr("repair_page.unlock_quest", qid=q))))
            item = QTableWidgetItem(ok_text)
            item.setForeground(Qt.GlobalColor.red)
            self.table.setItem(i, 2, item)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, max(self.table.columnWidth(0), 260))

        if n:
            self.summary_lbl.setText(str(i18n.tr("repair_page.dungeon_bad", n=n)))
            self.fix_btn.setEnabled(True)
        else:
            self.summary_lbl.setText(str(i18n.tr("repair_page.dungeon_ok")))

    # ---------- 修复 ----------
    def _fix(self):
        if not self._missing:
            return
        if QMessageBox.question(
                self, str(i18n.tr("dialogs.confirm")),
                str(i18n.tr("repair_page.dungeon_fix_confirm", n=len(self._missing)))
        ) != QMessageBox.StandardButton.Yes:
            return
        done = 0
        try:
            for g, _q in self._missing:
                self.data.execute(
                    "INSERT INTO tb_active_dungeon (USER_DBID, DUNGEON_GROUP_CID) VALUES (?,?)",
                    (1000, g))
                done += 1
        except Exception as ex:
            QMessageBox.critical(self, str(i18n.tr("status.error")), str(ex))
            return
        self.main_window.set_status(str(i18n.tr("repair_page.dungeon_fixed", n=done)))
        self._scan()


# ============================================================
# 任务步骤修复子页
# ============================================================
class QuestRepairTab(QWidget):
    """检测并修复进行中任务的步骤异常。

    场景: 直接改任务步骤 (跳过中间步骤) 会导致游戏内 NPC/刷怪不生成,
    任务卡死无法推进 (如冒险任务45卡在对话步骤)。本页可:
      - 扫描进行中任务, 校验 STEP_ID 是否在有效范围内;
      - 回退一步 / 重置到起始步骤 / 手动设为指定步骤, 让游戏重新执行步骤。
    元数据来自 quest_data.json (steps.min/max/count)。
    """

    def __init__(self, data, main_window):
        super().__init__()
        self.data = data
        self.main_window = main_window
        self.qm = QuestManager(data)
        self._rows = []      # [(qid, name, step, cnt, steps_meta, status_key)]
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        card, lay = make_card(str(i18n.tr("repair_page.quest_title")))
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        hint = QLabel(str(i18n.tr("repair_page.quest_hint")))
        hint.setStyleSheet("color: #7f849c; font-size: 9pt;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.scan_btn = QPushButton(str(i18n.tr("repair_page.btn_scan")))
        self.scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scan_btn.clicked.connect(self._scan)
        btn_row.addWidget(self.scan_btn)

        self.back_btn = QPushButton(str(i18n.tr("repair_page.btn_step_back")))
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.clicked.connect(lambda: self._adjust_step(-1))
        btn_row.addWidget(self.back_btn)

        self.reset_btn = QPushButton(str(i18n.tr("repair_page.btn_step_reset")))
        self.reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_btn.clicked.connect(self._reset_start)
        btn_row.addWidget(self.reset_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        # 手动设为指定步骤
        set_row = QHBoxLayout()
        set_row.setSpacing(6)
        set_row.addWidget(QLabel(str(i18n.tr("repair_page.step_set_label"))))
        self.step_spin = QSpinBox()
        self.step_spin.setRange(0, 999)
        self.step_spin.setValue(1)
        set_row.addWidget(self.step_spin)
        self.apply_btn = QPushButton(str(i18n.tr("repair_page.btn_step_apply")))
        self.apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_btn.clicked.connect(self._apply_step)
        set_row.addWidget(self.apply_btn)
        set_row.addStretch(1)
        lay.addLayout(set_row)

        self.summary_lbl = QLabel(str(i18n.tr("repair_page.quest_pending")))
        self.summary_lbl.setStyleSheet("font-size: 9pt;")
        lay.addWidget(self.summary_lbl)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            str(i18n.tr("repair_page.col_quest")),
            str(i18n.tr("repair_page.col_step")),
            str(i18n.tr("repair_page.col_range")),
            str(i18n.tr("repair_page.col_status")),
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_select)
        lay.addWidget(self.table, 1)

        outer.addWidget(card)

    def _on_select(self):
        """选中行时把当前步骤填入 spin。"""
        r = self.table.currentRow()
        if 0 <= r < len(self._rows):
            step = self._rows[r][2]
            self.step_spin.setValue(int(step))

    def reload(self):
        self._scan()

    # ---------- 扫描 ----------
    def _scan(self):
        self._rows = []
        if not self.data.db_path:
            self.summary_lbl.setText(str(i18n.tr("status.no_db")))
            self.table.setRowCount(0)
            return
        try:
            holds = self.data.select_all("tb_quest_hold")
        except Exception:
            holds = []
        bad = 0
        rows = []
        for h in holds:
            qid = int(h["QUEST_CID"])
            step = int(h["STEP_ID"] or 0)
            cnt = int(h["CNT"] or 0)
            meta = self.qm.q(qid)
            steps = meta.get("steps")
            if not meta:
                status = "unknown"
                rng = "-"
            elif not steps:
                status = "no_steps"
                rng = "-"
            else:
                smin, smax = int(steps.get("min", 0)), int(steps.get("max", 0))
                rng = f"{smin} ~ {smax}"
                if step < smin or step > smax:
                    status = "bad"
                else:
                    status = "ok"
            if status in ("bad", "unknown", "no_steps"):
                bad += 1
            name = self.qm.qname(qid) or f"ID {qid}"
            rows.append((qid, name, step, cnt, steps, status, rng))
        rows.sort(key=lambda x: x[0])
        self._rows = rows

        self.table.setRowCount(len(rows))
        status_text = {
            "ok": str(i18n.tr("repair_page.quest_status_ok")),
            "bad": str(i18n.tr("repair_page.quest_status_bad")),
            "no_steps": str(i18n.tr("repair_page.quest_status_no_steps")),
            "unknown": str(i18n.tr("repair_page.quest_status_unknown")),
        }
        for i, (qid, name, step, cnt, steps, status, rng) in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(f"{qid}  {name}"))
            self.table.setItem(i, 1, QTableWidgetItem(str(step)))
            self.table.setItem(i, 2, QTableWidgetItem(rng))
            item = QTableWidgetItem(str(status_text.get(status, status)))
            if status in ("bad", "unknown"):
                item.setForeground(Qt.GlobalColor.red)
            elif status == "no_steps":
                item.setForeground(Qt.GlobalColor.yellow)
            self.table.setItem(i, 3, item)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, max(self.table.columnWidth(0), 280))

        if not rows:
            self.summary_lbl.setText(str(i18n.tr("repair_page.quest_ok")))
        elif bad:
            self.summary_lbl.setText(str(i18n.tr("repair_page.quest_bad", n=bad)))
        else:
            self.summary_lbl.setText(str(i18n.tr("repair_page.quest_ok")))

    # ---------- 修复 ----------
    def _selected(self):
        r = self.table.currentRow()
        if r < 0 or r >= len(self._rows):
            QMessageBox.information(self, str(i18n.tr("dialogs.confirm")),
                                    str(i18n.tr("repair_page.quest_select_first")))
            return None
        return self._rows[r]

    def _set_step(self, row, new_step):
        """更新任务步骤 (CNT 归零)。"""
        qid = row[0]
        try:
            self.data.execute(
                "UPDATE tb_quest_hold SET STEP_ID=?, CNT=0 WHERE USER_DBID=? AND QUEST_CID=?",
                (int(new_step), USER_DBID, qid))
        except Exception as ex:
            QMessageBox.critical(self, str(i18n.tr("status.error")), str(ex))
            return False
        return True

    def _adjust_step(self, delta):
        row = self._selected()
        if row is None:
            return
        qid, name, step, cnt, steps, status, rng = row
        if not steps:
            QMessageBox.information(self, str(i18n.tr("repair_page.quest_title")),
                                    str(i18n.tr("repair_page.quest_status_no_steps")))
            return
        smin, smax = int(steps.get("min", 0)), int(steps.get("max", 0))
        new_step = max(smin, min(smax, step + delta))
        if new_step == step:
            self.main_window.set_status(str(i18n.tr("repair_page.quest_step_same")))
            return
        if not self._set_step(row, new_step):
            return
        self.main_window.set_status(str(i18n.tr("repair_page.quest_step_changed", name=name, step=new_step)))
        self._scan()

    def _reset_start(self):
        row = self._selected()
        if row is None:
            return
        qid, name, step, cnt, steps, status, rng = row
        if not steps:
            QMessageBox.information(self, str(i18n.tr("repair_page.quest_title")),
                                    str(i18n.tr("repair_page.quest_status_no_steps")))
            return
        smin = int(steps.get("min", 0))
        if not self._set_step(row, smin):
            return
        self.main_window.set_status(str(i18n.tr("repair_page.quest_step_changed", name=name, step=smin)))
        self._scan()

    def _apply_step(self):
        row = self._selected()
        if row is None:
            return
        qid, name, step, cnt, steps, status, rng = row
        target = int(self.step_spin.value())
        if steps:
            smin, smax = int(steps.get("min", 0)), int(steps.get("max", 0))
            if target < smin or target > smax:
                QMessageBox.information(
                    self, str(i18n.tr("repair_page.quest_title")),
                    str(i18n.tr("repair_page.quest_step_out_of_range", min=smin, max=smax)))
                return
        if not self._set_step(row, target):
            return
        self.main_window.set_status(str(i18n.tr("repair_page.quest_step_changed", name=name, step=target)))
        self._scan()


# ============================================================
# 修复页容器
# ============================================================
class RepairPage(QWidget):
    """异常修复页: QTabWidget 承载各子功能 (时间/副本/任务步骤修复)。"""

    def __init__(self, data, names, main_window):
        super().__init__()
        self.data = data
        self.names = names
        self.main_window = main_window
        self.tabs = QTabWidget()
        self.time_tab = TimeRepairTab(data, main_window)
        self.tabs.addTab(self.time_tab, str(i18n.tr("repair_page.tab_time")))
        self.dungeon_tab = DungeonRepairTab(data, main_window)
        self.tabs.addTab(self.dungeon_tab, str(i18n.tr("repair_page.tab_dungeon")))
        self.quest_tab = QuestRepairTab(data, main_window)
        self.tabs.addTab(self.quest_tab, str(i18n.tr("repair_page.tab_quest")))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.tabs)

    def reload(self):
        self.time_tab.reload()
        self.dungeon_tab.reload()
        self.quest_tab.reload()
