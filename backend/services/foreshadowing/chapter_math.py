# -*- coding: utf-8 -*-
"""Pure chapter/volume math helpers.

These helpers contain no database access. They calculate derived ranges from
volume dictionaries supplied by callers.
"""


def get_clean_chapter_count(volume, default=50):
    if not volume:
        return default
    try:
        value = int(volume.get("chapter_count"))
        return value if value > 0 else default
    except Exception:
        return default


def get_volume_chapter_range(volumes, target_volume_index):
    """Return (start_chapter, end_chapter) for a volume index."""
    target_volume_index = int(target_volume_index)
    start_chapter = 1
    sorted_volumes = sorted(volumes or [], key=lambda item: int(item.get("volume_index", 0)))
    for volume in sorted_volumes:
        volume_index = int(volume.get("volume_index", 0))
        chapter_count = get_clean_chapter_count(volume)
        end_chapter = start_chapter + chapter_count - 1
        if volume_index == target_volume_index:
            return start_chapter, end_chapter
        start_chapter = end_chapter + 1

    if sorted_volumes:
        last_volume = sorted_volumes[-1]
        last_volume_index = int(last_volume.get("volume_index", 0))
        _, last_end = get_volume_chapter_range(sorted_volumes, last_volume_index)
        diff = target_volume_index - last_volume_index
        default_count = get_clean_chapter_count(last_volume)
        start = last_end + (diff - 1) * default_count + 1
        return start, start + default_count - 1

    return (target_volume_index - 1) * 50 + 1, target_volume_index * 50


def get_chapter_volume_index(volumes, chapter_index):
    """Return the volume index that owns chapter_index."""
    chapter_index = int(chapter_index)
    start_chapter = 1
    sorted_volumes = sorted(volumes or [], key=lambda item: int(item.get("volume_index", 0)))
    for volume in sorted_volumes:
        volume_index = int(volume.get("volume_index", 0))
        chapter_count = get_clean_chapter_count(volume)
        end_chapter = start_chapter + chapter_count - 1
        if start_chapter <= chapter_index <= end_chapter:
            return volume_index
        start_chapter = end_chapter + 1

    if sorted_volumes:
        last_volume = sorted_volumes[-1]
        last_volume_index = int(last_volume.get("volume_index", 0))
        _, last_end = get_volume_chapter_range(sorted_volumes, last_volume_index)
        if chapter_index > last_end:
            default_count = get_clean_chapter_count(last_volume)
            diff = (chapter_index - last_end - 1) // default_count + 1
            return last_volume_index + diff

    return (chapter_index - 1) // 50 + 1


def get_total_chapter_count(volumes):
    if not volumes:
        return 1000
    return sum(get_clean_chapter_count(volume) for volume in volumes)
