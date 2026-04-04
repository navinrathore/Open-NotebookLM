import logging
import os
import contextvars
from logging.handlers import RotatingFileHandler

DEFAULT_LOG_FILE = os.getenv("DATAFLOW_LOG_FILE", "dataflow_agent.log")
DEFAULT_LOG_LEVEL = os.getenv("DATAFLOW_LOG_LEVEL", "INFO").upper()
MAX_LOG_SIZE = 10 * 1024 * 1024
BACKUP_COUNT = 5

# Context variables for request tracking
request_id_var = contextvars.ContextVar('request_id', default=None)
user_id_var = contextvars.ContextVar('user_id', default=None)
user_email_var = contextvars.ContextVar('user_email', default=None)


def set_request_context(request_id=None, user_id=None, user_email=None):
    """Set request context for logging."""
    if request_id:
        request_id_var.set(request_id)
    if user_id:
        user_id_var.set(user_id)
    if user_email:
        user_email_var.set(user_email)

# ANSI Color Codes
COLOR_MAP = {
    "DEBUG": "\033[46m\033[30m",    # Cyan background, black text
    "INFO": "\033[32m",              # Green
    "WARNING": "\033[43m\033[30m",   # Yellow background, black text
    "ERROR": "\033[31m",             # Red
    "CRITICAL": "\033[41m\033[37m",  # Red background, white text
    "RESET": "\033[0m",
}

# Field colors
FIELD_COLORS = {
    "time": "\033[90m",      # Gray
    "name": "\033[35m",      # Purple/Magenta
    "location": "\033[96m",  # Bright cyan
}

class ColorFormatter(logging.Formatter):
    """
    Formatter supporting highlighting for different fields, console output only.
    """
    def format(self, record):
        level_name = record.levelname
        level_color = COLOR_MAP.get(level_name, "")
        reset = COLOR_MAP["RESET"]

        # Format various fields
        asctime = self.formatTime(record, self.datefmt)
        levelname = record.levelname
        name = record.name
        filename = record.filename
        lineno = record.lineno
        message = record.getMessage()

        # Get context information
        req_id = request_id_var.get()
        user_email = user_email_var.get()
        user_id = user_id_var.get()

        # Build context string
        context_parts = []
        if req_id:
            context_parts.append(f"req={req_id[:8]}")
        if user_email:
            context_parts.append(f"user={user_email}")
        elif user_id:
            context_parts.append(f"uid={user_id}")

        context_str = f" [{' '.join(context_parts)}]" if context_parts else ""

        # Combine output with colors - different color for each field
        formatted = (
            f"{FIELD_COLORS['time']}{asctime}{reset} | "
            f"{level_color}{levelname:<8}{reset} | "
            f"{FIELD_COLORS['name']}{name}{context_str}{reset} | "
            f"{FIELD_COLORS['location']}{filename}:{lineno}{reset} | "
            f"{level_color}{message}{reset}"  # Message uses level color
        )

        return formatted

def _create_handler():
    """Create console and file log handlers."""
    # Console output (with color)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(DEFAULT_LOG_LEVEL)
    color_formatter = ColorFormatter(datefmt="%Y-%m-%d %H:%M:%S")
    stream_handler.setFormatter(color_formatter)

    # File output (no color, but includes context)
    file_handler = RotatingFileHandler(DEFAULT_LOG_FILE, maxBytes=MAX_LOG_SIZE, backupCount=BACKUP_COUNT, encoding="utf-8")
    file_handler.setLevel(DEFAULT_LOG_LEVEL)

    class PlainContextFormatter(logging.Formatter):
        """Plain formatter with context support for file output."""
        def format(self, record):
            # Get context information
            req_id = request_id_var.get()
            user_email = user_email_var.get()
            user_id = user_id_var.get()

            # Build context string
            context_parts = []
            if req_id:
                context_parts.append(f"req={req_id[:8]}")
            if user_email:
                context_parts.append(f"user={user_email}")
            elif user_id:
                context_parts.append(f"uid={user_id}")

            context_str = f" [{' '.join(context_parts)}]" if context_parts else ""

            # Add context to record.name
            original_name = record.name
            record.name = f"{original_name}{context_str}"
            result = super().format(record)
            record.name = original_name  # Restore original value
            return result

    plain_formatter = PlainContextFormatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(plain_formatter)
    return [stream_handler, file_handler]

def get_logger(name: str = "dataflow_agent") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handlers = _create_handler()
        for handler in handlers:
            logger.addHandler(handler)
        logger.setLevel(DEFAULT_LOG_LEVEL)
        logger.propagate = False
    return logger

log = get_logger()

if __name__ == "__main__":
    log.info("Logger initialized successfully")
    log.debug("This is a debug message.")
    log.warning("This is a warning.")
    log.error("This is an error.")
    log.critical("This is CRITICAL!")