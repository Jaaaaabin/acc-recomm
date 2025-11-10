# src/utils/cli_utils.py
# Simplified CLI helpers with minimal colors and rich progress bars.

import sys
from typing import Optional, Iterable, Iterator, TypeVar, TextIO

try:
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

T = TypeVar("T")

# ===== Simple ANSI colors (reduced palette) =====
RESET = "\033[0m"
BOLD = "\033[1m"

# Only essential colors
BLUE = "\033[94m"      # Info
GREEN = "\033[92m"     # Success
YELLOW = "\033[93m"    # Warning
RED = "\033[91m"       # Error
GRAY = "\033[90m"      # Muted text

_COLOR_ENABLED: bool = True


def set_color_enabled(enabled: bool) -> None:
    """Globally enable/disable colored output."""
    global _COLOR_ENABLED
    _COLOR_ENABLED = enabled


def _colorize(text: str, color: str) -> str:
    """Return text wrapped with ANSI color if enabled."""
    if not _COLOR_ENABLED:
        return text
    return f"{color}{text}{RESET}"


# ===== Simple colored prints =====

def print_info(msg: str, stream: TextIO = sys.stdout) -> None:
    """Print blue [INFO] message."""
    stream.write(f"{_colorize('[INFO]', BLUE)} {msg}\n")
    stream.flush()


def print_success(msg: str, stream: TextIO = sys.stdout) -> None:
    """Print green [OK] message."""
    stream.write(f"{_colorize('[OK]', GREEN)} {msg}\n")
    stream.flush()


def print_warning(msg: str, stream: TextIO = sys.stdout) -> None:
    """Print yellow [WARN] message."""
    stream.write(f"{_colorize('[WARN]', YELLOW)} {msg}\n")
    stream.flush()


def print_error(msg: str, stream: TextIO = sys.stderr) -> None:
    """Print red [ERROR] message."""
    stream.write(f"{_colorize('[ERROR]', RED)} {msg}\n")
    stream.flush()


def print_dim(msg: str, stream: TextIO = sys.stdout) -> None:
    """Print dimmed/gray message (for less important info)."""
    stream.write(f"{_colorize(msg, GRAY)}\n")
    stream.flush()


# ===== Progress Bar using rich =====

def progress_iter(
    iterable: Iterable[T],
    total: Optional[int] = None,
    desc: str = "Processing",
    disable: bool = False
) -> Iterator[T]:
    """
    Wrap an iterable with a progress bar (uses rich if available).
    
    Args:
        iterable: Items to iterate over
        total: Total count (auto-detected if iterable has __len__)
        desc: Description text
        disable: Set to True to disable progress bar
    
    Example:
        for item in progress_iter(data, desc="Loading"):
            process(item)
    """
    if disable or not RICH_AVAILABLE:
        # Fallback: just iterate without progress
        for x in iterable:
            yield x
        return
    
    if total is None:
        try:
            total = len(iterable)  # type: ignore[arg-type]
        except (TypeError, AttributeError):
            # If we can't get length, disable progress bar
            for x in iterable:
                yield x
            return
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        transient=True  # Progress bar disappears when done
    ) as progress:
        task = progress.add_task(desc, total=total)
        for x in iterable:
            yield x
            progress.update(task, advance=1)


class ProgressContext:
    """
    Context manager for manual progress updates.
    
    Example:
        with ProgressContext(total=100, desc="Processing") as progress:
            for i in range(100):
                # ... do work ...
                progress.update(1)
    """
    
    def __init__(self, total: int, desc: str = "Processing", disable: bool = False):
        self.total = total
        self.desc = desc
        self.disable = disable
        self._progress = None
        self._task = None
    
    def __enter__(self):
        if not self.disable and RICH_AVAILABLE:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                transient=True
            )
            self._progress.__enter__()
            self._task = self._progress.add_task(self.desc, total=self.total)
        return self
    
    def __exit__(self, *args):
        if self._progress:
            self._progress.__exit__(*args)
    
    def update(self, advance: int = 1) -> None:
        """Advance progress by specified amount."""
        if self._progress and self._task is not None:
            self._progress.update(self._task, advance=advance)
    
    def set_description(self, desc: str) -> None:
        """Update the progress description."""
        if self._progress and self._task is not None:
            self._progress.update(self._task, description=desc)


# ===== Installation check =====

def check_rich_installed() -> bool:
    """Check if rich is installed."""
    return RICH_AVAILABLE


def suggest_rich_install() -> None:
    """Suggest installing rich if not available."""
    if not RICH_AVAILABLE:
        print_warning("For better progress bars, install: uv add rich")


# ===== Example usage =====
if __name__ == "__main__":
    import time
    
    # Test colored prints
    print_info("Starting application...")
    print_dim("Debug: Initializing components")
    print_warning("Configuration file not found, using defaults")
    print_success("Connected to database")
    print_error("Failed to load optional plugin")
    
    print("\n--- Testing progress_iter ---")
    data = range(50)
    for item in progress_iter(data, desc="Loading data"):
        time.sleep(0.02)
    
    print("\n--- Testing ProgressContext ---")
    with ProgressContext(total=30, desc="Processing items") as progress:
        for i in range(30):
            time.sleep(0.03)
            progress.update(1)
            if i == 15:
                progress.set_description("Processing items (halfway!)")
    
    print_success("All tests completed!")
    
    # Show rich install suggestion if needed
    suggest_rich_install()