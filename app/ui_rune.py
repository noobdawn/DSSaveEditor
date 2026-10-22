# -*- coding: utf-8 -*-
"""符文页 (RunePage + AddRuneDialog): 左符文列表 (自定义行) + 新增/删除。

tb_gem 每件符文独立实例 (ITEM_DBID 大数); 属性效果从 gem_stat.json (GemNewStatData) 格式化。
"""

import os
import json
import time

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QLabel, QPushButton, QSpinBox, QDialog,
    QDialogButtonBox, QMessageBox,
)

from . import i18n
from .config import DATA_DIR
from .datasource import USER_DBID, localize_name


# ============================================================
# 符文页
# ============================================================
class RunePage(QWidget):
    """符文: 自定义列表 (名称 + 属性效果), 每行一个符文实例 + 新增/删除。"""

    ROW_V_PAD = 12
    ROW_SPACING = 2

    def __init__(self, data, names, main_window):
        super().__init__()
        self.data = data
        self.names = names
        self.main_window = main_window
        # 符文属性表 (gem_stat.json: {STAT_INFO_CID: {stat, ratio}})
        self.gem_stat = self._load_gem_stat()
        # 属性名映射 (stat_names.json stat_key)
        self.stat_names = self._load_stat_names()
        # 可新增符文 CID 清单 (item_types.json gem 数组)
        self.rune_cids = self._load_rune_cids()
        self._rows = []           # tb_gem 有效行
        self._current_dbid = None
        self._build()

    @staticmethod
    def _load_gem_stat():
        """加载 gem_stat.json; 失败返回 {}。"""
        try:
            path = os.path.join(DATA_DIR, "gem_stat.json")
            if not os.path.exists(path):
                return {}
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _load_stat_names():
        """加载 stat_names.json; 失败返回 {}。"""
        try:
            path = os.path.join(DATA_DIR, "stat_names.json")
            if not os.path.exists(path):
                return {}
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _load_rune_cids():
        """加载 item_types.json 的 gem 数组 (可新增符文 CID); 失败返回 []。"""
        try:
            path = os.path.join(DATA_DIR, "item_types.json")
            if not os.path.exists(path):
                return []
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return list(data.get("gem", [])) if isinstance(data, dict) else []
        except Exception:
            return []

    # ---------- 布局 ----------
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        hint = QLabel(str(i18n.tr("rune_page.hint")))
        hint.setStyleSheet("color: #7f849c; font-size: 9pt;")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(str(i18n.tr("rune_page.search")))
        self.search_box.textChanged.connect(self._on_search)
        outer.addWidget(self.search_box)

        self.rune_list = QListWidget()
        self.rune_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.rune_list.currentRowChanged.connect(self._on_select)
        self.rune_list.setSpacing(2)
        outer.addWidget(self.rune_list, 1)

        # 底部按钮行
        btn_row = QHBoxLayout()
        self.add_btn = QPushButton(str(i18n.tr("rune_page.add")))
        self.add_btn.setObjectName("primaryBtn")
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.clicked.connect(self._open_add_dialog)
        btn_row.addWidget(self.add_btn)
        self.del_btn = QPushButton(str(i18n.tr("rune_page.delete")))
        self.del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.del_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(self.del_btn)
        btn_row.addStretch(1)
        outer.addLayout(btn_row)

    # ---------- 数据 ----------
    def reload(self):
        self._rows = []
        self._current_dbid = None
        has_db = self.data.db_path is not None
        self.add_btn.setEnabled(has_db)
        self.del_btn.setEnabled(has_db)
        if not has_db:
            self.rune_list.clear()
            return
        try:
            rows = self.data.select_all(
                "tb_gem", "USER_DBID=? AND DELETED_DATE=0", (USER_DBID,))
        except Exception:
            rows = []
        self._rows = sorted(rows, key=lambda r: r["ITEM_CID"])
        self._rebuild_list()

    def _rune_name(self, cid):
        resolved = self.names.resolve("ITEM_CID", cid)
        if resolved:
            return str(resolved)
        return f"#{cid}"

    def _effect_text(self, stat_cid):
        """符文属性类型: 按实例 STAT_INFO_CID 查 gem_stat (GemNewStatData).
        gem_stat.json: {STAT_INFO_CID: {"stat": StatList, "ratio": 档位}};
        只显示属性类型 (游戏内数值由客户端公式计算, 数据表未导出, 以游戏为准)。"""
        info = (self.gem_stat or {}).get(str(stat_cid))
        if not info:
            return "-"
        name = self._stat_cn(info.get("stat")) or info.get("stat")
        return str(name) if name else "-"

    def _stat_cn(self, stat):
        """属性英文名 -> 本地化名 (stat_key, 大小写无关匹配); 找不到返回 None。"""
        if not self.stat_names:
            return None
        sk = self.stat_names.get("stat_key", {})
        key = stat.upper()
        for k, v in sk.items():
            if isinstance(v, dict) and "name" in v and k.upper() == key:
                return localize_name(v["name"])
        return None

    def _rebuild_list(self):
        self.rune_list.clear()
        kw = self.search_box.text().strip().lower()
        for r in self._rows:
            cid = r["ITEM_CID"]
            dbid = r["ITEM_DBID"]
            name = self._rune_name(cid)
            if kw and kw not in str(cid).lower() and kw not in name.lower():
                continue
            row = self._make_row_widget(cid, dbid, name, r["STAT_INFO_CID"])
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, row.height()))
            item.setData(Qt.ItemDataRole.UserRole, dbid)
            self.rune_list.addItem(item)
            self.rune_list.setItemWidget(item, row)

    def _make_row_widget(self, cid, dbid, name, stat_cid):
        """单行: 第一行 符文名(粗体) + 属性效果(灰); 第二行 DBID 后 6 位(更小灰字)。"""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(self.ROW_SPACING)

        top = QHBoxLayout()
        top.setSpacing(6)
        name_lbl = QLabel(name)
        f = name_lbl.font()
        f.setBold(True)
        name_lbl.setFont(f)
        top.addWidget(name_lbl)
        top.addStretch(1)
        eff = self._effect_text(stat_cid)
        eff_lbl = QLabel(eff)
        eff_lbl.setStyleSheet("color: #98c379; font-size: 9pt;")
        top.addWidget(eff_lbl)
        lay.addLayout(top)

        sub = QLabel(f"#{str(dbid)[-6:]}  ·  CID {cid}")
        sub.setStyleSheet("color: #7f849c; font-size: 8pt;")
        lay.addWidget(sub)

        # 自适应高度
        avail_w = max(self.rune_list.viewport().width() - 20, 240)
        desc_h = max(eff_lbl.sizeHint().height(), 16)
        name_h = name_lbl.sizeHint().height()
        total = self.ROW_V_PAD + name_h + desc_h
        if desc_h > 0:
            total += self.ROW_SPACING
        w.setFixedHeight(total)
        return w

    def _on_select(self, row_idx):
        if row_idx < 0 or row_idx >= self.rune_list.count():
            return
        item = self.rune_list.item(row_idx)
        if item is None:
            return
        dbid = item.data(Qt.ItemDataRole.UserRole)
        if dbid is None:
            return
        self._current_dbid = dbid

    # ---------- 新增 / 删除 ----------
    def _open_add_dialog(self):
        if not self.data.db_path:
            QMessageBox.information(self, "", str(i18n.tr("status.no_db")))
            return
        dlg = AddRuneDialog(self.data, self.names, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.reload()
            self.main_window.set_status(str(i18n.tr("rune_page.added",
                                                    n=dlg.added_count)))

    def _delete_selected(self):
        if self._current_dbid is None:
            QMessageBox.information(self, str(i18n.tr("dialogs.confirm")),
                                    str(i18n.tr("rune_page.select_first")))
            return
        dbid = self._current_dbid
        name = self._rune_name(self._row_cid(dbid)) or f"#{dbid}"
        if QMessageBox.question(
                self, str(i18n.tr("dialogs.confirm")),
                str(i18n.tr("rune_page.delete_confirm", name=name))
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.data.execute("DELETE FROM tb_gem WHERE USER_DBID=? AND ITEM_DBID=?",
                              (USER_DBID, dbid))
        except Exception as ex:
            QMessageBox.critical(self, str(i18n.tr("status.error")), str(ex))
            return
        self.main_window.set_status(str(i18n.tr("rune_page.deleted", n=1)))
        self._current_dbid = None
        self.reload()

    def _row_cid(self, dbid):
        for r in self._rows:
            if r["ITEM_DBID"] == dbid:
                return r["ITEM_CID"]
        return None

    # ---------- 搜索 ----------
    def _on_search(self, _text):
        self._rebuild_list()


def gem_stat_cid(item_cid):
    """符文 ITEM_CID -> STAT_INFO_CID (GemNewStatData.GemStatID, 100% 档)。

    规则: ITEM_CID 结构 1310XYZ
      X  = 品质 (0破损/1完整/2精炼/3璀璨/4完美)
      YZ = 系别 (01斗志/02守护/03活力/04专注/05增幅)
    组 = (品质+1)*100 + (系别-1)  -> 100~104 / 200~204 / ... / 500~504
    STAT_INFO_CID = 组*100 + 档位 (01=100%)
    写入 0 会被游戏忽略 (符文不显示)。
    """
    quality = (int(item_cid) // 100) % 10
    series = int(item_cid) % 100
    return ((quality + 1) * 100 + (series - 1)) * 100 + 1


# ============================================================
# 新增符文对话框
# ============================================================
class AddRuneDialog(QDialog):
    """新增符文: 搜索并选符文 -> 数量 (每件独立实例) -> 写入 tb_gem。"""

    def __init__(self, data, names, parent):
        super().__init__(parent)
        self.data = data
        self.names = names
        self.added_count = 0
        # 可新增符文 CID (从父页 RunePage 复用)
        self.rune_cids = list(getattr(parent, "rune_cids", None) or [])
        if not self.rune_cids:
            self.rune_cids = RunePage._load_rune_cids()
        self.setWindowTitle(str(i18n.tr("rune_page.add_title")))
        self.setMinimumSize(420, 460)
        self._build()
        self._refresh_list()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(str(i18n.tr("rune_page.search")))
        self.search_box.textChanged.connect(lambda _t: self._refresh_list())
        lay.addWidget(self.search_box)

        self.item_list = QListWidget()
        self.item_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        lay.addWidget(self.item_list, 1)

        cnt_row = QHBoxLayout()
        cnt_row.addWidget(QLabel(str(i18n.tr("rune_page.count"))))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 99)
        self.count_spin.setValue(1)
        cnt_row.addWidget(self.count_spin)
        cnt_row.addStretch(1)
        lay.addLayout(cnt_row)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(str(i18n.tr("dialogs.ok")))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(str(i18n.tr("dialogs.cancel")))
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _refresh_list(self):
        self.item_list.clear()
        cids = list(self.rune_cids)
        kw = self.search_box.text().strip().lower()
        if kw:
            cids = [c for c in cids
                    if kw in c.lower()
                    or kw in str(self.names.resolve("ITEM_CID", int(c)) or "").lower()]
        cids.sort(key=lambda c: int(c))
        for cid in cids:
            name = self.names.resolve("ITEM_CID", int(cid)) or f"#{cid}"
            it = QListWidgetItem(f"{cid} {name}")
            it.setData(Qt.ItemDataRole.UserRole, cid)
            self.item_list.addItem(it)

    def _new_item_dbid(self):
        """生成不冲突的 ITEM_DBID (时间戳<<28 | 随机28位, 查 tb_gem 去重)。"""
        import random
        while True:
            v = (int(time.time()) << 28) | random.getrandbits(28)
            exists = self.data.select_all("tb_gem", "ITEM_DBID=?", (v,))
            if not exists:
                return v

    def _on_ok(self):
        cur = self.item_list.currentItem()
        if cur is None:
            QMessageBox.information(self, str(i18n.tr("dialogs.confirm")),
                                    str(i18n.tr("rune_page.select_first")))
            return
        cid = int(cur.data(Qt.ItemDataRole.UserRole))
        cnt = self.count_spin.value()
        now = int(time.time())
        stat_cid = gem_stat_cid(cid)
        try:
            for _ in range(cnt):
                new_dbid = self._new_item_dbid()
                self.data.execute(
                    "INSERT INTO tb_gem (ITEM_DBID, USER_DBID, ITEM_CID, "
                    "STAT_INFO_CID, IS_LOCK, CREATED_DATE, DELETED_DATE) "
                    "VALUES (?,?,?,?,0,?,0)",
                    (new_dbid, USER_DBID, cid, stat_cid, now))
        except Exception as ex:
            QMessageBox.critical(self, str(i18n.tr("status.error")), str(ex))
            return
        self.added_count = cnt
        self.accept()
