from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from outfox_music_fixer.parser import parse_simfile, parse_tags
from outfox_music_fixer.scanner import discover_groups, parse_song_folder, scan_group, scan_library
from outfox_music_fixer.writer import save_song_metadata


class ParserTests(unittest.TestCase):
    def test_parse_tags_handles_multiline_values(self) -> None:
        text = "#TITLE:Song;\n#BPMS:0.000=120.000,\n64.000=150.000;\n"

        tags = parse_tags(text)

        self.assertEqual(
            [(tag.name, tag.value) for tag in tags],
            [
                ("TITLE", "Song"),
                ("BPMS", "0.000=120.000,\n64.000=150.000"),
            ],
        )

    def test_parse_ssc_metadata_and_charts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            song_dir = Path(tmpdir) / "Pack" / "Song"
            song_dir.mkdir(parents=True)
            path = song_dir / "chart.ssc"
            path.write_text(
                """
#VERSION:0.83;
#TITLE:Blue Sky;
#ARTIST:DJ Example;
#GENRE:House;
#BPMS:0.000=128.000;
#DISPLAYBPM:128;
#NOTEDATA:;
#STEPSTYPE:dance-single;
#DIFFICULTY:Easy;
#METER:4;
#CHARTNAME:Warmup;
#CREDIT:Alice;
#NOTES:
0000
;
#NOTEDATA:;
#STEPSTYPE:dance-double;
#DIFFICULTY:Challenge;
#METER:12;
#NOTES:
0000
;
""",
                encoding="utf-8",
            )

            song = parse_simfile(path, "Pack", song_dir)

        self.assertEqual(song.title, "Blue Sky")
        self.assertEqual(song.artist, "DJ Example")
        self.assertEqual(song.genre, "House")
        self.assertEqual(song.bpm_display, "128")
        self.assertEqual(
            [chart.display_name for chart in song.charts],
            [
                "dance-single / Light / 4",
                "dance-double / Challenge / 12",
            ],
        )

    def test_parse_sm_notes_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            song_dir = Path(tmpdir) / "Pack" / "Song"
            song_dir.mkdir(parents=True)
            path = song_dir / "chart.sm"
            path.write_text(
                """
#TITLE:Classic;
#ARTIST:Sample Artist;
#BPMS:0.000=140.000;
#NOTES:
     dance-single:
     :
     Beginner:
     2:
     0.000,0.000,0.000,0.000,0.000:
0000
;
#NOTES:
     dance-single:
     :
     Hard:
     9:
     0.000,0.000,0.000,0.000,0.000:
0000
;
""",
                encoding="utf-8",
            )

            song = parse_simfile(path, "Pack", song_dir)

        self.assertEqual(song.title, "Classic")
        self.assertEqual(song.genre, "")
        self.assertEqual(song.issue_labels, ("missing genre",))
        self.assertEqual(
            [chart.normalized_difficulty for chart in song.charts],
            ["Beginner", "Heavy"],
        )

    def test_scan_library_prefers_ssc_over_sm(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            song_dir = Path(tmpdir) / "Songs" / "Pack A" / "Song One"
            song_dir.mkdir(parents=True)
            (song_dir / "fallback.sm").write_text(
                "#TITLE:SM Title;\n#GENRE:Rock;\n",
                encoding="utf-8",
            )
            (song_dir / "main.ssc").write_text(
                "#TITLE:SSC Title;\n#GENRE:Pop;\n",
                encoding="utf-8",
            )

            library = scan_library(Path(tmpdir) / "Songs")

        self.assertEqual(len(library.songs), 1)
        self.assertEqual(library.songs[0].file_path.name, "main.ssc")
        self.assertEqual(library.songs[0].group, "Pack A")
        self.assertEqual(library.songs[0].title, "SSC Title")

    def test_scan_library_recurses_within_group_folders(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            song_dir = Path(tmpdir) / "Songs" / "Pack A" / "Nested" / "Song Two"
            song_dir.mkdir(parents=True)
            (song_dir / "chart.sm").write_text(
                "#TITLE:Nested Title;\n#GENRE:Techno;\n",
                encoding="utf-8",
            )
            progress_messages: list[str] = []

            library = scan_library(
                Path(tmpdir) / "Songs",
                progress=progress_messages.append,
            )

        self.assertEqual(len(library.songs), 1)
        self.assertEqual(library.songs[0].group, "Pack A")
        self.assertEqual(library.songs[0].title, "Nested Title")
        self.assertTrue(any("Scanning group: Pack A" in message for message in progress_messages))
        self.assertTrue(any("Found 1 stepfile" in message for message in progress_messages))

    def test_discover_groups_does_not_parse_songs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            group_dir = Path(tmpdir) / "Songs" / "Pack A"
            song_dir = group_dir / "Song One"
            song_dir.mkdir(parents=True)
            (song_dir / "chart.sm").write_text("#TITLE:Deferred;\n", encoding="utf-8")
            progress_messages: list[str] = []

            groups = discover_groups(
                Path(tmpdir) / "Songs",
                progress=progress_messages.append,
            )

        self.assertEqual([group.name for group in groups], ["Pack A"])
        self.assertFalse(any("Parsing" in message for message in progress_messages))

    def test_scan_group_only_parses_selected_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            songs_root = Path(tmpdir) / "Songs"
            first_song_dir = songs_root / "Pack A" / "Song One"
            second_song_dir = songs_root / "Pack B" / "Song Two"
            first_song_dir.mkdir(parents=True)
            second_song_dir.mkdir(parents=True)
            (first_song_dir / "chart.sm").write_text("#TITLE:First;\n", encoding="utf-8")
            (second_song_dir / "chart.sm").write_text("#TITLE:Second;\n", encoding="utf-8")

            groups = discover_groups(songs_root)
            songs = scan_group(songs_root, groups[0])

        self.assertEqual([song.title for song in songs], ["First"])

    def test_stale_stepfile_path_is_skipped_instead_of_returned_as_empty_song(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            song_dir = Path(tmpdir) / "Songs" / "Pack A" / "Song One"
            song_dir.mkdir(parents=True)
            missing_path = song_dir / "missing.sm"
            progress_messages: list[str] = []

            song = parse_song_folder(
                Path(tmpdir) / "Songs",
                song_dir,
                [missing_path],
                progress_messages.append,
            )

        self.assertIsNone(song)
        self.assertTrue(any("skipping" in message for message in progress_messages))

    def test_save_song_metadata_replaces_and_inserts_tags_with_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            song_dir = Path(tmpdir) / "Songs" / "Pack A" / "Song One"
            song_dir.mkdir(parents=True)
            path = song_dir / "chart.ssc"
            path.write_text(
                "#TITLE:Old Title;\n#ARTIST:Old Artist;\n#NOTEDATA:;\n",
                encoding="utf-8",
            )
            song = parse_simfile(path, "Pack A", song_dir)

            updated_song, backup_path = save_song_metadata(
                song,
                {
                    "TITLE": "New Title",
                    "ARTIST": "New Artist",
                    "GENRE": "House",
                },
            )

            written = path.read_text(encoding="utf-8")
            backup_exists = backup_path is not None and backup_path.exists()

        self.assertEqual(updated_song.title, "New Title")
        self.assertEqual(updated_song.artist, "New Artist")
        self.assertEqual(updated_song.genre, "House")
        self.assertIsNotNone(backup_path)
        self.assertTrue(backup_exists)
        self.assertIn("#TITLE:New Title;", written)
        self.assertIn("#ARTIST:New Artist;", written)
        self.assertIn("#GENRE:House;\n#NOTEDATA:;", written)


if __name__ == "__main__":
    unittest.main()
