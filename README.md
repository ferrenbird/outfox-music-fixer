# OutFox Music Fixer

A small Python 3.13 / PyQt6 desktop app for inspecting StepMania and Project OutFox song libraries.

It scans a local or network-mounted `Songs` folder, groups songs by pack, and shows the metadata most useful for library cleanup:

- title
- artist
- genre
- BPM / display BPM
- available chart styles and difficulties
- other metadata tags present in the simfile
- scan activity for slow local or network-mounted folders
- optional single-song metadata writing with automatic backups
- genre inventory after a full scan
- local cache restore on startup

## Run

```bash
uv sync
uv run outfox-music-fixer
```

You can also run the module directly inside uv's environment:

```bash
uv run python -m outfox_music_fixer
```

## Test

```bash
uv run python -m unittest discover -s tests
```

## Supported Library Layout

The scanner accepts a StepMania-style song root:

```text
Songs/
  Group or Pack Name/
    Song Folder/
      chart.ssc
      chart.sm
```

Network-mounted folders work the same way as local folders as long as they are visible in the filesystem.

If a song folder contains both `.ssc` and `.sm`, the app prefers `.ssc`.

Scanning is recursive inside each group folder, so deeper structures such as `Songs/Pack/Subfolder/Song/chart.ssc` are still found and grouped under `Pack`.

Opening a folder only loads the group folders. Selecting a group parses just that group. Use `Scan All Groups` only when you want to parse the whole library.

## Local Cache

The app stores the last loaded library state as JSON in the user's app-data folder. On macOS, the default path is:

```text
~/Library/Application Support/OutFox Music Fixer/library-cache.json
```

On startup, if a cache exists, the app asks whether to load it. Loading the cache restores the last root folder, group list, parsed song metadata, and genre inventory without touching the network-mounted library.

The cache is only a convenience snapshot. If files changed outside the app, use `Rescan Group` or `Scan All Groups` to refresh from disk.

## Genre Cleanup

The `Genres` tab shows exact genre values found in parsed songs. For a complete genre inventory, run `Scan All Groups` first.

This intentionally does not normalize values yet. If your library contains `KPOP`, `K-POP`, and `Korean pop`, they appear as separate genre buckets with their own song counts. Select a genre to review every song currently using that value, then edit a selected song's `Genre` field if needed.

## Editing Metadata

The app starts in read-only mode. To edit a single song:

1. Select a group and song.
2. Turn off `Read-only`.
3. Edit `Title`, `Artist`, or `Genre`.
4. Click `Save Metadata`.

Each save writes only the selected `.ssc` or `.sm` file and creates a timestamped `.bak` file beside it first. BPMs and chart data are still read-only.

## StepMania / OutFox Metadata Notes

The StepMania `.ssc` wiki documents `#GENRE` as a normal header tag, and also lists other useful song-level tags including `#TITLE`, `#SUBTITLE`, `#ARTIST`, transliteration tags, `#ORIGIN`, `#CREDIT`, `#BANNER`, `#BACKGROUND`, `#JACKET`, `#CDTITLE`, `#MUSIC`, `#PREVIEW`, `#OFFSET`, `#SAMPLESTART`, `#SAMPLELENGTH`, `#SELECTABLE`, `#BPMS`, `#DISPLAYBPM`, and timing/effect tags such as `#STOPS`, `#DELAYS`, `#WARPS`, `#SPEEDS`, `#SCROLLS`, `#FAKES`, `#LABELS`, `#BGCHANGES`, `#KEYSOUNDS`, and `#ATTACKS`.

The same wiki notes that `.ssc` supports per-chart note data sections with fields such as `#STEPSTYPE`, `#DIFFICULTY`, `#METER`, `#CHARTNAME`, `#DESCRIPTION`, `#RADARVALUES`, and chart-level `#CREDIT`.

Source: <https://github.com/stepmania/stepmania/wiki/ssc>

## Current Scope

- No database.
- No direct SFTP/HTTP connector.
- Writes are limited to `#TITLE`, `#ARTIST`, and `#GENRE` for one selected song at a time.
- No genre inference yet.

Good next steps are safe genre writing with backups, bulk filters, and optional genre suggestions from local audio metadata or external music databases.

## AI DISCLAIMER
This app is vibe-coded with Codex. I am developing many pieces of software by hand. This is not one of them. I'm simply committing this to version control on the off-chance it helps someone else.

I will try to maintain this one to the best of my abilities, and I will be optimizing it to not be so slop-tastic in the future. But for now, you have been warned.