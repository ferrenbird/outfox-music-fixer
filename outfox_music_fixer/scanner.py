from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import os
from pathlib import Path

from .models import Song
from .parser import parse_simfile


STEPFILE_EXTENSIONS = {".ssc", ".sm"}
EXTENSION_PRIORITY = {".ssc": 0, ".sm": 1}
ProgressCallback = Callable[[str], None]


@dataclass(frozen=True)
class Library:
    root: Path
    songs: tuple[Song, ...]

    @property
    def groups(self) -> tuple[str, ...]:
        return tuple(sorted({song.group for song in self.songs}, key=str.casefold))

    def songs_for_group(self, group: str) -> tuple[Song, ...]:
        return tuple(
            sorted(
                (song for song in self.songs if song.group == group),
                key=lambda song: song.display_title.casefold(),
            )
        )

    @property
    def missing_genre_count(self) -> int:
        return sum(1 for song in self.songs if not song.has_genre)

    @property
    def parse_warning_count(self) -> int:
        return sum(1 for song in self.songs if song.parse_errors)


@dataclass(frozen=True)
class GroupFolder:
    name: str
    path: Path


def discover_groups(root: Path, progress: ProgressCallback | None = None) -> tuple[GroupFolder, ...]:
    emit(progress, f"Opening {root}")
    root = normalize_root(root)
    if not root.exists():
        raise FileNotFoundError(f"Folder does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Path is not a folder: {root}")

    emit(progress, "Loading group folders")
    groups: list[GroupFolder] = []
    if stepfiles_in_folder(root):
        groups.append(GroupFolder(root.name, root))
        emit(progress, f"Selected folder contains stepfiles: {root.name}")

    for group_dir in child_directories(root):
        groups.append(GroupFolder(group_dir.name, group_dir))
        emit(progress, f"Found group: {group_dir.name}")

    emit(progress, f"Loaded {len(groups)} group folder(s)")
    return tuple(groups)


def scan_library(root: Path, progress: ProgressCallback | None = None) -> Library:
    root = normalize_root(root)
    if not root.exists():
        raise FileNotFoundError(f"Folder does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Path is not a folder: {root}")

    groups = discover_groups(root, progress)
    songs = scan_groups(root, groups, progress)

    library = Library(
        root=root,
        songs=tuple(sorted(songs, key=lambda song: (song.group.casefold(), song.display_title.casefold()))),
    )
    emit(progress, f"Finished: {len(library.groups)} group(s), {len(library.songs)} song(s)")
    return library


def scan_group(
    root: Path,
    group: GroupFolder,
    progress: ProgressCallback | None = None,
) -> tuple[Song, ...]:
    return tuple(scan_groups(normalize_root(root), (group,), progress))


def scan_groups(
    root: Path,
    groups: tuple[GroupFolder, ...],
    progress: ProgressCallback | None = None,
) -> list[Song]:
    root = normalize_root(root)
    songs: list[Song] = []
    for index, group in enumerate(groups, start=1):
        emit(progress, f"[{index}/{len(groups)}] Scanning group: {group.name}")
        if group.path == root:
            direct_stepfiles = stepfiles_in_folder(root)
            if direct_stepfiles:
                emit(progress, f"Found {len(direct_stepfiles)} stepfile(s): {root.name}")
                song = parse_song_folder(root, root, direct_stepfiles, progress)
                if song is not None:
                    songs.append(song)
        else:
            songs.extend(scan_group_folder(root, group.path, progress))

    emit(progress, f"Parsed {len(songs)} song(s)")

    return songs


def normalize_root(root: Path) -> Path:
    root = root.expanduser()
    if root.is_absolute():
        return root
    return Path.cwd() / root


def emit(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def child_directories(root: Path) -> list[Path]:
    return sorted(
        (child for child in root.iterdir() if child.is_dir()),
        key=lambda path: path.name.casefold(),
    )


def stepfiles_in_folder(folder: Path) -> list[Path]:
    return sorted(
        (
            child
            for child in folder.iterdir()
            if child.is_file() and child.suffix.lower() in STEPFILE_EXTENSIONS
        ),
        key=lambda path: (EXTENSION_PRIORITY.get(path.suffix.lower(), 99), path.name.casefold()),
    )


def scan_group_folder(
    root: Path,
    start_dir: Path,
    progress: ProgressCallback | None,
) -> list[Song]:
    checked_dirs = 0
    found_song_dirs = 0
    songs: list[Song] = []

    def on_walk_error(error: OSError) -> None:
        emit(progress, f"Warning: could not read {error.filename}: {error.strerror}")

    for current_root, dirnames, filenames in os.walk(start_dir, onerror=on_walk_error):
        checked_dirs += 1
        dirnames.sort(key=str.casefold)
        filenames.sort(key=str.casefold)

        current_dir = Path(current_root)
        matching = [
            current_dir / filename
            for filename in filenames
            if Path(filename).suffix.lower() in STEPFILE_EXTENSIONS
        ]
        if matching:
            found_song_dirs += 1
            relative = display_relative(root, current_dir)
            emit(progress, f"Found {len(matching)} stepfile(s): {relative}")
            song = parse_song_folder(root, current_dir, matching, progress)
            if song is not None:
                songs.append(song)

        if checked_dirs % 100 == 0:
            emit(
                progress,
                f"Checked {checked_dirs} folder(s) under {display_relative(root, start_dir)}; "
                f"found {found_song_dirs} song folder(s)",
            )

    return songs


def parse_song_folder(
    root: Path,
    song_dir: Path,
    stepfiles: list[Path],
    progress: ProgressCallback | None,
) -> Song | None:
    existing_stepfiles = [path for path in stepfiles if path.exists()]
    if not existing_stepfiles:
        emit(progress, f"Warning: skipping {display_relative(root, song_dir)}; no stepfile still exists")
        return None

    chosen = choose_stepfile(existing_stepfiles)
    emit(progress, f"Parsing {display_relative(root, song_dir)}: {chosen.name}")
    group = infer_group(root, song_dir)
    song = parse_simfile(chosen, group, song_dir)

    if is_unreadable_song(song):
        emit(progress, f"Warning: skipping unreadable stepfile: {chosen}")
        for error in song.parse_errors:
            emit(progress, f"Warning: {error}")
        return None

    return song


def is_unreadable_song(song: Song) -> bool:
    return (
        len(song.parse_errors) == 1
        and song.parse_errors[0].startswith("Could not read file:")
        and not song.title
        and not song.artist
        and not song.genre
        and not song.charts
    )


def display_relative(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def choose_stepfile(stepfiles: list[Path]) -> Path:
    return sorted(
        stepfiles,
        key=lambda path: (EXTENSION_PRIORITY.get(path.suffix.lower(), 99), path.name.casefold()),
    )[0]


def infer_group(root: Path, song_dir: Path) -> str:
    try:
        relative = song_dir.relative_to(root)
    except ValueError:
        return root.name

    parts = relative.parts
    if len(parts) >= 2:
        return parts[0]
    return root.name
