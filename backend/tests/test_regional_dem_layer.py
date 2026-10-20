from __future__ import annotations

import json
import struct
import zlib

import numpy as np
import pytest
from rasterio.transform import from_origin

from build_regional_dem_layer import (
    build_state_mask,
    color_for_index,
    encode_rgba_png,
    normalize_twi,
    select_tile_names,
)


def test_select_tile_names_parses_only_intersecting_listed_tiles():
    index = """
    Copernicus_DSM_COG_30_N10_00_E076_00_DEM/
    Copernicus_DSM_COG_30_N10_00_E077_00_DEM/
    Copernicus_DSM_COG_30_N20_00_E076_00_DEM/
    Copernicus_DSM_COG_30_S10_00_W076_00_DEM/
    """
    assert select_tile_names(index, bbox=(76.2, 9.7, 76.8, 10.4)) == [
        "Copernicus_DSM_COG_30_N10_00_E076_00_DEM"
    ]


def test_select_tile_names_fails_closed_if_source_index_empty():
    with pytest.raises(RuntimeError, match="no matching tiles"):
        select_tile_names("no tile paths here", bbox=(76, 10, 77, 11))


def test_normalize_twi_only_normalizes_masked_finite_cells():
    twi = np.arange(200, dtype=float).reshape(10, 20)
    twi[2, 3] = np.nan
    mask = np.ones(twi.shape, dtype=bool)
    value, low, high = normalize_twi(twi, mask)
    assert value.shape == twi.shape
    assert value[0, 0] == 0
    assert value[9, 19] == 1
    assert np.isnan(value[2, 3])
    assert high > low


def test_png_encoder_writes_valid_rgba_png_header_and_dimensions():
    rgba = np.zeros((2, 3, 4), dtype=np.uint8)
    rgba[0, 0] = [217, 4, 41, 150]
    encoded = encode_rgba_png(rgba)
    assert encoded.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", encoded[16:24]) == (3, 2)
    assert b"IEND" in encoded


def test_png_colours_match_wetness_legend_and_transparency():
    assert color_for_index(float("nan")) == (0, 0, 0, 0)
    assert color_for_index(0.1)[0:3] == (46, 196, 182)
    assert color_for_index(0.4)[0:3] == (252, 191, 73)
    assert color_for_index(0.6)[0:3] == (247, 127, 0)
    assert color_for_index(0.9)[0:3] == (217, 4, 41)


def test_state_mask_keeps_only_five_named_states():
    core_polygon = {"type": "Polygon", "coordinates": [[[76, 9], [77, 9], [77, 11], [76, 11], [76, 9]]]}
    boundary = {"features": [
        {"properties": {"name": state}, "geometry": core_polygon}
        for state in ("Andhra Pradesh", "Karnataka", "Kerala", "Tamil Nadu", "Telangana")
    ] + [
        {"properties": {"name": "Goa"}, "geometry": {
            "type": "Polygon", "coordinates": [[[73.5, 14], [74, 14], [74, 15], [73.5, 15], [73.5, 14]]]
        }},
    ]}
    mask = build_state_mask(boundary, from_origin(73, 15, 0.1, 0.1), 60, 40)
    assert mask.any()
    assert mask[50, 35]
    assert not mask[5, 5]
