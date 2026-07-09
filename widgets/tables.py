"""
ui/widgets/tables.py
─────────────────────
Reusable Qt Model/View components for the Risk Register.

RiskTableModel  — QAbstractTableModel backed by a list of risk dicts.
                  Virtualised: only visible rows are painted regardless
                  of total dataset size.

RiskDelegate    — QStyledItemDelegate that paints severity colour badges,
                  NIST function colours, status pills, and treatment count
                  indicators per-cell without creating widget objects per row.
                  This is the fix for the CustomTkinter crash: 1,000 risks
                  = zero extra widget objects; Qt renders visible cells only.

TreatmentTableModel / TreatmentDelegate — same pattern for the Treatments page.
"""

from __future__ import annotations
from typing import Any

from PySide6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel,
    Signal,
)
from PySide6.QtGui import (
    QColor, QFont, QPainter, QBrush, QPen,
)
from PySide6.QtWidgets import (
    QStyledItemDelegate, QStyleOptionViewItem,
    QApplication, QStyle,
)

from assets.themes.design_system import Colors, Fonts
from core.database.lookups import cis_display, mitre_display


# ── Risk columns ──────────────────────────────────────────────────────────────

RISK_COLUMNS = [
    ("score",        "Score",   90),
    ("title",        "Title",   0),    # flexible — stretches
    ("nist_function","NIST",    110),
    ("cia_component","CIA",     120),
    ("mitre_tactic", "MITRE",   150),
    ("owner",        "Owner",   140),
    ("status",       "Status",  110),
    ("treat_count",  "Treatments", 90),
    ("source",       "Src",     50),
]

COL_IDX = {col[0]: i for i, col in enumerate(RISK_COLUMNS)}


class RiskTableModel(QAbstractTableModel):
    """
    Virtualised table model for the risk register.

    Data is stored as a list of plain dicts (from get_risks()).
    Treatment counts are passed in separately as a dict {risk_id: count}
    to avoid N+1 queries — the register page does one bulk count query
    and passes it in, never querying per-row.
    """

    def __init__(self, risks: list[dict], tc_map: dict[int, int],
                 parent=None):
        super().__init__(parent)
        self._risks   = risks
        self._tc_map  = tc_map

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._risks)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(RISK_COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if (orientation == Qt.Orientation.Horizontal and
                role == Qt.ItemDataRole.DisplayRole):
            return RISK_COLUMNS[section][1]
        if (orientation == Qt.Orientation.Horizontal and
                role == Qt.ItemDataRole.FontRole):
            return Fonts.label_sm_bold()
        return None

    def data(self, index: QModelIndex,
             role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        if row >= len(self._risks):
            return None
        r = self._risks[row]

        col_key = RISK_COLUMNS[col][0]
        sc = int(r.get("risk_score") or 0)

        if role == Qt.ItemDataRole.DisplayRole:
            if col_key == "score":
                return f"{sc}"
            if col_key == "title":
                return str(r.get("title") or "")
            if col_key == "nist_function":
                return str(r.get("nist_function") or "—")
            if col_key == "cia_component":
                return str(r.get("cia_component") or "—")
            if col_key == "mitre_tactic":
                t = str(r.get("mitre_tactic") or "—")
                if t and t not in ("—","Not Applicable"):
                    try:
                        from core.database.lookups import get_mitre_info
                        info = get_mitre_info(t)
                        tid  = info.get("id","")
                        if tid and tid != "—":
                            return f"{tid}  ·  {t}"
                    except Exception:
                        pass
                    return t
                return "—"
            if col_key == "owner":
                return str(r.get("owner") or "—")
            if col_key == "status":
                st = str(r.get("status") or "—")
                icons = {"Open":"🔴", "In Progress":"🟡",
                         "Mitigated":"🟢","Closed":"🟢",
                         "Accepted":"🔵","Verified":"🟢"}
                return f"{icons.get(st,'○')}  {st}"
            if col_key == "treat_count":
                tc = self._tc_map.get(str(r.get("id", -1)), 0)
                return f"✔  {tc} Active" if tc else "—"
            if col_key == "source":
                src = str(r.get("source") or "Manual")
                return src[:3].upper()
            return ""

        if role == Qt.ItemDataRole.ForegroundRole:
            if col_key == "score":
                return QColor(Colors.severity_color(sc))
            if col_key == "nist_function":
                fn = r.get("nist_function", "")
                return QColor(Colors.nist_color(fn))
            if col_key == "cia_component":
                return QColor(Colors.PURPLE_LT)
            if col_key == "mitre_tactic":
                return QColor(Colors.CRITICAL)
            if col_key == "status":
                s = r.get("status", "")
                if s == "Open":     return QColor(Colors.MEDIUM)
                if s in ("Mitigated", "Closed"):
                    return QColor(Colors.SUCCESS_LT)
                return QColor(Colors.TEXT_MUTED)
            if col_key == "treat_count":
                tc = self._tc_map.get(str(r.get("id", -1)), 0)
                return QColor(Colors.SUCCESS_LT if tc else Colors.TEXT_DIM)
            if col_key == "source":
                src = str(r.get("source") or "Manual")
                return QColor(Colors.PURPLE_LT
                               if src == "AI Analysis"
                               else Colors.TEXT_DIM)
            return QColor(Colors.TEXT_PRIMARY)

        if role == Qt.ItemDataRole.BackgroundRole:
            bg = Colors.BG_CARD if row % 2 == 0 else Colors.BG_CARD2
            return QColor(bg)

        if role == Qt.ItemDataRole.FontRole:
            if col_key == "score":
                return Fonts.label_bold()
            if col_key == "title":
                return Fonts.label()
            return Fonts.label_sm()

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col_key in ("score", "treat_count", "source"):
                return int(Qt.AlignmentFlag.AlignCenter)
            return int(Qt.AlignmentFlag.AlignLeft |
                       Qt.AlignmentFlag.AlignVCenter)

        # Note: UserRole intentionally NOT implemented — returning a Python
        # dict via Qt's item data causes Shiboken C++ conversion errors.
        # Use model.risk_at(row) directly from click handlers instead.
        return None

    def risk_at(self, row: int) -> dict | None:
        if 0 <= row < len(self._risks):
            return self._risks[row]
        return None

    def refresh(self, risks: list[dict], tc_map: dict[int, int]) -> None:
        self.beginResetModel()
        self._risks  = risks
        self._tc_map = tc_map
        self.endResetModel()


# ── Risk sort/filter proxy ────────────────────────────────────────────────────

class RiskFilterProxy(QSortFilterProxyModel):
    """
    Proxy that filters on search text across title, owner, and MITRE tactic.
    The actual SQL filtering still happens in get_risks() — this proxy
    handles instant search-as-you-type on the already-loaded dataset
    without a DB round-trip on every keypress.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search = ""
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def set_search(self, text: str) -> None:
        self._search = text.strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int,
                          source_parent: QModelIndex) -> bool:
        if not self._search:
            return True
        src = self.sourceModel()
        r   = src.risk_at(source_row)
        if r is None:
            return False
        haystack = " ".join([
            str(r.get("title")           or ""),
            str(r.get("owner")           or ""),
            str(r.get("mitre_tactic")    or ""),
            str(r.get("mitre_technique") or ""),
            str(r.get("nist_function")   or ""),
            str(r.get("nist_category")   or ""),
            str(r.get("iso_domain")      or ""),
            str(r.get("iso_control")     or ""),
            str(r.get("cis_control")     or ""),
            str(r.get("category")        or ""),
            str(r.get("description")     or ""),
            str(r.get("status")          or ""),
        ]).lower()
        return self._search in haystack


# ── Treatment columns ─────────────────────────────────────────────────────────

TREATMENT_COLUMNS = [
    ("strategy",    "Strategy",  90),
    ("title",       "Title",     0),     # flexible
    ("risk_title",  "Risk",      190),
    ("owner",       "Owner",     120),
    ("status",      "Status",    105),
    ("target_date", "Target",    95),
    ("progress",    "",          70),    # progress bar via delegate
]
TCOL_IDX = {c[0]: i for i, c in enumerate(TREATMENT_COLUMNS)}


class TreatmentTableModel(QAbstractTableModel):
    """
    Virtualised table model for the Treatments page.

    Rows are treatment dicts joined with their parent risk title,
    as returned by the bulk query in TreatmentsPage.
    """

    def __init__(self, rows: list[dict], parent=None):
        super().__init__(parent)
        self._rows = rows

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(TREATMENT_COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if (orientation == Qt.Orientation.Horizontal and
                role == Qt.ItemDataRole.DisplayRole):
            return TREATMENT_COLUMNS[section][1]
        return None

    def data(self, index: QModelIndex,
             role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        if row >= len(self._rows):
            return None
        t = self._rows[row]
        col_key = TREATMENT_COLUMNS[col][0]

        if role == Qt.ItemDataRole.DisplayRole:
            if col_key == "strategy":   return str(t.get("strategy") or "")
            if col_key == "title":      return str(t.get("title") or "")
            if col_key == "risk_title": return str(t.get("risk_title") or "—")
            if col_key == "owner":      return str(t.get("owner") or "—")
            if col_key == "status":     return str(t.get("status") or "—")
            if col_key == "target_date":return str(t.get("target_date") or "—")
            if col_key == "progress":   return ""
            return ""

        if role == Qt.ItemDataRole.ForegroundRole:
            if col_key == "strategy":
                return QColor(Colors.treat_color(t.get("strategy", "")))
            if col_key == "status":
                return QColor(
                    Colors.treat_status_color(t.get("status", "")))
            if col_key == "target_date":
                from core.database.db import days_until
                d = days_until(t.get("target_date"))
                if d is not None and d < 0 and t.get("status") not in (
                        "Completed", "Verified"):
                    return QColor(Colors.CRITICAL)
                return QColor(Colors.TEXT_MUTED)
            return QColor(Colors.TEXT_PRIMARY)

        if role == Qt.ItemDataRole.BackgroundRole:
            return QColor(Colors.BG_CARD if row % 2 == 0
                          else Colors.BG_CARD2)

        if role == Qt.ItemDataRole.FontRole:
            if col_key in ("strategy", "status"):
                return Fonts.label_sm_bold()
            return Fonts.label_sm()

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignLeft |
                       Qt.AlignmentFlag.AlignVCenter)

        # UserRole: return status STRING only (never a dict — causes Shiboken crash)
        if role == Qt.ItemDataRole.UserRole:
            return str(t.get("status", ""))

        # UserRole+1: progress float 0.0–1.0 for the ProgressDelegate
        if role == Qt.ItemDataRole.UserRole + 1:
            lifecycle = ["Draft", "Approved", "In Progress",
                         "Completed", "Verified"]
            try:
                return lifecycle.index(t.get("status", "")) / 4.0
            except ValueError:
                return 0.0

        return None

    def row_at(self, row: int) -> dict | None:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def refresh(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()


# ── Progress bar delegate for treatment table ─────────────────────────────────

class ProgressDelegate(QStyledItemDelegate):
    """
    Paints a compact progress bar in the last column of the treatment table
    without creating a QProgressBar widget per row.
    """

    def paint(self, painter: QPainter,
              option: QStyleOptionViewItem,
              index: QModelIndex) -> None:
        progress = index.data(Qt.ItemDataRole.UserRole + 1)
        if progress is None:
            super().paint(painter, option, index)
            return

        painter.save()
        rect = option.rect.adjusted(8, 10, -8, -10)
        # Background track
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor(Colors.BG_BORDER)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 4, 4)
        # Progress fill
        fill = rect.adjusted(0, 0,
                              -int(rect.width() * (1 - progress)), 0)
        status = index.data(Qt.ItemDataRole.UserRole) or ""
        color  = QColor(Colors.treat_status_color(status))
        painter.setBrush(QBrush(color))
        painter.drawRoundedRect(fill, 4, 4)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem,
                 index: QModelIndex):
        return super().sizeHint(option, index).__class__(70, 30)
