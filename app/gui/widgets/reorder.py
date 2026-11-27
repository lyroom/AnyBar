"""app/gui/widgets/reorder.py — 物理让位拖拽重排序容器与拖拽抓手"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPointF, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QScrollArea, QWidget

from app.styles import qss_engine, tokens

from . import motion


class ReorderHandle(QWidget):
    """平滑高亮拖拽排序抓手：三条圆头细杠，支持手型光标与拖拽联动。"""

    def __init__(self, card: QWidget | None = None, container=None,
                 dark: bool = False, scale: float = 1.0, parent=None):
        super().__init__(parent or card)
        self._card = card
        self._container = container
        self._dark = bool(dark)
        self._scale = max(1.0, float(scale))
        self._pressed = False
        self._press_pos = None
        self._dragging = False
        self._hover_tween = motion.ValueTween(0.0, tokens.MOTION["micro"], parent=self)
        self._hover_tween.changed.connect(lambda _v: self.update())
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("按住上下拖拽调整顺序")

    def set_card_and_container(self, card: QWidget, container) -> None:
        self._card = card
        self._container = container

    def set_dark_scale(self, dark: bool, scale: float) -> None:
        self._dark = bool(dark)
        self._scale = max(1.0, float(scale))
        self.update()

    def enterEvent(self, event):
        self._hover_tween.animate_to(1.0, animate=self.isVisible())
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_tween.animate_to(0.0, animate=self.isVisible())
        self._pressed = False
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self._press_pos = event.globalPosition().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pressed and (event.buttons() & Qt.MouseButton.LeftButton):
            cur_pos = event.globalPosition().toPoint()
            if not self._dragging:
                if self._press_pos and (cur_pos - self._press_pos).manhattanLength() >= 3:
                    if self._container and self._card:
                        self._dragging = True
                        self.grabMouse()
                        self._container.begin_drag(self._card, event.globalPosition().y())
            else:
                if self._container:
                    self._container.update_drag(event.globalPosition().y())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragging:
                self._dragging = False
                try:
                    self.releaseMouse()
                except Exception:
                    pass
                if self._container:
                    self._container.finish_drag()
            self._pressed = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.update()
        super().mouseReleaseEvent(event)

    def hideEvent(self, event):
        if self._dragging:
            self._dragging = False
            try:
                self.releaseMouse()
            except Exception:
                pass
            if self._container:
                self._container.finish_drag()
        super().hideEvent(event)

    def paintEvent(self, event):
        t = tokens.get_tokens(self._dark)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = float(self.width()), float(self.height())
        cx, cy = w * 0.5, h * 0.5

        if self._pressed or self._dragging:
            line_color = QColor(t.accent)
        else:
            line_color = motion.blend_color(
                QColor(t.border_strong), QColor(t.text_secondary), self._hover_tween.value
            )

        s = self._scale
        pen_w = max(1.5, 1.7 * s)
        p.setPen(QPen(line_color, pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))

        half_w = 6.0 * s
        dy = 3.5 * s
        p.drawLine(QPointF(cx - half_w, cy - dy), QPointF(cx + half_w, cy - dy))
        p.drawLine(QPointF(cx - half_w, cy), QPointF(cx + half_w, cy))
        p.drawLine(QPointF(cx - half_w, cy + dy), QPointF(cx + half_w, cy + dy))
        p.end()


class AnimatedReorderContainer(QWidget):
    """物理让位拖拽重排序容器：升起投影 + 实时 OutCubic 让位 + 顺滑着陆动画。"""

    orderChanged = Signal()

    def __init__(self, row_h: int = 44, spacing: int = 6,
                 dark: bool = False, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self._row_h = int(row_h)
        self._spacing = int(spacing)
        self._dark = bool(dark)
        self._scale = max(1.0, float(scale))
        self._cards: list[QWidget] = []
        self._anims: dict[QWidget, QPropertyAnimation] = {}
        self._is_dragging = False
        self._is_landing = False
        self._dragging_card: QWidget | None = None
        self._orig_idx = 0
        self._current_target_idx = 0
        self._start_global_y = 0.0
        self._start_card_y = 0
        self.setObjectName("reorderContainer")

    def set_dark_scale(self, dark: bool, scale: float, row_h: int, spacing: int) -> None:
        self._dark = bool(dark)
        self._scale = max(1.0, float(scale))
        self._row_h = int(row_h)
        self._spacing = int(spacing)
        self._layout_all(animated=False)

    def add_card(self, card: QWidget) -> None:
        if card not in self._cards:
            self._cards.append(card)
            card.setParent(self)
            card.show()
            self._layout_all(animated=False)

    def remove_card(self, card: QWidget) -> None:
        if card in self._cards:
            self._cards.remove(card)
            if card in self._anims:
                anim = self._anims.pop(card)
                anim.stop()
                anim.deleteLater()
            card.setParent(None)
            card.deleteLater()
            self._layout_all(animated=True)

    def cards(self) -> list[QWidget]:
        return list(self._cards)

    def clear_cards(self) -> None:
        for c in list(self._cards):
            if c in self._anims:
                anim = self._anims.pop(c)
                anim.stop()
                anim.deleteLater()
            c.setParent(None)
            c.deleteLater()
        self._cards = []
        self.setFixedHeight(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        slot_h = self._row_h + self._spacing
        for i, c in enumerate(self._cards):
            if c != self._dragging_card:
                c.setGeometry(0, i * slot_h, w, self._row_h)
            else:
                c.resize(w, self._row_h)

    def _layout_all(self, animated: bool = False) -> None:
        w = max(100, self.width())
        slot_h = self._row_h + self._spacing
        total_h = len(self._cards) * self._row_h + max(0, len(self._cards) - 1) * self._spacing
        self.setFixedHeight(max(0, total_h))
        for i, c in enumerate(self._cards):
            dest_y = i * slot_h
            if animated:
                self._animate_card_to(c, dest_y)
            else:
                if c in self._anims:
                    self._anims[c].stop()
                c.setGeometry(0, dest_y, w, self._row_h)

    def _get_anim(self, card: QWidget) -> QPropertyAnimation:
        if card not in self._anims:
            anim = QPropertyAnimation(card, b"pos", self)
            self._anims[card] = anim
        return self._anims[card]

    def _animate_card_to(self, card: QWidget, dest_y: int) -> None:
        if card.pos().y() == dest_y:
            return
        anim = self._get_anim(card)
        anim.stop()
        anim.setDuration(tokens.MOTION["standard"])
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(card.pos())
        anim.setEndValue(QPoint(0, int(dest_y)))
        anim.start()

    def begin_drag(self, card: QWidget, start_global_y: float) -> None:
        if self._is_dragging or self._is_landing or card not in self._cards:
            return
        self._is_dragging = True
        self._dragging_card = card
        self._orig_idx = self._cards.index(card)
        self._current_target_idx = self._orig_idx
        self._start_global_y = float(start_global_y)
        self._start_card_y = card.pos().y()
        card.raise_()
        qss_engine.set_prop(card, "dragging", "true")

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(tokens.spx(22, self._scale))
        shadow.setOffset(0, tokens.spx(6, self._scale))
        shadow.setColor(QColor(0, 0, 0, 110 if self._dark else 52))
        card.setGraphicsEffect(shadow)

    def update_drag(self, current_global_y: float) -> None:
        if not self._is_dragging or not self._dragging_card:
            return
        delta_y = float(current_global_y) - self._start_global_y
        new_y = self._start_card_y + delta_y
        slot_h = self._row_h + self._spacing
        max_y = max(0, len(self._cards) * slot_h - self._row_h)
        clamped_y = max(0, min(new_y, max_y))
        self._dragging_card.move(0, int(clamped_y))

        parent_scroll = self.parent()
        while parent_scroll and not isinstance(parent_scroll, QScrollArea):
            parent_scroll = parent_scroll.parent()
        if parent_scroll:
            vp = parent_scroll.viewport()
            vp_pos = vp.mapFromGlobal(QPoint(0, int(current_global_y)))
            sb = parent_scroll.verticalScrollBar()
            if vp_pos.y() < 24 and sb.value() > 0:
                sb.setValue(sb.value() - 8)
            elif vp_pos.y() > vp.height() - 24 and sb.value() < sb.maximum():
                sb.setValue(sb.value() + 8)

        center_y = clamped_y + self._row_h * 0.5
        target_idx = max(0, min(int(round((center_y - self._row_h * 0.5) / slot_h)), len(self._cards) - 1))
        if target_idx != self._current_target_idx:
            self._current_target_idx = target_idx
            preview_cards = [c for c in self._cards if c != self._dragging_card]
            preview_cards.insert(target_idx, self._dragging_card)
            for slot, c in enumerate(preview_cards):
                if c == self._dragging_card:
                    continue
                self._animate_card_to(c, slot * slot_h)

    def finish_drag(self) -> None:
        if not self._is_dragging or not self._dragging_card:
            return
        slot_h = self._row_h + self._spacing
        final_y = self._current_target_idx * slot_h
        dragged = self._dragging_card
        orig_order = list(self._cards)

        self._is_landing = True
        anim = self._get_anim(dragged)
        anim.stop()
        anim.setDuration(tokens.MOTION["standard"])
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(dragged.pos())
        anim.setEndValue(QPoint(0, int(final_y)))

        def _on_finished():
            try:
                anim.finished.disconnect(_on_finished)
            except Exception:
                pass
            dragged.setGraphicsEffect(None)
            qss_engine.set_prop(dragged, "dragging", "false")
            preview_cards = [c for c in self._cards if c != dragged]
            preview_cards.insert(self._current_target_idx, dragged)
            self._cards = preview_cards
            self._is_dragging = False
            self._is_landing = False
            self._dragging_card = None
            if self._cards != orig_order:
                self.orderChanged.emit()

        anim.finished.connect(_on_finished)
        anim.start()
