import logging
import sys
from datetime import datetime
from pathlib import Path

from app.utils.time import IST


RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
CYAN = "\033[36m"
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"

LEVEL_COLORS = {
    logging.DEBUG: BLUE,
    logging.INFO: GREEN,
    logging.WARNING: YELLOW,
    logging.ERROR: RED,
    logging.CRITICAL: f"{BOLD}{MAGENTA}",
}

MESSAGE_COLORS = {
    logging.DEBUG: "\033[37m",
    logging.INFO: "\033[97m",
    logging.WARNING: YELLOW,
    logging.ERROR: RED,
    logging.CRITICAL: f"{BOLD}{RED}",
}

NOISY_LOGGERS = (
    "asyncio",
    "httpcore",
    "httpx",
    "motor",
    "passlib",
    "pymongo",
    "urllib3",
    "watchfiles",
)


class IstFormatter(logging.Formatter):
    def __init__(self, *args, use_color: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.use_color = use_color

    def formatTime(self, record, datefmt=None):  # noqa: N802
        dt = datetime.fromtimestamp(record.created, tz=IST)
        rendered = dt.strftime(datefmt) if datefmt else dt.isoformat()
        if not self.use_color:
            return rendered
        return f"{DIM}{rendered}{RESET}"

    def format(self, record: logging.LogRecord) -> str:
        copy = logging.makeLogRecord(record.__dict__.copy())
        message = record.getMessage().replace("\n", "\n    ")
        copy.msg = self._style_message(record.levelno, message)
        copy.args = ()
        copy.levelname = self._style_level(record.levelno, record.levelname)
        copy.name = self._style_logger_name(record.name)
        return super().format(copy)

    def _style_level(self, levelno: int, levelname: str) -> str:
        label = f"{levelname:<8}"
        if not self.use_color:
            return label
        color = LEVEL_COLORS.get(levelno, CYAN)
        return f"{color}{BOLD}{label}{RESET}"

    def _style_logger_name(self, logger_name: str) -> str:
        label = f"{logger_name:<24.24}"
        if not self.use_color:
            return label
        return f"{CYAN}{label}{RESET}"

    def _style_message(self, levelno: int, message: str) -> str:
        if not self.use_color:
            return message
        color = MESSAGE_COLORS.get(levelno, "\033[97m")
        return f"{color}{message}{RESET}"


def _enable_windows_ansi() -> None:
    try:
        from colorama import just_fix_windows_console
    except ImportError:
        return

    just_fix_windows_console()


def _runtime_log_path() -> Path:
    return Path(__file__).resolve().parents[3] / "logs" / "backend-runtime.log"


def configure_logging(debug: bool = True) -> None:
    _enable_windows_ansi()

    stream_formatter = IstFormatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S %Z",
        use_color=getattr(sys.stderr, "isatty", lambda: False)(),
    )
    file_formatter = IstFormatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S %Z",
        use_color=False,
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(stream_formatter)

    runtime_log_path = _runtime_log_path()
    file_handler = None
    file_handler_error = None
    try:
        runtime_log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(runtime_log_path, encoding="utf-8")
        file_handler.setFormatter(file_formatter)
    except OSError as exc:
        file_handler_error = exc

    root_logger = logging.getLogger()
    for existing_handler in list(root_logger.handlers):
        root_logger.removeHandler(existing_handler)
        existing_handler.close()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(stream_handler)
    if file_handler:
        root_logger.addHandler(file_handler)
    if file_handler_error:
        root_logger.warning("File logging disabled for %s: %s", runtime_log_path, file_handler_error)

    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.DEBUG if debug else logging.INFO)
    app_logger.propagate = True

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(logging.INFO)

    for logger_name in NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
