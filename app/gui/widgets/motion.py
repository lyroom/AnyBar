"""app/motion.py — AnyBar 轻量级物理动效引擎

设计原则：
1. 零泄漏：复用单个 QVariantAnimation/QPropertyAnimation 实例或在替换时立即 stop+deleteLater；
2. 零空转：控件不可见时立即跳过动画直达终态，环境微动效在 hideEvent 自动停表；
3. 可中断：任何进行中的状态/高度/切换动画都能无缝反向打断；
4. 统一时序：全部 duration 取自 tokens.MOTION。
"""

from __future__ import annotations

from PySide6.QtCore import (QEasingCurve, QObject, QPoint, QPropertyAnimation,
                            Qt, QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout,
                               QLabel, QSizePolicy, QStackedWidget,
                               QVBoxLayout, QWidget)

from app.styles import icons, qss_engine, tokens


def blend_color(c1: QColor | str, c2: QColor | str, t: float) -> QColor:
    """在两个颜色之间按 t ∈ [0, 1] 做 RGBA 线性插值。"""
    t = max(0.0, min(1.0, float(t)))
    a = QColor(c1)
    b = QColor(c2)
    return QColor(
        int(round(a.red() + (b.red() - a.red()) * t)),
        int(round(a.green() + (b.green() - a.green()) * t)),
        int(round(a.blue() + (b.blue() - a.blue()) * t)),
        int(round(a.alpha() + (b.alpha() - a.alpha()) * t)),
    )


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, float(t)))
    inv = 1.0 - t
    return 1.0 - inv * inv * inv


class ValueTween(QObject):
    """可复用、可中断的浮点标量补间器（单实例，零 QObject 累积）。"""

    changed = Signal(float)

    def __init__(self, initial: float = 0.0, duration: int = tokens.MOTION["standard"],
                 easing: QEasingCurve.Type = QEasingCurve.Type.OutCubic,
                 parent: QObject | None = None):
        super().__init__(parent)
        self._value = float(initial)
        self._target = float(initial)
        self._duration = int(duration)
        self._easing = easing
        self._anim = QVariantAnimation(self)
        self._anim.valueChanged.connect(self._on_step)

    @property
    def value(self) -> float:
        return self._value

    @property
    def target(self) -> float:
        return self._target

    def is_running(self) -> bool:
        return self._anim.state() == QVariantAnimation.State.Running

    def _on_step(self, val) -> None:
        self._value = float(val)
        self.changed.emit(self._value)

    def set_immediate(self, val: float) -> None:
        self._anim.stop()
        v = float(val)
        self._value = v
        self._target = v
        self.changed.emit(v)

    def animate_to(self, target: float, duration: int | None = None,
                   easing: QEasingCurve.Type | None = None,
                   animate: bool = True) -> None:
        tgt = float(target)
        self._target = tgt
        if not animate or abs(tgt - self._value) < 1e-4:
            self.set_immediate(tgt)
            return
        self._anim.stop()
        self._anim.setDuration(self._duration if duration is None else int(duration))
        self._anim.setEasingCurve(self._easing if easing is None else easing)
        self._anim.setStartValue(self._value)
        self._anim.setEndValue(tgt)
        self._anim.start()

    def stop(self) -> None:
        self._anim.stop()


class CollapsibleSection(QWidget):
    """平滑高度展开/折叠容器：替代瞬间 .show()/.hide() 硬弹。"""

    heightChanged = Signal()
    toggled = Signal(bool)

    def __init__(self, content: QWidget | None = None, expanded: bool = False,
                 duration: int = tokens.MOTION["standard"],
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._expanded = bool(expanded)
        self._duration = int(duration)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)
        self._content: QWidget | None = None

        self._anim = QPropertyAnimation(self, b"maximumHeight", self)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda _v: self.heightChanged.emit())
        self._anim.finished.connect(self._on_anim_finished)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if content is not None:
            self.set_content(content)
        self.set_expanded(self._expanded, animated=False)

    def set_content(self, widget: QWidget) -> None:
        if self._content is not None:
            self._lay.removeWidget(self._content)
            self._content.setParent(None)
        self._content = widget
        self._lay.addWidget(widget)
        if not self._expanded:
            self.setMaximumHeight(0)
            self.hide()

    def is_expanded(self) -> bool:
        return self._expanded

    def _target_content_height(self) -> int:
        if self._content is None:
            return 0
        self._content.adjustSize()
        lay = self._content.layout()
        if lay is not None:
            lay.invalidate()
            lay.activate()
        w = max(120, self.width() or (self.parentWidget().width() if self.parentWidget() else 360))
        hfw = self._content.heightForWidth(w) if self._content.hasHeightForWidth() else 0
        hint = self._content.sizeHint().height()
        return max(1, hint, hfw)

    def set_expanded(self, expanded: bool, animated: bool = True) -> None:
        want = bool(expanded)
        was_expanded = self._expanded
        was_running = self._anim.state() == QPropertyAnimation.State.Running
        self._expanded = want
        self._anim.stop()

        # 状态与可见性均未变化且未处于过渡动画中：静默跳过，避免无意义触发 heightChanged 引起整窗抖动/闪烁
        if (want == was_expanded and not was_running
                and ((want and self.isVisible() and self.maximumHeight() >= 1000000)
                     or (not want and not self.isVisible() and self.maximumHeight() == 0))):
            return

        if not animated or (not self.isVisible() and not want):
            if want:
                self.setMaximumHeight(16777215)
                self.show()
            else:
                self.setMaximumHeight(0)
                self.hide()
            self.heightChanged.emit()
            return

        if want:
            start_h = 0 if not self.isVisible() else self.height()
            self.setMaximumHeight(start_h)
            self.show()
            end_h = self._target_content_height()
            if abs(end_h - start_h) < 2:
                self.setMaximumHeight(16777215)
                self.heightChanged.emit()
                return
            self._anim.setDuration(self._duration)
            self._anim.setStartValue(start_h)
            self._anim.setEndValue(end_h)
            self._anim.start()
        else:
            start_h = self.height()
            if start_h <= 1:
                self.setMaximumHeight(0)
                self.hide()
                self.heightChanged.emit()
                return
            self._anim.setDuration(max(110, int(self._duration * 0.8)))
            self._anim.setStartValue(start_h)
            self._anim.setEndValue(0)
            self._anim.start()

    def _on_anim_finished(self) -> None:
        if self._expanded:
            self.setMaximumHeight(16777215)
        else:
            self.setMaximumHeight(0)
            self.hide()
        self.heightChanged.emit()
        self.toggled.emit(self._expanded)


class AnimatedStackedWidget(QStackedWidget):
    """支持柔和淡入过渡的页面栈，动画结束后自动卸载 GraphicsEffect 避免渲染副作用。"""

    def __init__(self, duration: int = tokens.MOTION["fast"],
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._duration = int(duration)
        self._fade_anim: QPropertyAnimation | None = None
        self._fade_target: QWidget | None = None

    def _cleanup_fade(self) -> None:
        if self._fade_anim is not None:
            self._fade_anim.blockSignals(True)
            self._fade_anim.stop()
            self._fade_anim.deleteLater()
            self._fade_anim = None
        if self._fade_target is not None:
            try:
                self._fade_target.setGraphicsEffect(None)
            except RuntimeError:
                pass
            self._fade_target = None

    def setCurrentIndex(self, index: int) -> None:
        if index == self.currentIndex() or index < 0 or index >= self.count():
            return
        self._cleanup_fade()
        super().setCurrentIndex(index)
        if not self.isVisible():
            return
        w = self.widget(index)
        if w is None:
            return
        eff = QGraphicsOpacityEffect(w)
        eff.setOpacity(0.0)
        w.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(self._duration)
        anim.setStartValue(0.15)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_target = w
        self._fade_anim = anim
        anim.finished.connect(self._cleanup_fade)
        anim.start()

    def setCurrentWidget(self, widget: QWidget) -> None:
        idx = self.indexOf(widget)
        if idx >= 0:
            self.setCurrentIndex(idx)


class ToastBanner(QFrame):
    """设置窗内部轻量浮动提示条：滑入 + 淡入 + 自动淡出，不挤压页面布局。"""

    def __init__(self, parent: QWidget, dark: bool = False, scale: float = 1.0):
        super().__init__(parent)
        self._dark = bool(dark)
        self._scale = max(1.0, float(scale))
        self._kind = "info"
        self.setObjectName("toastBanner")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._eff = QGraphicsOpacityEffect(self)
        self._eff.setOpacity(0.0)
        self.setGraphicsEffect(self._eff)

        self._dismissing = False
        self._fade_anim = QPropertyAnimation(self._eff, b"opacity", self)
        self._fade_anim.finished.connect(self._on_fade_finished)
        self._pos_anim = QPropertyAnimation(self, b"pos", self)
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._dismiss)

        lay = QHBoxLayout(self)
        px_x = tokens.spx(14, self._scale)
        px_y = tokens.spx(8, self._scale)
        lay.setContentsMargins(px_x, px_y, px_x, px_y)
        lay.setSpacing(tokens.spx(8, self._scale))

        self._icon = icons.IconWidget("check", tokens.get_tokens(dark).ok,
                                      size=tokens.spx(15, self._scale))
        lay.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignVCenter)

        self._lbl = QLabel("")
        f = QFont()
        f.setFamilies(list(tokens.FONT_TEXT))
        f.setPixelSize(tokens.spx(12, self._scale))
        f.setWeight(QFont.Weight.DemiBold)
        self._lbl.setFont(f)
        lay.addWidget(self._lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        self._apply_style("info")
        self.hide()

    def set_dark_scale(self, dark: bool, scale: float) -> None:
        self._dark = bool(dark)
        self._scale = max(1.0, float(scale))
        self._apply_style(self._kind)

    def _apply_style(self, kind: str) -> None:
        self._kind = kind
        t = tokens.get_tokens(self._dark)
        palette_map = {
            "ok": (t.ok, "check"),
            "warn": (t.warn, "info"),
            "danger": (t.danger, "quit"),
            "info": (t.accent, "info"),
        }
        fg, ic_name = palette_map.get(kind, (t.accent, "info"))
        self._icon.set_icon(ic_name)
        self._icon.set_color(fg)
        qss_engine.set_prop(self, "kind", kind)
        # 若父容器未挂载 common.qss（例如独立组件测试），则按需加载编译后的 common.qss
        parent_w = self.parentWidget()
        if parent_w is None or "toastBanner" not in (parent_w.styleSheet() or ""):
            self.setStyleSheet(qss_engine.compile_qss("common", dark=self._dark, scale=self._scale))

    def show_message(self, text: str, kind: str = "ok",
                     duration_ms: int = tokens.MOTION["toast_hold"]) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self._hold_timer.stop()
        self._fade_anim.stop()
        self._pos_anim.stop()

        self._apply_style(kind)
        self._lbl.setText(str(text))
        self.adjustSize()

        pw, ph = parent.width(), parent.height()
        tw, th = min(self.sizeHint().width(), max(160, pw - tokens.spx(48, self._scale))), self.sizeHint().height()
        self.resize(tw, th)
        tx = max(tokens.spx(16, self._scale), (pw - tw) // 2)
        ty = max(tokens.spx(16, self._scale), ph - th - tokens.spx(64, self._scale))
        start_pos = QPoint(tx, ty + tokens.spx(12, self._scale))
        end_pos = QPoint(tx, ty)

        self.move(start_pos)
        self.raise_()
        self.show()

        self._pos_anim.setDuration(tokens.MOTION["standard"])
        self._pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._pos_anim.setStartValue(start_pos)
        self._pos_anim.setEndValue(end_pos)
        self._pos_anim.start()

        self._dismissing = False
        self._fade_anim.setDuration(tokens.MOTION["standard"])
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.setStartValue(self._eff.opacity())
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()
        self._hold_timer.start(int(duration_ms))

    def _dismiss(self) -> None:
        self._dismissing = True
        self._fade_anim.stop()
        self._fade_anim.setDuration(tokens.MOTION["fast"])
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade_anim.setStartValue(self._eff.opacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.start()

    def _on_fade_finished(self) -> None:
        if self._dismissing:
            self._dismissing = False
            self.hide()
