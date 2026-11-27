from app.core.logger import get_logger, is_benign_qt_message


class TestGetLogger:
    def test_writes_to_log_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TOUCHBAR_LOG_DIR", str(tmp_path))
        logger = get_logger("anybar.t_writes", "writes.log")
        logger.info("hello %s", "world")
        for h in logger.handlers:
            h.flush()
        assert "hello world" in tmp_path.joinpath("writes.log").read_text(encoding="utf-8")

    def test_env_var_overrides_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TOUCHBAR_LOG_DIR", str(tmp_path))
        custom = tmp_path / "custom.log"
        monkeypatch.setenv("TOUCHBAR_T_CUSTOM", str(custom))
        logger = get_logger("anybar.t_custom", "default.log", env_var="TOUCHBAR_T_CUSTOM")
        logger.info("x")
        for h in logger.handlers:
            h.flush()
        assert custom.exists()
        assert not tmp_path.joinpath("default.log").exists()

    def test_same_name_cached(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TOUCHBAR_LOG_DIR", str(tmp_path))
        l1 = get_logger("anybar.t_cached", "cached.log")
        l2 = get_logger("anybar.t_cached", "cached.log")
        assert l1 is l2
        assert len(l1.handlers) == 1

    def test_level_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TOUCHBAR_LOG_DIR", str(tmp_path))
        monkeypatch.setenv("TOUCHBAR_LOG_LEVEL", "WARNING")
        logger = get_logger("anybar.t_level", "level.log")
        assert logger.level == 30

    def test_default_log_dir(self, monkeypatch):
        import tempfile, os
        monkeypatch.delenv("TOUCHBAR_LOG_DIR", raising=False)
        logger = get_logger("anybar.t_default_dir", "default_dir.log")
        expected_dir = os.path.join(tempfile.gettempdir(), "anybar")
        assert any(os.path.abspath(expected_dir) in os.path.abspath(h.baseFilename)
                   for h in logger.handlers if hasattr(h, "baseFilename"))

class TestQtMessageFilter:
    def test_set_geometry_warning_is_benign(self):
        msg = ("QWindowsWindow::setGeometry: Unable to set geometry "
               "775x675+4092+733 on QWidgetWindow/\"x\" on \"X24QQ1\".")
        assert is_benign_qt_message(msg) is True

    def test_other_warning_is_not_benign(self):
        assert is_benign_qt_message("QPainter::begin: Paint device returned "
                                    "engine == 0") is False

def test_rp_and_tick_log_level_filtering(monkeypatch):
    import logging
    from app.gui.taskbar.window import _rp_log, _rp_logger
    from app.gui.taskbar.widget import _tick_log, _tick_logger

    recorded_rp = []
    recorded_tick = []

    monkeypatch.setattr(_rp_logger, "isEnabledFor", lambda lvl: lvl >= logging.INFO)
    monkeypatch.setattr(_rp_logger, "debug", lambda msg: recorded_rp.append(("DEBUG", msg)))
    monkeypatch.setattr(_rp_logger, "info", lambda msg: recorded_rp.append(("INFO", msg)))

    monkeypatch.setattr(_tick_logger, "isEnabledFor", lambda lvl: lvl >= logging.INFO)
    monkeypatch.setattr(_tick_logger, "debug", lambda msg: recorded_tick.append(("DEBUG", msg)))
    monkeypatch.setattr(_tick_logger, "info", lambda msg: recorded_tick.append(("INFO", msg)))

    _rp_log("snap", x=1)
    _rp_log("deadzone", target=100)
    _rp_log("color", rgb="#000")
    assert recorded_rp == []

    _rp_log("MOVE", x=10, y=20)
    _rp_log("HIDE", fs=True)
    assert len(recorded_rp) == 2
    assert recorded_rp[0] == ("INFO", "MOVE x=10 y=20")
    assert recorded_rp[1] == ("INFO", "HIDE fs=True")

    _tick_log("tick", offset=0)
    _tick_log("swp_pre", r=(0, 0, 0, 0))
    _tick_log("paint", w=100)
    assert recorded_tick == []

    _tick_log("watchdog", lvl=1)
    assert len(recorded_tick) == 1
    assert recorded_tick[0] == ("INFO", "watchdog lvl=1")

