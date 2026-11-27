import logging
import logging.handlers
import os
import sys
import tempfile

_LOG_FORMAT = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

_BENIGN_QT_MESSAGES = (
    "QWindowsWindow::setGeometry: Unable to set geometry",
)


def is_benign_qt_message(message: str) -> bool:
    return any(str(message).startswith(p) for p in _BENIGN_QT_MESSAGES)


def install_qt_message_filter():
    from PySide6 import QtCore

    def handler(mode, context, message):
        if is_benign_qt_message(message):
            return
        try:
            text = QtCore.qFormatLogMessage(mode, context, message)
        except (RuntimeError, TypeError):
            text = message
        print(text, file=sys.stderr)

    QtCore.qInstallMessageHandler(handler)


def get_logger(name: str, filename: str, env_var: str = None,
               max_bytes: int = 1_000_000, backup_count: int = 1) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    log_dir = os.environ.get("TOUCHBAR_LOG_DIR",
                             os.path.join(tempfile.gettempdir(), "anybar"))
    path = os.environ.get(env_var) if env_var else None
    if not path:
        path = os.path.join(log_dir, filename)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
    except OSError:
        handler = logging.NullHandler()
    handler.setFormatter(_LOG_FORMAT)
    logger.addHandler(handler)
    level = os.environ.get("TOUCHBAR_LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, level, logging.INFO))
    logger.propagate = False
    return logger