"""app/weather_glyph.py — iOS 扁平拟真矢量天气图标（QPainter 自绘，柔光外晕 + 立体云朵 + 细腻动效）

不依赖 emoji 字体：任意缩放都锐利，在深浅卡片与大气渐变底板上均有通透立体质感。
kind 取值：sun / moon / partly / partly_night / cloud / rain / shower / thunder / snow / fog
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QLinearGradient, QPainter, QPainterPath,
                           QPen, QRadialGradient)

# emoji（数据源给的 icon）→ 图标种类，供无 kind 字段的旧数据兜底
_EMOJI_KIND = {
    "☀️": "sun", "☀": "sun", "🌤️": "partly", "⛅": "partly", "☁️": "cloud", "☁": "cloud",
    "🌧️": "rain", "🌦️": "shower", "⛈️": "thunder", "❄️": "snow", "🌨️": "snow",
    "🌫️": "fog",
}


def kind_from_emoji(icon: str) -> str:
    return _EMOJI_KIND.get(icon or "", "partly")


def _cloud_path(x: float, y: float, w: float, h: float) -> QPainterPath:
    """由两个圆丘 + 圆角底座合成的饱满云朵轮廓（x,y,w,h 为云的外包矩形）。"""
    base_h = h * 0.54
    base = QPainterPath()
    base.addRoundedRect(QRectF(x, y + h - base_h, w, base_h), base_h / 2.0, base_h / 2.0)
    big_d = h * 0.80
    small_d = h * 0.60
    big = QPainterPath()
    big.addEllipse(QRectF(x + w * 0.45 - big_d / 2.0, y, big_d, big_d))
    small = QPainterPath()
    small.addEllipse(QRectF(x + w * 0.19, y + h * 0.25, small_d, small_d))
    return base.united(big).united(small).simplified()


def _paint_sparkle(p: QPainter, cx: float, cy: float, r: float, alpha: int,
                   color: QColor | None = None) -> None:
    """绘制一颗精致的四角星芒（用于晴夜月亮周围的微烁星光）。"""
    if r <= 0.4 or alpha <= 8:
        return
    c = QColor(color) if color is not None else QColor(255, 250, 228)
    c.setAlpha(max(0, min(255, int(alpha))))
    path = QPainterPath()
    k = r * 0.26
    path.moveTo(cx, cy - r)
    path.quadTo(cx + k, cy - k, cx + r, cy)
    path.quadTo(cx + k, cy + k, cx, cy + r)
    path.quadTo(cx - k, cy + k, cx - r, cy)
    path.quadTo(cx - k, cy - k, cx, cy - r)
    path.closeSubpath()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawPath(path)


def _paint_sun(p: QPainter, cx: float, cy: float, r: float, rays: bool = True,
               phase: float = 0.0) -> None:
    tau = phase * 2.0 * math.pi if phase else 0.0
    pulse = 0.5 + 0.5 * math.sin(tau) if phase else 0.5
    r_core = r * (1.0 + 0.055 * math.sin(tau)) if phase else r

    # 1. 暖金柔光外晕（确保半径严格收敛在画布内接圆内，绝不产生方框裁边）
    halo_r = r_core * (1.96 + 0.14 * pulse)
    halo = QRadialGradient(cx, cy, halo_r)
    halo.setColorAt(0.0, QColor(255, 206, 68, int(115 + 40 * pulse)))
    halo.setColorAt(0.52, QColor(255, 172, 28, int(40 + 20 * pulse)))
    halo.setColorAt(1.0, QColor(255, 160, 0, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(halo)
    p.drawEllipse(QPointF(cx, cy), halo_r, halo_r)

    # 2. 匀速旋转且轻微呼吸的圆头太阳光芒
    if rays:
        pen = QPen(QColor("#FFB81C"), max(1.3, r * 0.23))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        rot = tau * 0.5 if phase else 0.0
        for i in range(8):
            a = math.radians(i * 45) + rot
            ext = 1.84 + (0.10 * math.sin(tau + i * 0.8) if phase else 0.0)
            p.drawLine(
                QPointF(cx + math.cos(a) * r_core * 1.40, cy + math.sin(a) * r_core * 1.40),
                QPointF(cx + math.cos(a) * r_core * ext, cy + math.sin(a) * r_core * ext),
            )

    # 3. 拟真球面径向渐变太阳本体（偏左上镜面光源）
    g = QRadialGradient(cx - r_core * 0.30, cy - r_core * 0.32, r_core * 1.45)
    g.setColorAt(0.0, QColor("#FFF7C2"))
    g.setColorAt(0.42, QColor("#FFD039"))
    g.setColorAt(1.0, QColor("#FF8800"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawEllipse(QPointF(cx, cy), r_core, r_core)

    # 4. 顶部微弱玻璃高光月弧
    hl_r = r_core * 0.62
    hl = QRadialGradient(cx - r_core * 0.25, cy - r_core * 0.32, hl_r)
    hl.setColorAt(0.0, QColor(255, 255, 255, 130))
    hl.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(hl)
    p.drawEllipse(QPointF(cx - r_core * 0.18, cy - r_core * 0.22), hl_r, hl_r * 0.78)


def _paint_moon(p: QPainter, cx: float, cy: float, r: float,
                phase: float = 0.0, dark: bool = True) -> None:
    tau = phase * 2.0 * math.pi if phase else 0.0
    pulse = 0.5 + 0.5 * math.sin(tau) if phase else 0.5
    r_core = r * (1.0 + 0.045 * math.sin(tau)) if phase else r

    # 1. 柔和月晕（深色底用银蓝光晕，浅色底用暮色靛蓝光晕确保清晰轮廓）
    halo_r = r_core * (1.50 + 0.12 * pulse)
    halo = QRadialGradient(cx, cy, halo_r)
    if dark:
        halo.setColorAt(0.0, QColor(199, 210, 254, int(112 + 48 * pulse)))
        halo.setColorAt(0.52, QColor(129, 140, 248, int(36 + 20 * pulse)))
        halo.setColorAt(1.0, QColor(99, 102, 241, 0))
    else:
        halo.setColorAt(0.0, QColor(99, 102, 241, int(72 + 32 * pulse)))
        halo.setColorAt(0.55, QColor(79, 70, 229, int(24 + 14 * pulse)))
        halo.setColorAt(1.0, QColor(79, 70, 229, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(halo)
    p.drawEllipse(QPointF(cx, cy), halo_r, halo_r)

    # 2. 月牙本体（轻拟物球面渐变 + 缓慢轻盈摇曳）
    p.save()
    if phase:
        p.translate(cx, cy)
        p.rotate(4.2 * math.sin(tau))
        p.translate(-cx, -cy)

    moon = QPainterPath()
    moon.addEllipse(QPointF(cx, cy), r_core, r_core)
    cut = QPainterPath()
    cut.addEllipse(QPointF(cx + r_core * 0.52, cy - r_core * 0.34), r_core * 0.85, r_core * 0.85)
    shape = moon.subtracted(cut)

    g = QRadialGradient(cx - r_core * 0.35, cy - r_core * 0.25, r_core * 1.55)
    if dark:
        g.setColorAt(0.0, QColor("#FFFFFF"))
        g.setColorAt(0.45, QColor("#E0E7FF"))
        g.setColorAt(1.0, QColor("#818CF8"))
        rim_c = QColor(255, 255, 255, 95)
    else:
        g.setColorAt(0.0, QColor("#C7D2FE"))
        g.setColorAt(0.45, QColor("#6366F1"))
        g.setColorAt(1.0, QColor("#3730A3"))
        rim_c = QColor(67, 56, 202, 110)
    p.setPen(QPen(rim_c, max(0.6, r_core * 0.04)))
    p.setBrush(g)
    p.drawPath(shape)
    p.restore()

    # 3. 错峰闪烁的微星点（浅色底用澄澈靛金星芒，深色底用暖白星芒）
    stars = (
        (cx + r_core * 0.72, cy - r_core * 0.62, r_core * 0.26, 0.0),
        (cx + r_core * 1.02, cy - r_core * 0.14, r_core * 0.18, 2.1),
        (cx + r_core * 0.44, cy - r_core * 0.96, r_core * 0.15, 4.2),
    )
    star_col = QColor(255, 250, 228) if dark else QColor(79, 70, 229)
    for sx, sy, sr, shift in stars:
        twinkle = (0.38 + 0.62 * (0.5 + 0.5 * math.sin(tau * 1.5 + shift))) if phase else 0.72
        _paint_sparkle(p, sx, sy, sr * (0.72 + 0.38 * twinkle), int((235 if dark else 205) * twinkle), star_col)


def _paint_cloud(p: QPainter, rect: QRectF, dark: bool, tone: str = "light",
                 dx: float = 0.0, dy: float = 0.0, flash: float = 0.0) -> None:
    if dx != 0.0 or dy != 0.0:
        rect = QRectF(rect.x() + dx, rect.y() + dy, rect.width(), rect.height())
    path = _cloud_path(rect.x(), rect.y(), rect.width(), rect.height())

    # 1. 云底轻拟物软阴影（给出前后景深）
    p.save()
    p.translate(0.0, max(1.0, rect.height() * 0.08))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(15, 23, 42, 42 if dark else 28))
    p.drawPath(path)
    p.restore()

    # 2. 立体体积渐变云身
    g = QLinearGradient(rect.x(), rect.y(), rect.x(), rect.bottom())
    if tone == "storm":
        g.setColorAt(0.0, QColor("#A6B3C4"))
        g.setColorAt(0.55, QColor("#7B889A"))
        g.setColorAt(1.0, QColor("#535E6E"))
    elif dark:
        g.setColorAt(0.0, QColor("#FFFFFF"))
        g.setColorAt(0.58, QColor("#E2E8F0"))
        g.setColorAt(1.0, QColor("#A8B6C8"))
    else:
        g.setColorAt(0.0, QColor("#FFFFFF"))
        g.setColorAt(0.60, QColor("#EBF0F7"))
        g.setColorAt(1.0, QColor("#B7C3D4"))
    p.setBrush(g)
    p.setPen(QPen(QColor(15, 23, 42, 34), 0.75) if not dark and tone != "storm" else Qt.PenStyle.NoPen)
    p.drawPath(path)

    # 3. 顶部柔亮云丘高光（3D 棉花糖蓬松感）
    p.save()
    p.setClipPath(path)
    puff = QRadialGradient(
        rect.x() + rect.width() * 0.44,
        rect.y() + rect.height() * 0.22,
        rect.width() * 0.48,
    )
    puff.setColorAt(0.0, QColor(255, 255, 255, 175 if tone != "storm" else 85))
    puff.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(puff)
    p.drawRect(rect)

    # 闪电瞬间照亮云底的暖黄反射
    if flash > 0.05:
        glow = QRadialGradient(
            rect.x() + rect.width() * 0.52,
            rect.bottom(),
            rect.width() * 0.55,
        )
        glow.setColorAt(0.0, QColor(255, 238, 130, int(170 * flash)))
        glow.setColorAt(1.0, QColor(255, 214, 10, 0))
        p.setBrush(glow)
        p.drawRect(rect)
    p.restore()


def paint_weather_glyph(painter: QPainter, rect: QRectF, kind: str,
                        dark: bool = True, is_day: bool = True,
                        phase: float = 0.0) -> None:
    """在 rect（取其内接正方形居中）内绘制 iOS 扁平拟真天气图标。

    phase: 0.0~1.0 连续时间相位，为 0 时呈现静态，非 0 时呈现明显而柔和的物理微动效。
    """
    s = min(rect.width(), rect.height())
    x0 = rect.x() + (rect.width() - s) / 2.0
    y0 = rect.y() + (rect.height() - s) / 2.0

    if kind == "sun" and not is_day:
        kind = "moon"
    elif kind == "partly" and not is_day:
        kind = "partly_night"

    tau = phase * 2.0 * math.pi if phase else 0.0

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    if kind == "sun":
        _paint_sun(painter, x0 + s * 0.5, y0 + s * 0.5, s * 0.225, phase=phase)
    elif kind == "moon":
        _paint_moon(painter, x0 + s * 0.48, y0 + s * 0.52, s * 0.29, phase=phase, dark=dark)
    elif kind in ("partly", "partly_night"):
        if kind == "partly":
            _paint_sun(painter, x0 + s * 0.35, y0 + s * 0.35, s * 0.185, phase=phase * 0.5)
        else:
            _paint_moon(painter, x0 + s * 0.34, y0 + s * 0.35, s * 0.24, phase=phase, dark=dark)
        cloud_dx = math.sin(tau) * (s * 0.04) if phase else 0.0
        cloud_dy = math.cos(tau) * (s * 0.024) if phase else 0.0
        _paint_cloud(painter, QRectF(x0 + s * 0.12, y0 + s * 0.38, s * 0.80, s * 0.48),
                     dark, dx=cloud_dx, dy=cloud_dy)
    elif kind == "cloud":
        # 后景小云反相微飘，增加景深
        back_dx = -math.sin(tau) * (s * 0.03) if phase else 0.0
        _paint_cloud(painter, QRectF(x0 + s * 0.28, y0 + s * 0.14, s * 0.62, s * 0.38),
                     dark, tone="storm" if dark else "light", dx=back_dx)
        cloud_dx = math.sin(tau) * (s * 0.045) if phase else 0.0
        cloud_dy = math.sin(tau * 1.0 + 0.8) * (s * 0.028) if phase else 0.0
        _paint_cloud(painter, QRectF(x0 + s * 0.04, y0 + s * 0.26, s * 0.88, s * 0.54),
                     dark, dx=cloud_dx, dy=cloud_dy)
    else:
        tone = "storm" if kind in ("rain", "thunder") else "light"
        is_flash = bool(kind == "thunder" and phase and (0.12 <= phase < 0.18 or 0.22 <= phase < 0.25))
        cloud_dx = math.sin(tau) * (s * 0.025) if phase else 0.0
        cloud_dy = math.cos(tau) * (s * 0.018) if phase else 0.0
        _paint_cloud(painter, QRectF(x0 + s * 0.06, y0 + s * 0.09, s * 0.88, s * 0.51),
                     dark, tone, dx=cloud_dx, dy=cloud_dy, flash=1.0 if is_flash else 0.0)
        by = y0 + s * 0.66
        if kind in ("rain", "shower"):
            base_pen = QColor("#7DD3FC" if dark else "#0EA5E9")
            pen_w = max(1.5, s * 0.088)
            if not phase:
                pen = QPen(base_pen, pen_w)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                for i in range(3):
                    dx = x0 + s * (0.30 + i * 0.20)
                    painter.drawLine(QPointF(dx + s * 0.05, by), QPointF(dx - s * 0.03, by + s * 0.22))
            else:
                pen = QPen(base_pen, pen_w)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                travel = s * 0.28
                drop_len = s * 0.16
                for i in range(3):
                    p_i = (phase * 1.8 + i * 0.34) % 1.0
                    alpha = int(255 * math.sin(p_i * math.pi))
                    c = QColor(base_pen)
                    c.setAlpha(max(20, min(255, alpha)))
                    pen.setColor(c)
                    painter.setPen(pen)
                    dx = x0 + s * (0.29 + i * 0.21)
                    cur_y = by - s * 0.05 + p_i * travel
                    x_shift = s * 0.05 - (p_i * 0.09 * s)
                    painter.drawLine(
                        QPointF(dx + x_shift, cur_y),
                        QPointF(dx + x_shift - s * 0.035, cur_y + drop_len),
                    )
        elif kind == "thunder":
            bolt = QPainterPath()
            bx, bw = x0 + s * 0.45, s * 0.21
            bolt.moveTo(bx + bw * 0.62, by - s * 0.05)
            bolt.lineTo(bx - bw * 0.05, by + s * 0.13)
            bolt.lineTo(bx + bw * 0.38, by + s * 0.13)
            bolt.lineTo(bx + bw * 0.10, by + s * 0.32)
            bolt.lineTo(bx + bw * 0.96, by + s * 0.07)
            bolt.lineTo(bx + bw * 0.50, by + s * 0.07)
            bolt.closeSubpath()
            painter.setPen(Qt.PenStyle.NoPen)
            bolt_color = QColor("#FFFBEB") if is_flash else QColor("#FFD60A")
            if is_flash:
                fglow = QRadialGradient(bx + bw * 0.4, by + s * 0.12, s * 0.28)
                fglow.setColorAt(0.0, QColor(255, 245, 180, 180))
                fglow.setColorAt(1.0, QColor(255, 214, 10, 0))
                painter.setBrush(fglow)
                painter.drawEllipse(QPointF(bx + bw * 0.4, by + s * 0.12), s * 0.28, s * 0.28)
            painter.setBrush(bolt_color)
            painter.drawPath(bolt)

            base_pen = QColor("#7DD3FC" if dark else "#0EA5E9")
            pen = QPen(base_pen, max(1.2, s * 0.07))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            travel = s * 0.25
            drop_len = s * 0.14
            for i in (0, 2):
                p_i = (phase * 1.6 + i * 0.4) % 1.0 if phase else 0.5
                alpha = int(220 * math.sin(p_i * math.pi)) if phase else 185
                c = QColor(base_pen)
                c.setAlpha(max(20, min(255, alpha)))
                pen.setColor(c)
                painter.setPen(pen)
                dx = x0 + s * (0.25 + i * 0.25)
                cur_y = by - s * 0.02 + p_i * travel
                painter.drawLine(QPointF(dx + s * 0.04, cur_y), QPointF(dx + s * 0.01, cur_y + drop_len))
        elif kind == "snow":
            base_color = QColor("#F0F9FF" if dark else "#38BDF8")
            painter.setPen(Qt.PenStyle.NoPen)
            if not phase:
                painter.setBrush(base_color)
                for i in range(3):
                    painter.drawEllipse(QPointF(x0 + s * (0.30 + i * 0.20), by + s * (0.08 if i % 2 else 0.17)),
                                        s * 0.055, s * 0.055)
            else:
                travel = s * 0.30
                for i in range(3):
                    p_i = (phase * 0.9 + i * 0.33) % 1.0
                    alpha = int(245 * math.sin(p_i * math.pi))
                    c = QColor(base_color)
                    c.setAlpha(max(25, min(255, alpha)))
                    sway = math.sin(p_i * 2.0 * math.pi + i * 2.0) * (s * 0.045)
                    snow_x = x0 + s * (0.28 + i * 0.22) + sway
                    snow_y = by - s * 0.03 + p_i * travel
                    snow_r = s * 0.052 * (0.85 + 0.22 * math.cos(p_i * math.pi))
                    _paint_sparkle(painter, snow_x, snow_y, snow_r * 1.45, alpha, c)
        elif kind == "fog":
            pen = QPen(QColor(203, 213, 225, 235) if dark else QColor(148, 163, 184, 235), max(1.4, s * 0.075))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            for i, (a, b) in enumerate(((0.20, 0.80), (0.28, 0.72), (0.22, 0.64))):
                shift = math.sin(tau + i * 1.4) * (s * 0.055) if phase else 0.0
                yy = by + s * 0.05 + i * s * 0.11
                painter.drawLine(QPointF(x0 + s * a + shift, yy), QPointF(x0 + s * b + shift, yy))

    painter.restore()
