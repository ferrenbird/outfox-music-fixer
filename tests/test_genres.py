from __future__ import annotations

import unittest
from pathlib import Path

from outfox_music_fixer.genres import build_genre_index, genre_label, sorted_genre_counts
from outfox_music_fixer.models import Song


def make_song(title: str, genre: str) -> Song:
    return Song(
        group="Pack",
        folder_name=title,
        directory=Path("/tmp") / title,
        file_path=Path("/tmp") / title / "chart.ssc",
        file_format="ssc",
        title=title,
        genre=genre,
    )


class GenreTests(unittest.TestCase):
    def test_build_genre_index_keeps_exact_genre_values(self) -> None:
        songs = (
            make_song("One", "KPOP"),
            make_song("Two", "K-POP"),
            make_song("Three", "Korean pop"),
            make_song("Four", "KPOP"),
            make_song("Five", ""),
        )

        index = build_genre_index(songs)

        self.assertEqual(set(index), {"KPOP", "K-POP", "Korean pop", ""})
        self.assertEqual(len(index["KPOP"]), 2)
        self.assertEqual(genre_label(""), "(missing genre)")

    def test_sorted_genre_counts_orders_by_count_and_keeps_missing_last(self) -> None:
        songs = (
            make_song("One", "Pop"),
            make_song("Two", "Rock"),
            make_song("Three", "Pop"),
            make_song("Four", ""),
            make_song("Five", ""),
            make_song("Six", "K-POP"),
        )

        counts = sorted_genre_counts(build_genre_index(songs))

        self.assertEqual(counts, [("Pop", 2), ("K-POP", 1), ("Rock", 1), ("", 2)])


if __name__ == "__main__":
    unittest.main()
