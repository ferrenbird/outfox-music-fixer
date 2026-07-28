from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from .models import Chart, Song


HEADER_KEYS_TO_IGNORE_IN_TAG_SUMMARY = {"NOTES", "NOTES2"}


@dataclass(frozen=True)
class RawTag:
    name: str
    value: str


def parse_simfile(path: Path, group: str, song_dir: Path) -> Song:
    errors: list[str] = []
    try:
        text = read_text(path)
    except OSError as exc:
        return Song(
            group=group,
            folder_name=song_dir.name,
            directory=song_dir,
            file_path=path,
            file_format=path.suffix.lower().lstrip("."),
            parse_errors=(f"Could not read file: {exc}",),
        )

    tags = parse_tags(text)
    if path.suffix.lower() == ".ssc":
        return parse_ssc(path, group, song_dir, tags, errors)
    return parse_sm(path, group, song_dir, tags, errors)


def read_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_tags(text: str) -> list[RawTag]:
    tags: list[RawTag] = []
    index = 0
    text_length = len(text)

    while index < text_length:
        hash_index = text.find("#", index)
        if hash_index == -1:
            break

        tag_start = hash_index + 1
        tag_end = tag_start
        while tag_end < text_length and (
            text[tag_end].isalnum() or text[tag_end] in {"_", "-"}
        ):
            tag_end += 1

        if tag_end == tag_start:
            index = tag_start
            continue

        cursor = tag_end
        while cursor < text_length and text[cursor].isspace():
            cursor += 1

        if cursor >= text_length or text[cursor] != ":":
            index = tag_end
            continue

        value_start = cursor + 1
        value_end = text.find(";", value_start)
        if value_end == -1:
            value = text[value_start:]
            index = text_length
        else:
            value = text[value_start:value_end]
            index = value_end + 1

        tags.append(RawTag(text[tag_start:tag_end].upper(), value.strip()))

    return tags


def parse_ssc(
    path: Path,
    group: str,
    song_dir: Path,
    tags: list[RawTag],
    errors: list[str],
) -> Song:
    header: OrderedDict[str, str] = OrderedDict()
    chart_tags: OrderedDict[str, str] | None = None
    charts: list[Chart] = []

    for tag in tags:
        if tag.name == "NOTEDATA":
            if chart_tags is not None:
                charts.append(chart_from_ssc_tags(chart_tags))
            chart_tags = OrderedDict()
            continue

        if chart_tags is None:
            if tag.name not in HEADER_KEYS_TO_IGNORE_IN_TAG_SUMMARY:
                header[tag.name] = tag.value
        else:
            if tag.name not in HEADER_KEYS_TO_IGNORE_IN_TAG_SUMMARY:
                chart_tags[tag.name] = tag.value

    if chart_tags is not None:
        charts.append(chart_from_ssc_tags(chart_tags))

    return song_from_header(
        path=path,
        group=group,
        song_dir=song_dir,
        file_format="ssc",
        header=header,
        charts=charts,
        errors=errors,
    )


def parse_sm(
    path: Path,
    group: str,
    song_dir: Path,
    tags: list[RawTag],
    errors: list[str],
) -> Song:
    header: OrderedDict[str, str] = OrderedDict()
    charts: list[Chart] = []

    for tag in tags:
        if tag.name == "NOTES":
            chart = chart_from_sm_notes(tag.value)
            if chart is None:
                errors.append("Could not parse one #NOTES chart block.")
            else:
                charts.append(chart)
            continue
        if tag.name != "NOTES2":
            header[tag.name] = tag.value

    return song_from_header(
        path=path,
        group=group,
        song_dir=song_dir,
        file_format="sm",
        header=header,
        charts=charts,
        errors=errors,
    )


def chart_from_ssc_tags(tags: OrderedDict[str, str]) -> Chart:
    return Chart(
        stepstype=tags.get("STEPSTYPE", ""),
        difficulty=tags.get("DIFFICULTY", ""),
        meter=tags.get("METER", ""),
        description=tags.get("DESCRIPTION", ""),
        chart_name=tags.get("CHARTNAME", ""),
        credit=tags.get("CREDIT", ""),
    )


def chart_from_sm_notes(value: str) -> Chart | None:
    fields = value.split(":", 5)
    if len(fields) < 5:
        return None

    return Chart(
        stepstype=fields[0].strip(),
        description=fields[1].strip(),
        difficulty=fields[2].strip(),
        meter=fields[3].strip(),
    )


def song_from_header(
    path: Path,
    group: str,
    song_dir: Path,
    file_format: str,
    header: OrderedDict[str, str],
    charts: list[Chart],
    errors: list[str],
) -> Song:
    return Song(
        group=group,
        folder_name=song_dir.name,
        directory=song_dir,
        file_path=path,
        file_format=file_format,
        title=header.get("TITLE", ""),
        subtitle=header.get("SUBTITLE", ""),
        artist=header.get("ARTIST", ""),
        genre=header.get("GENRE", ""),
        bpms=header.get("BPMS", ""),
        display_bpm=header.get("DISPLAYBPM", ""),
        credit=header.get("CREDIT", ""),
        music=header.get("MUSIC", ""),
        banner=header.get("BANNER", ""),
        background=header.get("BACKGROUND", ""),
        charts=tuple(charts),
        tags=dict(header),
        parse_errors=tuple(errors),
    )
