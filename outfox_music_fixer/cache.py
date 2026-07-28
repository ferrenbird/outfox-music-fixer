from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

from .models import Chart, Song
from .scanner import GroupFolder


CACHE_VERSION = 1
APP_DIR_NAME = "OutFox Music Fixer"
CACHE_FILE_NAME = "library-cache.json"
ENV_CACHE_FILE = "OUTFOX_MUSIC_FIXER_CACHE_FILE"


@dataclass(frozen=True)
class CachedLibrary:
    root_path: Path
    group_folders: dict[str, GroupFolder]
    group_order: list[str]
    songs_by_group: dict[str, tuple[Song, ...]]
    saved_at: str

    @property
    def parsed_group_count(self) -> int:
        return len(self.songs_by_group)

    @property
    def song_count(self) -> int:
        return sum(len(songs) for songs in self.songs_by_group.values())


def default_cache_path() -> Path:
    override = os.environ.get(ENV_CACHE_FILE)
    if override:
        return Path(override).expanduser()

    if sys.platform == "darwin":
        base_dir = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    elif sys.platform.startswith("win"):
        base_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        base_dir = base_dir / APP_DIR_NAME
    else:
        base_dir = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        base_dir = base_dir / "outfox-music-fixer"

    return base_dir / CACHE_FILE_NAME


def cache_exists(cache_file: Path | None = None) -> bool:
    return (cache_file or default_cache_path()).exists()


def save_library_cache(
    root_path: Path,
    group_folders: dict[str, GroupFolder],
    group_order: list[str],
    songs_by_group: dict[str, tuple[Song, ...]],
    cache_file: Path | None = None,
) -> Path:
    path = cache_file or default_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": CACHE_VERSION,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root_path": str(root_path),
        "groups": [
            group_to_dict(group_folders[name])
            for name in group_order
            if name in group_folders
        ],
        "songs_by_group": {
            group: [song_to_dict(song) for song in songs]
            for group, songs in songs_by_group.items()
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_library_cache(cache_file: Path | None = None) -> CachedLibrary:
    path = cache_file or default_cache_path()
    payload = json.loads(path.read_text(encoding="utf-8"))

    if payload.get("version") != CACHE_VERSION:
        raise ValueError(f"Unsupported cache version: {payload.get('version')}")

    groups = [group_from_dict(item) for item in payload.get("groups", [])]
    group_folders = {group.name: group for group in groups}
    group_order = [group.name for group in groups]
    songs_by_group = {
        str(group): tuple(song_from_dict(song) for song in songs)
        for group, songs in payload.get("songs_by_group", {}).items()
    }

    return CachedLibrary(
        root_path=Path(payload["root_path"]),
        group_folders=group_folders,
        group_order=group_order,
        songs_by_group=songs_by_group,
        saved_at=str(payload.get("saved_at", "")),
    )


def group_to_dict(group: GroupFolder) -> dict[str, str]:
    return {
        "name": group.name,
        "path": str(group.path),
    }


def group_from_dict(payload: dict[str, Any]) -> GroupFolder:
    return GroupFolder(
        name=str(payload.get("name", "")),
        path=Path(str(payload.get("path", ""))),
    )


def chart_to_dict(chart: Chart) -> dict[str, str]:
    return {
        "stepstype": chart.stepstype,
        "difficulty": chart.difficulty,
        "meter": chart.meter,
        "description": chart.description,
        "chart_name": chart.chart_name,
        "credit": chart.credit,
    }


def chart_from_dict(payload: dict[str, Any]) -> Chart:
    return Chart(
        stepstype=str(payload.get("stepstype", "")),
        difficulty=str(payload.get("difficulty", "")),
        meter=str(payload.get("meter", "")),
        description=str(payload.get("description", "")),
        chart_name=str(payload.get("chart_name", "")),
        credit=str(payload.get("credit", "")),
    )


def song_to_dict(song: Song) -> dict[str, Any]:
    return {
        "group": song.group,
        "folder_name": song.folder_name,
        "directory": str(song.directory),
        "file_path": str(song.file_path),
        "file_format": song.file_format,
        "title": song.title,
        "artist": song.artist,
        "genre": song.genre,
        "bpms": song.bpms,
        "display_bpm": song.display_bpm,
        "subtitle": song.subtitle,
        "credit": song.credit,
        "music": song.music,
        "banner": song.banner,
        "background": song.background,
        "charts": [chart_to_dict(chart) for chart in song.charts],
        "tags": dict(song.tags),
        "parse_errors": list(song.parse_errors),
    }


def song_from_dict(payload: dict[str, Any]) -> Song:
    return Song(
        group=str(payload.get("group", "")),
        folder_name=str(payload.get("folder_name", "")),
        directory=Path(str(payload.get("directory", ""))),
        file_path=Path(str(payload.get("file_path", ""))),
        file_format=str(payload.get("file_format", "")),
        title=str(payload.get("title", "")),
        artist=str(payload.get("artist", "")),
        genre=str(payload.get("genre", "")),
        bpms=str(payload.get("bpms", "")),
        display_bpm=str(payload.get("display_bpm", "")),
        subtitle=str(payload.get("subtitle", "")),
        credit=str(payload.get("credit", "")),
        music=str(payload.get("music", "")),
        banner=str(payload.get("banner", "")),
        background=str(payload.get("background", "")),
        charts=tuple(chart_from_dict(chart) for chart in payload.get("charts", [])),
        tags={str(key): str(value) for key, value in payload.get("tags", {}).items()},
        parse_errors=tuple(str(error) for error in payload.get("parse_errors", [])),
    )
