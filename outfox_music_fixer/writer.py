from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

from .models import Song
from .parser import parse_simfile


WRITABLE_TAGS = ("TITLE", "ARTIST", "GENRE")
ENCODINGS = ("utf-8", "cp1252", "latin-1")


def save_song_metadata(song: Song, updates: dict[str, str]) -> tuple[Song, Path | None]:
    normalized_updates = {
        key.upper(): sanitize_tag_value(value)
        for key, value in updates.items()
        if key.upper() in WRITABLE_TAGS
    }
    if not normalized_updates:
        return song, None

    current_values = {
        "TITLE": song.title,
        "ARTIST": song.artist,
        "GENRE": song.genre,
    }
    changed = {
        key: value
        for key, value in normalized_updates.items()
        if current_values.get(key, "") != value
    }
    if not changed:
        return song, None

    text, encoding = read_text_with_encoding(song.file_path)
    updated_text = apply_header_updates(text, changed)

    backup_path = make_backup_path(song.file_path)
    shutil.copy2(song.file_path, backup_path)
    song.file_path.write_text(updated_text, encoding=encoding, newline="")

    return parse_simfile(song.file_path, song.group, song.directory), backup_path


def read_text_with_encoding(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig"

    for encoding in ENCODINGS:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8"


def sanitize_tag_value(value: str) -> str:
    return " ".join(value.replace(";", " ").split())


def apply_header_updates(text: str, updates: dict[str, str]) -> str:
    header_end = first_chart_tag_index(text)
    updated = text
    offset = 0

    for key, value in updates.items():
        replacement = f"#{key}:{value};"
        span = find_header_tag_span(updated, key, header_end + offset)
        if span is None:
            insert_at = header_end + offset
            prefix = "" if insert_at == 0 or updated[insert_at - 1] == "\n" else "\n"
            inserted = f"{prefix}{replacement}\n"
            updated = updated[:insert_at] + inserted + updated[insert_at:]
            offset += len(inserted)
        else:
            start, end = span
            updated = updated[:start] + replacement + updated[end:]
            offset += len(replacement) - (end - start)

    return updated


def first_chart_tag_index(text: str) -> int:
    upper_text = text.upper()
    candidates = [
        index
        for marker in ("#NOTEDATA", "#NOTES")
        if (index := upper_text.find(marker)) != -1
    ]
    return min(candidates) if candidates else len(text)


def find_header_tag_span(text: str, key: str, header_end: int) -> tuple[int, int] | None:
    index = 0
    key = key.upper()
    while index < header_end:
        hash_index = text.find("#", index, header_end)
        if hash_index == -1:
            return None

        tag_start = hash_index + 1
        tag_end = tag_start
        while tag_end < header_end and (text[tag_end].isalnum() or text[tag_end] in {"_", "-"}):
            tag_end += 1

        if tag_end == tag_start:
            index = tag_start
            continue

        cursor = tag_end
        while cursor < header_end and text[cursor].isspace():
            cursor += 1

        if cursor >= header_end or text[cursor] != ":":
            index = tag_end
            continue

        value_end = text.find(";", cursor + 1)
        if value_end == -1 or value_end > header_end:
            return None

        if text[tag_start:tag_end].upper() == key:
            return hash_index, value_end + 1
        index = value_end + 1

    return None


def make_backup_path(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.name}.{timestamp}.bak")
    counter = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.{timestamp}-{counter}.bak")
        counter += 1
    return candidate
