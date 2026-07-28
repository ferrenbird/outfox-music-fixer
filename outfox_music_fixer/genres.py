from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from .models import Song


MISSING_GENRE = ""
MISSING_GENRE_LABEL = "(missing genre)"


def genre_key(song: Song) -> str:
    return song.genre.strip()


def genre_label(genre: str) -> str:
    return genre or MISSING_GENRE_LABEL


def build_genre_index(songs: Iterable[Song]) -> dict[str, tuple[Song, ...]]:
    grouped: dict[str, list[Song]] = defaultdict(list)
    for song in songs:
        grouped[genre_key(song)].append(song)

    return {
        genre: tuple(sorted(items, key=lambda song: (song.group.casefold(), song.display_title.casefold())))
        for genre, items in grouped.items()
    }


def sorted_genre_counts(index: dict[str, tuple[Song, ...]]) -> list[tuple[str, int]]:
    return sorted(
        ((genre, len(songs)) for genre, songs in index.items()),
        key=lambda item: (item[0] == MISSING_GENRE, -item[1], item[0].casefold()),
    )
