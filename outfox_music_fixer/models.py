from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


DIFFICULTY_ALIASES = {
    "beginner": "Beginner",
    "easy": "Light",
    "light": "Light",
    "medium": "Standard",
    "standard": "Standard",
    "hard": "Heavy",
    "heavy": "Heavy",
    "challenge": "Challenge",
    "edit": "Edit",
}


@dataclass(frozen=True)
class Chart:
    stepstype: str = ""
    difficulty: str = ""
    meter: str = ""
    description: str = ""
    chart_name: str = ""
    credit: str = ""

    @property
    def normalized_difficulty(self) -> str:
        return DIFFICULTY_ALIASES.get(self.difficulty.strip().lower(), self.difficulty.strip())

    @property
    def display_name(self) -> str:
        parts = [
            self.stepstype.strip(),
            self.normalized_difficulty,
            self.meter.strip(),
        ]
        return " / ".join(part for part in parts if part)


@dataclass(frozen=True)
class Song:
    group: str
    folder_name: str
    directory: Path
    file_path: Path
    file_format: str
    title: str = ""
    artist: str = ""
    genre: str = ""
    bpms: str = ""
    display_bpm: str = ""
    subtitle: str = ""
    credit: str = ""
    music: str = ""
    banner: str = ""
    background: str = ""
    charts: tuple[Chart, ...] = ()
    tags: dict[str, str] = field(default_factory=dict)
    parse_errors: tuple[str, ...] = ()

    @property
    def display_title(self) -> str:
        return self.title.strip() or self.folder_name

    @property
    def bpm_display(self) -> str:
        return self.display_bpm.strip() or self.bpms.strip()

    @property
    def has_genre(self) -> bool:
        return bool(self.genre.strip())

    @property
    def issue_labels(self) -> tuple[str, ...]:
        labels: list[str] = []
        if not self.has_genre:
            labels.append("missing genre")
        if not self.title.strip():
            labels.append("missing title")
        if not self.artist.strip():
            labels.append("missing artist")
        if not self.charts:
            labels.append("no charts")
        if self.parse_errors:
            labels.append("parse warning")
        return tuple(labels)
