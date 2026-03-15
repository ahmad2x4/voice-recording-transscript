import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from .realtime.client import TranscriptEvent

log = logging.getLogger(__name__)

# ANSI colors
GREEN = "\033[32m"
BLUE = "\033[34m"
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"

SPEAKER_COLORS = {
    "You": GREEN,
    "Remote": BLUE,
}


class OutputManager:
    def __init__(self, queue: asyncio.Queue[TranscriptEvent], output_dir: Path):
        self.queue = queue
        self.output_dir = output_dir
        self._file_path: Path | None = None
        self._file = None
        self._current_item: str = ""
        self._current_label: str = ""
        self._current_text: str = ""

    @property
    def file_path(self) -> Path | None:
        return self._file_path

    def _ensure_file(self) -> None:
        if self._file is not None:
            return
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
        self._file_path = self.output_dir / f"transcript_{ts}.txt"
        self._file = open(self._file_path, "w", encoding="utf-8")
        log.info("Transcript file: %s", self._file_path)

    def _color_for(self, label: str) -> str:
        return SPEAKER_COLORS.get(label, YELLOW)

    def _print_delta(self, event: TranscriptEvent) -> None:
        if event.item_id != self._current_item:
            # New utterance — start a new line
            if self._current_item:
                sys.stdout.write("\n")
            self._current_item = event.item_id
            self._current_label = event.label
            self._current_text = ""
            ts = event.timestamp.strftime("%H:%M:%S")
            color = self._color_for(event.label)
            sys.stdout.write(f"{DIM}[{ts}]{RESET} {color}{event.label}:{RESET} ")

        self._current_text += event.text
        sys.stdout.write(event.text)
        sys.stdout.flush()

    def _print_final(self, event: TranscriptEvent) -> None:
        if event.item_id == self._current_item:
            # We were streaming deltas for this item — just finish the line
            sys.stdout.write("\n")
        else:
            # No deltas received — print the full line
            ts = event.timestamp.strftime("%H:%M:%S")
            color = self._color_for(event.label)
            sys.stdout.write(
                f"{DIM}[{ts}]{RESET} {color}{event.label}:{RESET} {event.text}\n"
            )

        sys.stdout.flush()
        self._current_item = ""
        self._current_text = ""

        # Write to file
        self._ensure_file()
        assert self._file is not None
        ts = event.timestamp.strftime("%H:%M:%S")
        self._file.write(f"[{ts}] {event.label}: {event.text}\n")
        self._file.flush()

    async def run(self) -> None:
        try:
            while True:
                event = await self.queue.get()
                if event.is_final:
                    self._print_final(event)
                else:
                    self._print_delta(event)
        except asyncio.CancelledError:
            self.flush()
            raise

    def flush(self) -> None:
        if self._current_item:
            sys.stdout.write("\n")
            sys.stdout.flush()
        if self._file:
            self._file.close()
            self._file = None
