"""Extracts a bbox-clipped region from Protomaps' public daily planet
PMTiles build (https://build.protomaps.com/YYYYMMDD.pmtiles) into a small,
local *.pmtiles file - via HTTP range requests only, never downloading the
full (~100+ GB) planet file. See docs/feature_plan.md's "PMTiles-Region
herunterladen".

Deliberately a one-shot download, not a live/streaming renderer and not an
auto-update mechanism (checking for newer daily builds, refreshing stale
regions, etc. is out of scope for now - see the plan's P5 note): the user
downloads a region once, and it works fully offline afterward exactly like
a manually-placed file would.

Protomaps' own docs note they discourage hotlinking the daily build bucket
at scale and recommend self-hosting for production use; this is accepted
here for a modest-traffic desktop tool (see the plan for the tradeoff).
"""
from __future__ import annotations

import datetime
import json
import math
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from pmtiles.reader import Reader
from pmtiles.tile import Compression, TileType, deserialize_directory, find_tile, zxy_to_tileid
from pmtiles.writer import Writer

# Matches the real User-Agent-sensitivity observed against
# build.protomaps.com (bare urllib requests without one get a 403, even for
# range requests that otherwise succeed) - a normal browser-like UA avoids
# the block without claiming to be any specific browser.
_USER_AGENT = "Mozilla/5.0 (compatible; ELRSGroundStation/1.0)"
_BUILD_URL_TEMPLATE = "https://build.protomaps.com/{date}.pmtiles"
# Protomaps retains "all builds for the past week" (see docs.protomaps.com/
# basemaps/downloads) - a week plus a small margin covers any single missed
# day without scanning indefinitely.
_MAX_BUILD_LOOKBACK_DAYS = 10
_REQUEST_TIMEOUT_S = 20

MAX_EXTRACT_ZOOM = 14  # matches the existing dev_data/pmtiles region extracts


class PMTilesExtractError(Exception):
    pass


class ExtractCancelled(Exception):
    pass


def find_latest_build_url() -> str:
    """Probes backwards from today (UTC) for the newest daily build that
    actually exists - the exact date isn't predictable/stable (see the
    module docstring's retention note), so this can't be hardcoded."""
    today = datetime.datetime.now(datetime.timezone.utc).date()
    last_error: Optional[Exception] = None
    for days_back in range(_MAX_BUILD_LOOKBACK_DAYS):
        date_str = (today - datetime.timedelta(days=days_back)).strftime("%Y%m%d")
        url = _BUILD_URL_TEMPLATE.format(date=date_str)
        try:
            _http_range_get(url, 0, 1)
            return url
        except Exception as exc:  # noqa: BLE001 - probing, any failure just tries the next day
            last_error = exc
            continue
    raise PMTilesExtractError(
        f"Kein aktueller Protomaps-Build gefunden (letzte {_MAX_BUILD_LOOKBACK_DAYS} Tage geprüft): {last_error}"
    )


def _http_range_get(url: str, offset: int, length: int) -> bytes:
    end = offset + length - 1
    req = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT, "Range": f"bytes={offset}-{end}"}
    )
    with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_S) as resp:
        return resp.read()


def _lonlat_to_tile_xy(lon: float, lat: float, zoom: int) -> Tuple[int, int]:
    lat = max(min(lat, 85.0511), -85.0511)  # Web Mercator's valid latitude range
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


def _tile_ids_for_bbox(min_lon: float, min_lat: float, max_lon: float, max_lat: float, maxzoom: int) -> List[int]:
    """All z/x/y tile IDs (as PMTiles Hilbert tile_ids) covering the bbox,
    for every zoom level from 0 up to maxzoom - low zooms are needed too so
    the map still renders something while zoomed out over the region."""
    tile_ids = []
    for z in range(0, maxzoom + 1):
        x_min, y_max = _lonlat_to_tile_xy(min_lon, min_lat, z)
        x_max, y_min = _lonlat_to_tile_xy(max_lon, max_lat, z)
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                tile_ids.append(zxy_to_tileid(z, x, y))
    return tile_ids


@dataclass
class RegionSpec:
    filename: str
    label_key: str  # core/i18n.py key, not a display string - keeps this module UI-free
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float


# Bounding boxes read directly from each region's own PMTiles header (via
# the `pmtiles show` CLI against the existing dev_data/pmtiles extracts),
# not guessed - see the migration plan. The single source of truth for
# both the auto-selected local file (ui/map_widget.py's
# _select_pmtiles_region()) and the manual "download a region" dialog
# (ui/pmtiles_download_dialog.py).
KNOWN_REGIONS: Tuple[RegionSpec, ...] = (
    RegionSpec("germany.pmtiles", "pmtilesregion_germany", 5.87, 47.27, 15.04, 55.06),
    RegionSpec("austria.pmtiles", "pmtilesregion_austria", 9.53, 46.37, 17.16, 49.02),
    RegionSpec("switzerland.pmtiles", "pmtilesregion_switzerland", 5.96, 45.82, 10.49, 47.81),
    RegionSpec("italy.pmtiles", "pmtilesregion_italy", 6.63, 35.49, 18.58, 47.10),
)
FALLBACK_REGION_FILE = "germany.pmtiles"  # matches the demo default (Munich)


class _DirectoryCache:
    """Leaf directories in a PMTiles file group spatially-close tiles
    together (Hilbert curve ordering) - caching each fetched leaf by its
    (offset, length) means neighboring tiles in the requested bbox reuse
    the same directory fetch instead of re-requesting it per tile."""

    def __init__(self, get_bytes: Callable[[int, int], bytes]) -> None:
        self._get_bytes = get_bytes
        self._cache: Dict[Tuple[int, int], list] = {}

    def get(self, offset: int, length: int) -> list:
        key = (offset, length)
        if key not in self._cache:
            self._cache[key] = deserialize_directory(self._get_bytes(offset, length))
        return self._cache[key]


def _resolve_entry(dir_cache: _DirectoryCache, header: dict, tile_id: int) -> Optional[Tuple[int, int]]:
    """Directory traversal only, no tile-data fetch - returns the tile's
    raw (offset, length) within the tile-data section, or None if the
    source has no such tile."""
    dir_offset = header["root_offset"]
    dir_length = header["root_length"]
    for _ in range(4):  # PMTiles' documented max directory depth
        directory = dir_cache.get(dir_offset, dir_length)
        result = find_tile(directory, tile_id)
        if result is None:
            return None
        if result.run_length == 0:
            dir_offset = header["leaf_directory_offset"] + result.offset
            dir_length = result.length
            continue
        return (result.offset, result.length)
    return None


# Range-request coalescing thresholds for the tile-data fetch phase - a
# real region can address tens of thousands of tiles; one HTTP request per
# tile would take on the order of hours even at good latency. PMTiles'
# Hilbert-curve tile ordering means spatially-close tiles (exactly what a
# bbox query asks for) also tend to sit close together in the tile-data
# section, so merging nearby entries into one larger range request cuts
# the request count by roughly two orders of magnitude in practice.
_MAX_COALESCE_GAP_BYTES = 256 * 1024
_MAX_BATCH_BYTES = 16 * 1024 * 1024


def _coalesce_ranges(sorted_entries: List[Tuple[int, int]]) -> List[Tuple[int, int, List[Tuple[int, int]]]]:
    """Groups (offset, length) entries - already sorted by offset - into
    [start, end) windows, each small/close enough to fetch with a single
    range request. Returns (window_start, window_end, entries_in_window)."""
    if not sorted_entries:
        return []
    batches = []
    batch_start, batch_end = sorted_entries[0][0], sorted_entries[0][0] + sorted_entries[0][1]
    batch_entries = [sorted_entries[0]]
    for offset, length in sorted_entries[1:]:
        end = offset + length
        if offset - batch_end <= _MAX_COALESCE_GAP_BYTES and end - batch_start <= _MAX_BATCH_BYTES:
            batch_end = max(batch_end, end)
            batch_entries.append((offset, length))
        else:
            batches.append((batch_start, batch_end, batch_entries))
            batch_start, batch_end = offset, end
            batch_entries = [(offset, length)]
    batches.append((batch_start, batch_end, batch_entries))
    return batches


def extract_region(
    region: RegionSpec,
    output_path: Path,
    maxzoom: int = MAX_EXTRACT_ZOOM,
    build_url: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
) -> None:
    """Downloads only the tiles covering `region`'s bbox (up to `maxzoom`)
    from the Protomaps daily build via HTTP range requests, and writes them
    as a new, standalone *.pmtiles file at `output_path`. Raises
    PMTilesExtractError / ExtractCancelled on failure; never leaves a
    partial file at `output_path` (writes to a temp path first).

    Two phases, reflected in progress_callback(done, total) (`total` grows
    once phase 1's real size is known - callers must always re-read
    `total`, never cache it): phase 1 resolves which tile-data byte ranges
    are needed (directory traversal only, cheap); phase 2 fetches those
    ranges, coalesced into as few large HTTP requests as possible (see
    _coalesce_ranges()) - this is the phase that actually dominates
    wall-clock time for a real region.
    """
    url = build_url or find_latest_build_url()
    get_bytes = lambda offset, length: _http_range_get(url, offset, length)  # noqa: E731

    try:
        reader = Reader(get_bytes)
        header = reader.header()
        metadata = reader.metadata()
    except Exception as exc:
        raise PMTilesExtractError(f"Kopf-/Metadaten der Quelle konnten nicht gelesen werden: {exc}") from exc

    effective_maxzoom = min(maxzoom, header["max_zoom"])
    tile_ids = sorted(
        set(_tile_ids_for_bbox(region.min_lon, region.min_lat, region.max_lon, region.max_lat, effective_maxzoom))
    )
    total_tiles = len(tile_ids)
    if total_tiles == 0:
        raise PMTilesExtractError("Keine Kacheln für diese Region gefunden.")

    dir_cache = _DirectoryCache(get_bytes)

    def _check_cancelled():
        if is_cancelled is not None and is_cancelled():
            raise ExtractCancelled()

    # --- phase 1: resolve tile_id -> (offset, length), no data fetched yet
    resolved: Dict[int, Tuple[int, int]] = {}
    for i, tile_id in enumerate(tile_ids):
        _check_cancelled()
        entry = _resolve_entry(dir_cache, header, tile_id)
        if entry is not None:
            resolved[tile_id] = entry
        if progress_callback is not None:
            progress_callback(i + 1, total_tiles)

    if not resolved:
        raise PMTilesExtractError("Region enthält keine Kacheln (Quelle deckt diesen Bereich nicht ab).")

    # --- phase 2: fetch the actual tile bytes, batched
    unique_entries = sorted(set(resolved.values()))
    batches = _coalesce_ranges(unique_entries)
    entry_bytes: Dict[Tuple[int, int], bytes] = {}
    for b, (batch_start, batch_end, batch_entries) in enumerate(batches):
        _check_cancelled()
        blob = get_bytes(header["tile_data_offset"] + batch_start, batch_end - batch_start)
        for offset, length in batch_entries:
            entry_bytes[(offset, length)] = blob[offset - batch_start : offset - batch_start + length]
        if progress_callback is not None:
            progress_callback(total_tiles + b + 1, total_tiles + len(batches))

    # --- write the result
    tmp_path = output_path.with_suffix(output_path.suffix + ".part")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    writer = None
    try:
        with open(tmp_path, "wb") as f:
            writer = Writer(f)
            for tile_id in tile_ids:
                entry = resolved.get(tile_id)
                if entry is not None:
                    writer.write_tile(tile_id, entry_bytes[entry])

            if writer.addressed_tiles == 0:
                raise PMTilesExtractError("Region enthält keine Kacheln (Quelle deckt diesen Bereich nicht ab).")

            new_header = {
                "tile_compression": header["tile_compression"],
                "tile_type": header["tile_type"],
                "min_lon_e7": int(region.min_lon * 1e7),
                "min_lat_e7": int(region.min_lat * 1e7),
                "max_lon_e7": int(region.max_lon * 1e7),
                "max_lat_e7": int(region.max_lat * 1e7),
            }
            writer.finalize(new_header, metadata)
    except BaseException:
        # Writer.tile_f (a TemporaryFile staging tile bytes before
        # finalize() copies them into the real output) is only closed by
        # finalize() itself - on any early exit we never reach that, so
        # close it explicitly to avoid leaking the OS file handle.
        if writer is not None:
            writer.tile_f.close()
        tmp_path.unlink(missing_ok=True)
        raise

    tmp_path.replace(output_path)
