import io
import tempfile
import unittest
from pathlib import Path

from pmtiles.reader import MemorySource, Reader
from pmtiles.tile import Compression, TileType, tileid_to_zxy, zxy_to_tileid
from pmtiles.writer import Writer

import core.pmtiles_extract as pmtiles_extract
from core.pmtiles_extract import (
    ExtractCancelled,
    PMTilesExtractError,
    RegionSpec,
    _coalesce_ranges,
    _DirectoryCache,
    _resolve_entry,
    _lonlat_to_tile_xy,
    _tile_ids_for_bbox,
    extract_region,
    find_latest_build_url,
)


class LonLatToTileXyTest(unittest.TestCase):
    def test_zoom_zero_is_always_the_single_tile(self):
        self.assertEqual(_lonlat_to_tile_xy(11.5756, 48.1372, 0), (0, 0))
        self.assertEqual(_lonlat_to_tile_xy(-179.0, 84.0, 0), (0, 0))

    def test_munich_at_zoom_10_matches_known_slippy_tile(self):
        # Hand-verified against the standard OSM slippy-map tile formula:
        # x = floor((lon+180)/360*2^z) = floor(191.5756/360*1024) = 544
        # y = floor((1 - ln(tan(lat_rad)+sec(lat_rad))/pi)/2*2^z) = 355
        self.assertEqual(_lonlat_to_tile_xy(11.5756, 48.1372, 10), (544, 355))

    def test_out_of_range_latitude_is_clamped_not_raising(self):
        _lonlat_to_tile_xy(0.0, 89.9, 5)
        _lonlat_to_tile_xy(0.0, -89.9, 5)


class TileIdsForBboxTest(unittest.TestCase):
    def test_includes_every_zoom_from_zero_to_maxzoom(self):
        ids = _tile_ids_for_bbox(11.0, 48.0, 11.1, 48.1, maxzoom=3)
        zooms = {tileid_to_zxy(t)[0] for t in ids}
        self.assertEqual(zooms, {0, 1, 2, 3})

    def test_no_duplicate_tile_ids_within_a_zoom(self):
        ids = _tile_ids_for_bbox(11.0, 48.0, 11.1, 48.1, maxzoom=2)
        self.assertEqual(len(ids), len(set(ids)))

    def test_a_larger_bbox_yields_more_tiles_at_the_same_maxzoom(self):
        small = _tile_ids_for_bbox(11.0, 48.0, 11.05, 48.05, maxzoom=8)
        large = _tile_ids_for_bbox(5.0, 45.0, 16.0, 55.0, maxzoom=8)
        self.assertLess(len(small), len(large))


def _build_synthetic_pmtiles() -> bytes:
    """A tiny, real, valid PMTiles v3 archive: z0's single tile plus all
    four z1 tiles, each with a distinct payload - enough to exercise
    directory traversal (root + at least the possibility of a leaf) without
    needing a real network fetch."""
    buf = io.BytesIO()
    writer = Writer(buf)
    writer.write_tile(zxy_to_tileid(0, 0, 0), b"tile-z0")
    for x in range(2):
        for y in range(2):
            writer.write_tile(zxy_to_tileid(1, x, y), f"tile-z1-{x}-{y}".encode())
    header = {
        "tile_compression": Compression.NONE,
        "tile_type": TileType.MVT,
        "min_lon_e7": int(-180 * 1e7),
        "min_lat_e7": int(-85 * 1e7),
        "max_lon_e7": int(180 * 1e7),
        "max_lat_e7": int(85 * 1e7),
    }
    writer.finalize(header, {"vector_layers": []})
    return buf.getvalue()


class ResolveEntryTest(unittest.TestCase):
    def setUp(self):
        self.data = _build_synthetic_pmtiles()
        self.get_bytes = MemorySource(self.data)
        self.header = Reader(self.get_bytes).header()
        self.dir_cache = _DirectoryCache(self.get_bytes)

    def test_resolves_the_correct_bytes_for_an_existing_tile(self):
        tile_id = zxy_to_tileid(1, 0, 1)
        offset, length = _resolve_entry(self.dir_cache, self.header, tile_id)
        result = self.get_bytes(self.header["tile_data_offset"] + offset, length)
        self.assertEqual(result, b"tile-z1-0-1")

    def test_returns_none_for_a_tile_not_in_the_source(self):
        tile_id = zxy_to_tileid(5, 10, 10)
        result = _resolve_entry(self.dir_cache, self.header, tile_id)
        self.assertIsNone(result)

    def test_directory_cache_is_reused_across_calls(self):
        fetch_log = []
        original = self.get_bytes

        def counting_get_bytes(offset, length):
            fetch_log.append((offset, length))
            return original(offset, length)

        cache = _DirectoryCache(counting_get_bytes)
        _resolve_entry(cache, self.header, zxy_to_tileid(1, 0, 0))
        count_after_first = len(fetch_log)
        _resolve_entry(cache, self.header, zxy_to_tileid(1, 0, 1))
        # The second lookup hits the same (small, single-level) root
        # directory already cached, and _resolve_entry() never fetches the
        # tile data itself (that's phase 2's job) - so no new fetch at all.
        self.assertEqual(len(fetch_log), count_after_first)


class CoalesceRangesTest(unittest.TestCase):
    def test_empty_input_returns_no_batches(self):
        self.assertEqual(_coalesce_ranges([]), [])

    def test_single_entry_is_its_own_batch(self):
        batches = _coalesce_ranges([(100, 50)])
        self.assertEqual(batches, [(100, 150, [(100, 50)])])

    def test_adjacent_entries_merge_into_one_batch(self):
        entries = [(0, 100), (100, 100), (200, 100)]
        batches = _coalesce_ranges(entries)
        self.assertEqual(len(batches), 1)
        start, end, members = batches[0]
        self.assertEqual((start, end), (0, 300))
        self.assertEqual(members, entries)

    def test_entries_within_the_gap_threshold_merge(self):
        entries = [(0, 100), (100 + 1000, 100)]  # small gap, well under the threshold
        batches = _coalesce_ranges(entries)
        self.assertEqual(len(batches), 1)

    def test_entries_far_apart_stay_in_separate_batches(self):
        entries = [(0, 100), (10_000_000, 100)]  # gap far exceeds the coalescing threshold
        batches = _coalesce_ranges(entries)
        self.assertEqual(len(batches), 2)

    def test_a_batch_never_exceeds_the_max_batch_size(self):
        # Many small, tightly-packed entries that would otherwise all
        # coalesce into one batch must still get split once the max batch
        # byte span is reached.
        entries = [(i * 1000, 500) for i in range(20000)]
        batches = _coalesce_ranges(entries)
        for start, end, members in batches:
            self.assertLessEqual(end - start, 16 * 1024 * 1024)

    def test_every_input_entry_appears_exactly_once_across_all_batches(self):
        entries = [(0, 100), (500, 100), (2_000_000, 100), (2_000_300, 100)]
        batches = _coalesce_ranges(entries)
        all_members = [m for _, _, members in batches for m in members]
        self.assertEqual(sorted(all_members), sorted(entries))


class ExtractRegionTest(unittest.TestCase):
    def setUp(self):
        self.source_bytes = _build_synthetic_pmtiles()
        self._real_http_range_get = pmtiles_extract._http_range_get
        pmtiles_extract._http_range_get = self._fake_http_range_get
        self.tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        pmtiles_extract._http_range_get = self._real_http_range_get
        self.tmpdir.cleanup()

    def _fake_http_range_get(self, url, offset, length):
        return self.source_bytes[offset : offset + length]

    def test_writes_a_valid_smaller_pmtiles_file(self):
        region = RegionSpec("test.pmtiles", "Test", -1.0, -1.0, 1.0, 1.0)
        output_path = Path(self.tmpdir.name) / "test.pmtiles"
        progress_calls = []
        extract_region(
            region, output_path, maxzoom=1, build_url="https://fake.example/planet.pmtiles",
            progress_callback=lambda done, total: progress_calls.append((done, total)),
        )
        self.assertTrue(output_path.is_file())
        self.assertTrue(progress_calls)
        self.assertEqual(progress_calls[-1][0], progress_calls[-1][1])

        # The written file must itself be a valid, readable PMTiles archive.
        written = output_path.read_bytes()
        reader = Reader(MemorySource(written))
        self.assertEqual(reader.get(0, 0, 0), b"tile-z0")
        self.assertEqual(reader.get(1, 0, 0), b"tile-z1-0-0")

    def test_does_not_leave_a_temp_file_behind_on_success(self):
        region = RegionSpec("test.pmtiles", "Test", -1.0, -1.0, 1.0, 1.0)
        output_path = Path(self.tmpdir.name) / "test.pmtiles"
        extract_region(region, output_path, maxzoom=1, build_url="https://fake.example/planet.pmtiles")
        self.assertFalse(output_path.with_suffix(".pmtiles.part").exists())

    def test_cancellation_raises_and_cleans_up(self):
        region = RegionSpec("test.pmtiles", "Test", -1.0, -1.0, 1.0, 1.0)
        output_path = Path(self.tmpdir.name) / "test.pmtiles"
        with self.assertRaises(ExtractCancelled):
            extract_region(
                region, output_path, maxzoom=1, build_url="https://fake.example/planet.pmtiles",
                is_cancelled=lambda: True,
            )
        self.assertFalse(output_path.exists())
        self.assertFalse(output_path.with_suffix(".pmtiles.part").exists())

    def test_bbox_outside_the_source_data_raises(self):
        # A source containing only one tile, far away from anything a
        # low-maxzoom Munich-area extraction would ever request (z0's
        # tile is deliberately absent here, unlike the shared synthetic
        # source, so nothing in the requested range matches at all).
        far_away_source = io.BytesIO()
        writer = Writer(far_away_source)
        writer.write_tile(zxy_to_tileid(5, 31, 31), b"far-away-tile")
        writer.finalize(
            {
                "tile_compression": Compression.NONE, "tile_type": TileType.MVT,
                "min_lon_e7": int(-180 * 1e7), "min_lat_e7": int(-85 * 1e7),
                "max_lon_e7": int(180 * 1e7), "max_lat_e7": int(85 * 1e7),
            },
            {"vector_layers": []},
        )
        far_away_bytes = far_away_source.getvalue()
        pmtiles_extract._http_range_get = lambda url, offset, length: far_away_bytes[offset : offset + length]

        region = RegionSpec("test.pmtiles", "Test", 11.0, 48.0, 11.1, 48.1)
        output_path = Path(self.tmpdir.name) / "test.pmtiles"
        with self.assertRaises(PMTilesExtractError):
            extract_region(region, output_path, maxzoom=3, build_url="https://fake.example/planet.pmtiles")
        self.assertFalse(output_path.exists())


class FindLatestBuildUrlTest(unittest.TestCase):
    def setUp(self):
        self._real_http_range_get = pmtiles_extract._http_range_get

    def tearDown(self):
        pmtiles_extract._http_range_get = self._real_http_range_get

    def test_returns_the_first_url_that_succeeds(self):
        calls = []

        def fake(url, offset, length):
            calls.append(url)
            if len(calls) < 3:
                raise OSError("404")
            return b"x"

        pmtiles_extract._http_range_get = fake
        url = find_latest_build_url()
        self.assertEqual(url, calls[-1])
        self.assertEqual(len(calls), 3)

    def test_raises_when_nothing_succeeds_within_the_lookback_window(self):
        pmtiles_extract._http_range_get = lambda url, offset, length: (_ for _ in ()).throw(OSError("404"))
        with self.assertRaises(PMTilesExtractError):
            find_latest_build_url()


if __name__ == "__main__":
    unittest.main()
