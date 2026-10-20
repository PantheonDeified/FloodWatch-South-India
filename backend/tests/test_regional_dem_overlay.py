from __future__ import annotations

import numpy as np
import pytest

from build_regional_dem_overlay import (
    colorize_relative_twi,
    decode_terrarium_rgba,
    lat_to_tile_y,
    lon_to_tile_x,
)


def test_terrarium_decoder_reads_fractional_elevation_metres():
    # Terrarium: elevation = (R*256 + G + B/256) - 32768.
    rgba = np.array([[[128, 5, 64, 255]]], dtype=np.uint8)
    elevation, valid = decode_terrarium_rgba(rgba)
    assert elevation[0, 0] == pytest.approx(5.25)
    assert valid[0, 0]


def test_terrarium_transparency_marks_unknown_cells():
    rgba = np.array([[[128, 0, 0, 0], [128, 0, 0, 255]]], dtype=np.uint8)
    elevation, valid = decode_terrarium_rgba(rgba)
    assert np.isfinite(elevation).all()
    assert valid.tolist() == [[False, True]]


def test_south_india_tile_coordinates_are_in_web_mercator_domain():
    x = lon_to_tile_x(78.0, 8)
    y = lat_to_tile_y(14.0, 8)
    assert 0 <= x < 256
    assert 0 <= y < 256
    assert int(x) == 183
    assert int(y) == 117 or int(y) == 118


def test_relative_twi_render_is_colored_and_keeps_nodata_transparent():
    values = np.array([[0.0, 0.25, 0.55, 0.75, 1.0, -9999.0]], dtype=np.float32)
    rgba = colorize_relative_twi(values, low=0.0, high=1.0)
    assert rgba.shape == (1, 6, 4)
    assert rgba[0, 0, 3] == 205
    assert rgba[0, 3, 0] > rgba[0, 0, 0]  # red channel rises into the red hazard class
    assert rgba[0, 4, 0] == 217 and rgba[0, 4, 1] == 4
    assert rgba[0, 5].tolist() == [0, 0, 0, 0]


def test_twi_colorizer_rejects_bad_percentile_range():
    with pytest.raises(ValueError, match="percentile range"):
        colorize_relative_twi(np.array([[1.0, 2.0]]), low=2.0, high=2.0)
