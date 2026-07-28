from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from outfox_music_fixer.cache import load_library_cache, save_library_cache
from outfox_music_fixer.models import Chart, Song
from outfox_music_fixer.scanner import GroupFolder


class CacheTests(unittest.TestCase):
    def test_library_cache_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "cache.json"
            root = Path(tmpdir) / "Songs"
            group = GroupFolder("Pack A", root / "Pack A")
            song = Song(
                group="Pack A",
                folder_name="Song One",
                directory=root / "Pack A" / "Song One",
                file_path=root / "Pack A" / "Song One" / "chart.ssc",
                file_format="ssc",
                title="Song One",
                artist="Artist",
                genre="K-POP",
                bpms="0.000=128.000",
                charts=(Chart(stepstype="dance-single", difficulty="Hard", meter="9"),),
                tags={"TITLE": "Song One", "GENRE": "K-POP"},
                parse_errors=("warning",),
            )

            saved_path = save_library_cache(
                root,
                {"Pack A": group},
                ["Pack A"],
                {"Pack A": (song,)},
                cache_file=cache_file,
            )
            cached = load_library_cache(cache_file)

        self.assertEqual(saved_path, cache_file)
        self.assertEqual(cached.root_path, root)
        self.assertEqual(cached.group_order, ["Pack A"])
        self.assertEqual(cached.group_folders["Pack A"].path, group.path)
        self.assertEqual(cached.songs_by_group["Pack A"][0].title, "Song One")
        self.assertEqual(cached.songs_by_group["Pack A"][0].genre, "K-POP")
        self.assertEqual(cached.songs_by_group["Pack A"][0].charts[0].normalized_difficulty, "Heavy")
        self.assertEqual(cached.songs_by_group["Pack A"][0].tags["GENRE"], "K-POP")
        self.assertEqual(cached.songs_by_group["Pack A"][0].parse_errors, ("warning",))


if __name__ == "__main__":
    unittest.main()
