"""app/gui/hover_panel/cards/music_card.py — 音乐与歌词预览卡片"""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from app.styles import tokens

from ..primitives import TierCard, make_card_header, make_label
from .base import BasePanelCard, PanelCardContext


class MusicPanelCard(BasePanelCard):
    """正在播放音乐与歌词卡片（当 cfg['music'] 存在且含曲名时渲染）。"""

    card_id = "music"

    def build(self, ctx: PanelCardContext) -> QWidget | None:
        music = ctx.cfg.get("music")
        if not (isinstance(music, dict) and music.get("title")):
            return None

        dark, scale = ctx.dark, ctx.scale
        t = tokens.get_tokens(dark)
        sp = lambda v, lo=1: tokens.spx(v, scale, lo=lo)

        card = TierCard(dark, scale)
        v = QVBoxLayout(card)
        v.setContentsMargins(sp(14, 10), sp(10, 7), sp(14, 10), sp(10, 7))
        v.setSpacing(sp(4, 3))
        title = str(music.get("title", ""))
        artist = str(music.get("artist", "")).strip()
        text = title if not artist else f"{title} · {artist}"
        v.addWidget(make_card_header("music", t.accent, text, None, dark, scale))
        lyrics = [str(x) for x in (music.get("lyrics") or []) if str(x).strip()]
        if lyrics:
            v.addWidget(make_label("\n".join(lyrics[:2]), 11 * scale, t.text_muted, 400, wrap=True, role="muted"))
        return card
