"""Evidence Console design system for the Relic Auditor dashboard.

Every colour, radius, spacing step, and type size used by the desktop
dashboard is defined here. Widgets must never embed raw style strings; they
pull from :data:`TOKENS` or ask :func:`stylesheet` for the compiled Qt style.

The palette mirrors the Relic Auditor product identity: a true-black canvas,
neon yellow for primary action and selection, acid lime for verified state,
a lighter green for active evidence, amber for advisory, and a restrained
off-white for body text. Accents carry meaning, so they stay scarce.

Sizing is font-metric driven rather than pixel-locked. Windows users run this
at 100%-200% display scaling with varying system font sizes, so any control
that holds text derives its minimum height from the actual font metrics via
:func:`control_height` instead of a hard-coded pixel value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


# --------------------------------------------------------------------------
# Colour
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Palette:
    """Named colours. Values are hex strings usable directly in Qt style."""

    # Canvas: true black through progressively lifted panel surfaces.
    canvas: str = "#000000"
    surface: str = "#07090C"
    panel: str = "#0B0E13"
    panel_raised: str = "#11151C"
    panel_hover: str = "#161B24"
    inset: str = "#05070A"

    # Hairline borders. Luminous ones are reserved for focus and selection.
    border: str = "#1C222C"
    border_strong: str = "#2A323F"
    border_luminous: str = "#3D4757"

    # Type.
    text: str = "#ECEFF3"
    text_muted: str = "#9AA6B4"
    # Lifted from #6B7787. Captions used to paint their own black background,
    # which flattered the contrast; once labels became transparent they sit on
    # panel_raised (#11151C) where the old value measured 4.019:1 - under the
    # 4.5:1 AA floor these 7pt captions need.
    text_dim: str = "#7A8798"
    text_inverse: str = "#000000"

    # Accents.
    yellow: str = "#E8FF00"          # primary action, selection, emphasis
    yellow_dim: str = "#B8CC00"
    yellow_wash: str = "#1A1D00"
    lime: str = "#9EFF3D"            # verified / ready / success
    lime_wash: str = "#0D1A05"
    green: str = "#4ADE80"           # active evidence, positive findings
    green_wash: str = "#04140C"
    amber: str = "#FFB020"           # uncertain / partial / advisory
    amber_wash: str = "#1A1102"
    red: str = "#FF4D4D"             # genuine failure or blocked only
    red_wash: str = "#1A0505"
    slate: str = "#5E6B62"           # inactive, secondary info


PALETTE = Palette()


# --------------------------------------------------------------------------
# Spacing, radius, type
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Spacing:
    """A 4px-based spacing scale. Use the names, not the numbers."""

    xxs: int = 2
    xs: int = 4
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 24
    xxl: int = 32


@dataclass(frozen=True)
class Radius:
    sm: int = 4
    md: int = 8
    lg: int = 12
    pill: int = 999


@dataclass(frozen=True)
class Typography:
    """Font stacks and the type scale, in points.

    A condensed technical face is preferred for headings and numerals; the UI
    face stays highly legible for controls and dense tables. Both fall back
    through widely available Windows fonts before hitting the generic family.
    """

    display: str = (
        '"Bahnschrift", "Oswald", "Segoe UI Semibold", "Segoe UI", '
        '"DejaVu Sans", sans-serif'
    )
    ui: str = '"Segoe UI Variable Text", "Segoe UI", "Inter", "DejaVu Sans", sans-serif'
    mono: str = '"Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace'

    # Point sizes. Qt scales these by the OS DPI setting automatically.
    micro: int = 7
    small: int = 8
    body: int = 9
    body_lg: int = 10
    title: int = 12
    heading: int = 15
    display_sm: int = 19
    display_lg: int = 25

    tracking_wide: str = "1.5px"
    tracking_brand: str = "3px"


SPACING = Spacing()
RADIUS = Radius()
TYPE = Typography()


# --------------------------------------------------------------------------
# Status semantics
# --------------------------------------------------------------------------

#: Maps a semantic status to (foreground, wash background, border).
#: Colour never carries meaning alone - every consumer also renders a label.
STATUS_COLORS: Mapping[str, tuple[str, str, str]] = {
    "ready": (PALETTE.lime, PALETTE.lime_wash, PALETTE.lime),
    "success": (PALETTE.lime, PALETTE.lime_wash, PALETTE.lime),
    "active": (PALETTE.green, PALETTE.green_wash, PALETTE.green),
    "running": (PALETTE.yellow, PALETTE.yellow_wash, PALETTE.yellow_dim),
    "primary": (PALETTE.yellow, PALETTE.yellow_wash, PALETTE.yellow_dim),
    "advisory": (PALETTE.amber, PALETTE.amber_wash, PALETTE.amber),
    "warning": (PALETTE.amber, PALETTE.amber_wash, PALETTE.amber),
    "failed": (PALETTE.red, PALETTE.red_wash, PALETTE.red),
    "blocked": (PALETTE.red, PALETTE.red_wash, PALETTE.red),
    "idle": (PALETTE.slate, PALETTE.panel, PALETTE.border),
    "inactive": (PALETTE.slate, PALETTE.panel, PALETTE.border),
    "cancelled": (PALETTE.text_dim, PALETTE.panel, PALETTE.border_strong),
}

#: Every status also has words, so the state survives greyscale and
#: colour-vision differences.
STATUS_LABELS: Mapping[str, str] = {
    "ready": "READY",
    "success": "COMPLETE",
    "active": "ACTIVE",
    "running": "RUNNING",
    "advisory": "ADVISORY",
    "warning": "CHECK",
    "failed": "FAILED",
    "blocked": "BLOCKED",
    "idle": "IDLE",
    "inactive": "INACTIVE",
    "cancelled": "CANCELLED",
}


def status_colors(status: str) -> tuple[str, str, str]:
    return STATUS_COLORS.get(status, STATUS_COLORS["idle"])


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status.upper())


# --------------------------------------------------------------------------
# Font-metric aware sizing
# --------------------------------------------------------------------------

#: Vertical padding added above and below one line of text inside a control.
CONTROL_PADDING_Y = SPACING.sm
#: Absolute floor so controls stay clickable even with a tiny system font.
MIN_TOUCH_TARGET = 28


def control_height(font_metrics: Any, lines: int = 1, padding: int | None = None) -> int:
    """Minimum height for a control holding ``lines`` lines of text.

    Derived from real font metrics so Windows font scaling and per-monitor DPI
    changes grow controls instead of clipping their text. Never replace this
    with a fixed pixel height on anything that renders text.
    """

    pad = CONTROL_PADDING_Y if padding is None else padding
    line = font_metrics.height()
    return max(MIN_TOUCH_TARGET, line * max(1, lines) + pad * 2)


def text_width(font_metrics: Any, text: str, padding: int = 0) -> int:
    """Pixel width needed to render ``text`` without eliding."""

    return font_metrics.horizontalAdvance(text) + padding * 2


@dataclass(frozen=True)
class Breakpoints:
    """Widths at which the dashboard reorganises.

    Below :attr:`stack`, side-by-side panels stack vertically so the console
    stays usable at the minimum supported window size.
    """

    minimum_width: int = 960
    minimum_height: int = 600
    #: Below this logical width a ~390px sidebar plus a usable workspace no
    #: longer fit side by side, so the console stacks them vertically. Set it
    #: too high and stacking kicks in while horizontal would still have been
    #: comfortable, which buries the primary action below the fold.
    stack: int = 980
    wide: int = 1600


BREAKPOINTS = Breakpoints()


#: Everything a widget may need, in one mapping, for tests and introspection.
TOKENS: dict[str, Any] = {
    "palette": PALETTE,
    "spacing": SPACING,
    "radius": RADIUS,
    "type": TYPE,
    "status_colors": STATUS_COLORS,
    "status_labels": STATUS_LABELS,
    "breakpoints": BREAKPOINTS,
}


# --------------------------------------------------------------------------
# Compiled Qt stylesheet
# --------------------------------------------------------------------------


def stylesheet() -> str:
    """Build the application stylesheet from the tokens above.

    Sizes here are padding and radius only. Heights come from font metrics at
    widget construction time, so nothing that holds text is pixel-locked.
    """

    p, s, r, t = PALETTE, SPACING, RADIUS, TYPE
    return f"""
/* ---- base ------------------------------------------------------------ */
QWidget {{
    background: {p.canvas};
    color: {p.text};
    font-family: {t.ui};
    font-size: {t.body}pt;
}}
QMainWindow, QDialog {{ background: {p.canvas}; }}
QToolTip {{
    background: {p.panel_raised};
    color: {p.text};
    border: 1px solid {p.border_luminous};
    padding: {s.sm}px;
}}

/* ---- structure ------------------------------------------------------- */
QFrame#relicPanel {{
    background: {p.panel};
    border: 1px solid {p.border};
    border-radius: {r.lg}px;
}}
QFrame#relicPanel[emphasis="true"] {{ border-color: {p.border_luminous}; }}
QFrame#evidenceCard, QFrame#metricCard {{
    background: {p.panel_raised};
    border: 1px solid {p.border};
    border-radius: {r.md}px;
}}
QFrame#metricCard:hover {{ border-color: {p.border_luminous}; }}
QFrame#headerBar {{
    background: {p.surface};
    border-bottom: 1px solid {p.border};
}}
QFrame#hairline {{ background: {p.border}; border: none; }}

/* ---- type ------------------------------------------------------------ */
/* Labels inherit their parent surface. The base QWidget rule paints every
   widget true black, which on a lifted panel turned each ordinary caption
   into a black band and made the console look assembled from strips. Black
   bands are now reserved for widgets that opt in (badges, inputs, headings
   that set their own background). */
QLabel {{ background: transparent; }}
QCheckBox, QRadioButton {{ background: transparent; }}
QLabel#brandMark {{
    color: {p.yellow};
    font-family: {t.display};
    font-size: {t.display_sm}pt;
    font-weight: 800;
    letter-spacing: {t.tracking_brand};
}}
QLabel#brandSub {{
    color: {p.text_muted};
    font-family: {t.display};
    font-size: {t.small}pt;
    font-weight: 600;
    letter-spacing: {t.tracking_wide};
}}
QLabel#sectionLabel {{
    color: {p.text_dim};
    font-size: {t.micro}pt;
    font-weight: 700;
    letter-spacing: {t.tracking_wide};
}}
QLabel#panelTitle {{
    color: {p.text};
    font-family: {t.display};
    font-size: {t.title}pt;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QLabel#mutedLabel {{ color: {p.text_muted}; }}
QLabel#dimLabel {{ color: {p.text_dim}; font-size: {t.small}pt; }}
QLabel#metricValue {{
    color: {p.yellow};
    font-family: {t.display};
    font-size: {t.display_sm}pt;
    font-weight: 800;
}}
QLabel#metricValue[tone="evidence"] {{ color: {p.green}; }}
QLabel#metricValue[tone="neutral"] {{ color: {p.text}; }}
/* "Not measured yet" is a real state and must read as one: a muted em dash,
   never a tiny floating glyph that looks like a rendering failure and never
   a zero, which would claim a measurement that was not taken. */
QLabel#metricValue[state="unavailable"] {{
    color: {p.text_dim};
    font-weight: 600;
}}
QLabel#metricLabel {{
    color: {p.text_dim};
    font-size: {t.micro}pt;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#monoLabel {{ font-family: {t.mono}; color: {p.text_muted}; }}
QLabel#emptyTitle {{
    color: {p.text_muted};
    font-family: {t.display};
    font-size: {t.body_lg}pt;
    font-weight: 700;
}}
QLabel#answerConclusion {{
    color: {p.text};
    font-family: {t.display};
    font-size: {t.display_lg}pt;
    font-weight: 800;
    letter-spacing: 0.3px;
}}
QLabel#emptyBody {{ color: {p.text_dim}; }}
QLabel#emptyMarker {{
    color: {p.slate};
    font-size: {t.display_sm}pt;
    font-weight: 400;
}}

/* ---- inputs ---------------------------------------------------------- */
QLineEdit, QComboBox, QPlainTextEdit, QSpinBox {{
    background: {p.inset};
    border: 1px solid {p.border_strong};
    border-radius: {r.sm}px;
    padding: {s.sm}px {s.md}px;
    color: {p.text};
    selection-background-color: {p.yellow};
    selection-color: {p.text_inverse};
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QSpinBox:focus {{
    border: 1px solid {p.yellow};
}}
QLineEdit:disabled, QComboBox:disabled, QPlainTextEdit:disabled {{
    /* Disabled must stay readable, not vanish into the canvas. */
    color: {p.text_dim};
    background: {p.panel};
    border-color: {p.border};
}}
QComboBox::drop-down {{ border: none; width: {s.xl}px; }}
QComboBox::down-arrow {{
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {p.text_muted};
}}
QComboBox QAbstractItemView {{
    background: {p.panel_raised};
    border: 1px solid {p.border_luminous};
    selection-background-color: {p.yellow};
    selection-color: {p.text_inverse};
    outline: none;
}}
QCheckBox {{ color: {p.text}; spacing: {s.sm}px; }}
QCheckBox:disabled {{ color: {p.text_dim}; }}
QCheckBox::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {p.border_strong};
    border-radius: {r.sm}px;
    background: {p.inset};
}}
QCheckBox::indicator:checked {{
    background: {p.yellow};
    border-color: {p.yellow};
}}
QCheckBox::indicator:focus {{ border-color: {p.yellow}; }}
QRadioButton {{ color: {p.text}; spacing: {s.sm}px; }}
QRadioButton::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {p.border_strong};
    border-radius: 8px;
    background: {p.inset};
}}
QRadioButton::indicator:checked {{
    background: {p.yellow};
    border-color: {p.yellow};
}}

/* ---- buttons --------------------------------------------------------- */
QPushButton {{
    background: {p.panel_raised};
    border: 1px solid {p.border_strong};
    border-radius: {r.sm}px;
    padding: {s.sm}px {s.lg}px;
    color: {p.text};
    font-weight: 600;
}}
QPushButton:hover {{
    background: {p.panel_hover};
    border-color: {p.border_luminous};
}}
QPushButton:focus {{ border: 1px solid {p.yellow}; }}
QPushButton:disabled {{
    color: {p.text_dim};
    background: {p.panel};
    border-color: {p.border};
}}
QPushButton#primaryButton {{
    background: {p.yellow};
    border: 1px solid {p.yellow};
    color: {p.text_inverse};
    font-weight: 800;
    letter-spacing: 0.5px;
    padding: {s.md}px {s.xl}px;
}}
QPushButton#primaryButton:hover {{ background: {p.lime}; border-color: {p.lime}; }}
QPushButton#primaryButton:disabled {{
    background: {p.panel_raised};
    border-color: {p.border_strong};
    color: {p.text_dim};
}}
QPushButton#secondaryButton {{
    background: transparent;
    border: 1px solid {p.border_strong};
    color: {p.text};
}}
QPushButton#secondaryButton:hover {{
    border-color: {p.yellow};
    color: {p.yellow};
}}
QPushButton#dangerButton {{
    background: transparent;
    border: 1px solid {p.red};
    color: {p.red};
}}
QPushButton#dangerButton:hover {{ background: {p.red_wash}; }}
/* An ID selector outranks QPushButton:disabled, so without this rule a
   correctly-disabled Cancel button still rendered in live red and read as
   clickable. Disabled must look disabled. */
QPushButton#dangerButton:disabled {{
    background: {p.panel};
    border-color: {p.border};
    color: {p.text_dim};
}}
QPushButton[kind="decision"] {{
    color: {p.yellow};
    padding: {s.xs}px {s.md}px;
}}
QPushButton[kind="quiet"] {{ background: transparent; border-color: {p.border}; }}

/* ---- badges ---------------------------------------------------------- */
QLabel#statusBadge {{
    border-radius: {r.sm}px;
    padding: {s.xs}px {s.sm}px;
    font-size: {t.micro}pt;
    font-weight: 800;
    letter-spacing: 1px;
}}

/* ---- tables ---------------------------------------------------------- */
QTableView {{
    background: {p.panel};
    alternate-background-color: {p.surface};
    border: 1px solid {p.border};
    border-radius: {r.md}px;
    gridline-color: {p.border};
    selection-background-color: {p.yellow_wash};
    selection-color: {p.yellow};
    outline: none;
}}
QTableView::item {{ padding: {s.sm}px {s.md}px; }}
QTableView::item:selected {{
    background: {p.yellow_wash};
    color: {p.yellow};
    border-left: 2px solid {p.yellow};
}}
QTableView::item:focus {{ outline: none; }}
QHeaderView {{ background: {p.surface}; }}
QHeaderView::section {{
    background: {p.surface};
    color: {p.text_dim};
    border: none;
    border-bottom: 1px solid {p.border_strong};
    padding: {s.sm}px;
    font-size: {t.micro}pt;
    font-weight: 700;
    letter-spacing: 1px;
}}
QHeaderView::section:hover {{ color: {p.yellow}; }}
QTableCornerButton::section {{ background: {p.surface}; border: none; }}

/* ---- ranked lists --------------------------------------------------- */
QListWidget {{
    background: {p.inset};
    border: 1px solid {p.border_strong};
    border-radius: {r.md}px;
    color: {p.text_muted};
    outline: none;
    padding: {s.xs}px;
}}
QListWidget::item {{
    background: {p.panel};
    border: 1px solid {p.border};
    border-radius: {r.sm}px;
    padding: {s.sm}px {s.md}px;
    margin: {s.xxs}px 0;
}}
QListWidget::item:hover {{
    background: {p.panel_hover};
    border-color: {p.border_luminous};
}}
QListWidget::item:selected {{
    background: {p.yellow_wash};
    color: {p.yellow};
    border-color: {p.yellow_dim};
}}
QListWidget:focus {{ border-color: {p.yellow}; }}

/* ---- tabs ------------------------------------------------------------ */
QTabWidget::pane {{ border: none; background: {p.canvas}; }}
QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: transparent;
    color: {p.text_dim};
    padding: {s.sm}px {s.lg}px;
    margin-right: {s.xs}px;
    border-bottom: 2px solid transparent;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    color: {p.yellow};
    border-bottom: 2px solid {p.yellow};
}}
QTabBar::tab:hover:!selected {{ color: {p.text}; }}
QTabBar::tab:focus {{ border-bottom-color: {p.lime}; }}

/* ---- progress -------------------------------------------------------- */
QProgressBar {{
    border: none;
    background: {p.panel_raised};
    border-radius: {r.sm}px;
    text-align: center;
    color: {p.text_muted};
    font-size: {t.micro}pt;
}}
QProgressBar::chunk {{ background: {p.yellow}; border-radius: {r.sm}px; }}
QProgressBar[state="success"]::chunk {{ background: {p.lime}; }}
QProgressBar[state="failed"]::chunk {{ background: {p.red}; }}

/* ---- scrolling ------------------------------------------------------- */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 0;
}}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 0;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {p.border_strong};
    border-radius: 5px;
    min-height: 32px;
    min-width: 32px;
}}
QScrollBar::handle:hover {{ background: {p.border_luminous}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; border: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- misc ------------------------------------------------------------ */
QSplitter::handle {{ background: {p.border}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
/* Vertical padding here plus the font-metric minimum height applied in
   qt_app keeps descenders (p, g, y) off the window edge at every scale. */
QStatusBar {{
    background: {p.surface};
    color: {p.text_dim};
    border-top: 1px solid {p.border};
    padding: {s.xs}px {s.lg}px;
}}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ background: transparent; color: {p.text_dim}; }}
QMenu {{
    background: {p.panel_raised};
    border: 1px solid {p.border_luminous};
    color: {p.text};
}}
QMenu::item:selected {{ background: {p.yellow}; color: {p.text_inverse}; }}
QGraphicsView {{
    background: {p.surface};
    border: 1px solid {p.border};
    border-radius: {r.md}px;
}}
"""
