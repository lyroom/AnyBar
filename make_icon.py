import os
import struct
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QBuffer, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPen

SIZES = [16, 24, 32, 48, 64, 128, 256]
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def render(size: int) -> QImage:
    """绘制 Apple iOS/macOS 风格圆角矩形 + 深底黄绿活动环应用图标。"""
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    s = float(size)
    rect = QRectF(s * 0.06, s * 0.06, s * 0.88, s * 0.88)
    bg = QLinearGradient(0.0, rect.top(), 0.0, rect.bottom())
    bg.setColorAt(0.0, QColor("#1E293B"))
    bg.setColorAt(1.0, QColor("#0F172A"))
    p.setPen(QPen(QColor(255, 255, 255, 45), max(1.0, s * 0.03)))
    p.setBrush(bg)
    p.drawRoundedRect(rect, s * 0.22, s * 0.22)

    r = s * 0.27
    cx, cy = s * 0.5, s * 0.5
    stroke = max(2.2, s * 0.11)
    ring_rect = QRectF(cx - r, cy - r, 2.0 * r, 2.0 * r)
    track_pen = QPen(QColor(255, 255, 255, 45), stroke)
    track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(track_pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(ring_rect)

    arc_grad = QLinearGradient(ring_rect.left(), ring_rect.top(),
                               ring_rect.right(), ring_rect.bottom())
    arc_grad.setColorAt(0.0, QColor("#FBBF24"))
    arc_grad.setColorAt(1.0, QColor("#10B981"))
    arc_pen = QPen(arc_grad, stroke)
    arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(arc_pen)
    p.drawArc(ring_rect, 90 * 16, -int(275 * 16))
    p.end()
    return img


def to_png_bytes(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def write_ico(pairs, path):
    count = len(pairs)
    header = struct.pack("<HHH", 0, 1, count)
    offset = 6 + 16 * count
    entries = b""
    data = b""
    for png, s in pairs:
        dim = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        data += png
        offset += len(png)
    with open(path, "wb") as f:
        f.write(header + entries + data)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    pairs = []
    for s in SIZES:
        img = render(s)
        png = to_png_bytes(img)
        pairs.append((png, s))
        if s == 256:
            img.save(os.path.join(OUT_DIR, "icon_256.png"))
    ico_path = os.path.join(OUT_DIR, "icon.ico")
    write_ico(pairs, ico_path)

    img = render(256)
    # 验证深底与不透明度
    c_bg = img.pixelColor(128, 30)
    assert c_bg.alpha() > 200, "背景不透明度不足"
    assert c_bg.red() < 50 and c_bg.green() < 60 and c_bg.blue() < 80, "底色需为深色背景"
    with open(ico_path, "rb") as f:
        head = f.read(6)
    reserved, ico_type, count = struct.unpack("<HHH", head)
    assert (reserved, ico_type, count) == (0, 1, len(SIZES)), "ICO 头部不符"
    sizes = {os.path.getsize(os.path.join(OUT_DIR, n)) for n in ("icon.ico", "icon_256.png")}
    assert all(v > 0 for v in sizes)
    print("ICON_OK", ico_path, os.path.getsize(ico_path), "bytes,", count, "sizes")


if __name__ == "__main__":
    main()
