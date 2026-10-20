from __future__ import annotations

import json
import math

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin

from dem_hydrology_engine import DEMHydrologyEngine
from export_hazard_geojson import (
    export_hazard_raster_to_geojson,
    load_dem_projected,
)


def test_priority_flood_fills_a_closed_depression():
    dem = np.full((9, 9), 10.0)
    dem[3:6, 3:6] = 20.0
    dem[4, 4] = 5.0
    engine = DEMHydrologyEngine(dem, cell_size_meters=30.0)
    conditioned = engine.condition_dem()
    assert conditioned[4, 4] == pytest.approx(20.0)
    assert conditioned[4, 4] > dem[4, 4]


def test_slope_radians_matches_planar_gradient():
    rows, cols = np.indices((8, 8))
    dem = 4.0 * rows + 3.0 * cols
    engine = DEMHydrologyEngine(dem, dx_meters=30.0, dy_meters=30.0)
    slope = engine.calculate_slope()
    expected = math.atan(math.hypot(3.0 / 30.0, 4.0 / 30.0))
    assert np.nanmedian(slope[1:-1, 1:-1]) == pytest.approx(expected, abs=1e-7)


def test_d8_flow_accumulation_routes_across_a_downhill_plane():
    dem = np.tile(np.arange(9, dtype=float)[::-1], (9, 1))
    engine = DEMHydrologyEngine(dem, cell_size_meters=30.0)
    accumulation = engine.flow_accumulation()
    assert np.nanmax(accumulation) >= 9
    assert np.nanmin(accumulation) >= 1


def test_twi_and_hazard_index_are_finite_and_bounded():
    rows, cols = np.indices((10, 10))
    dem = 300.0 - 2.0 * cols + rows
    engine = DEMHydrologyEngine(dem, cell_size_meters=30.0)
    twi = engine.compute_twi()
    hazard = engine.generate_hazard_grid(twi, 75.0)
    assert np.isfinite(twi).all()
    assert np.nanmin(hazard) >= 0.0
    assert np.nanmax(hazard) <= 1.0
    assert np.nanmax(hazard) <= 0.5 + 1e-7


def test_nodata_is_preserved_in_outputs():
    dem = np.full((8, 8), 100.0)
    mask = np.ones((8, 8), dtype=bool)
    mask[3, 3] = False
    dem[3, 3] = np.nan
    engine = DEMHydrologyEngine(dem, cell_size_meters=30.0, valid_mask=mask)
    assert np.isnan(engine.condition_dem()[3, 3])
    assert np.isnan(engine.calculate_slope()[3, 3])
    assert np.isnan(engine.compute_twi()[3, 3])


def test_missing_or_invalid_rainfall_is_not_a_zero_rain_fallback():
    engine = DEMHydrologyEngine(np.full((5, 5), 10.0), cell_size_meters=30.0)
    twi = engine.compute_twi()
    with pytest.raises(ValueError, match="rainfall"):
        engine.generate_hazard_grid(twi, None)
    with pytest.raises(ValueError, match="rainfall"):
        engine.generate_hazard_grid(twi, -1.0)


def test_geojson_export_uses_wgs84_polygons_and_labels_index_not_probability(tmp_path):
    hazard = np.array([[0.1, 0.3, 0.6], [0.8, 0.2, 0.4], [0.0, 0.9, 0.7]], dtype=float)
    twi = np.full((3, 3), 8.0)
    slope = np.full((3, 3), 0.1)
    flow = np.full((3, 3), 5.0)
    output = tmp_path / "hazard.geojson"
    count = export_hazard_raster_to_geojson(
        hazard,
        affine_transform=from_origin(76.4, 10.2, 0.01, 0.01),
        source_crs=CRS.from_epsg(4326),
        output_filename=output,
        twi_grid=twi,
        slope_radians=slope,
        flow_accumulation=flow,
        rainfall_24h_mm=80.0,
        rainfall_source="test input",
        dem_source="test-dem.tif",
        min_index=0.25,
        max_features=10,
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    assert count == 6
    assert len(data["features"]) == 6
    assert all(feature["geometry"]["type"] == "Polygon" for feature in data["features"])
    assert all(feature["properties"]["hazard_index"] >= 0.25 for feature in data["features"])
    assert "not inundation probability" in data["metadata"]["note"]
    assert "probability" not in data["features"][0]["properties"]


def test_geojson_export_caps_feature_count(tmp_path):
    hazard = np.ones((10, 10), dtype=float)
    output = tmp_path / "bounded.geojson"
    count = export_hazard_raster_to_geojson(
        hazard,
        affine_transform=from_origin(76.4, 10.2, 0.001, 0.001),
        source_crs=CRS.from_epsg(4326),
        output_filename=output,
        rainfall_24h_mm=150.0,
        rainfall_source="test input",
        dem_source="test-dem.tif",
        min_index=0.0,
        max_features=7,
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    assert count == 7
    assert len(data["features"]) == 7


def test_dem_loader_requires_georeferenced_raster(tmp_path):
    no_crs_dem = tmp_path / "no-crs.tif"
    with rasterio.open(
        no_crs_dem, "w", driver="GTiff", height=8, width=8, count=1,
        dtype="float32", transform=from_origin(76.4, 10.2, 0.001, 0.001),
    ) as dst:
        dst.write(np.full((8, 8), 10.0, dtype=np.float32), 1)
    with pytest.raises(ValueError, match="no CRS"):
        load_dem_projected(no_crs_dem)


def test_dem_loader_reprojects_a_small_geotiff_to_metric_utm(tmp_path):
    source_dem = tmp_path / "source-dem.tif"
    rows, cols = np.indices((30, 30))
    values = (100.0 + 0.2 * rows + 0.1 * cols).astype(np.float32)
    with rasterio.open(
        source_dem, "w", driver="GTiff", height=30, width=30, count=1,
        dtype="float32", crs="EPSG:4326", transform=from_origin(76.4, 10.2, 0.001, 0.001),
        nodata=-9999.0,
    ) as dst:
        dst.write(values, 1)
    dem, valid, transform, crs, dx, dy = load_dem_projected(
        source_dem, cell_size_meters=30.0, max_cells=10_000
    )
    assert crs.is_projected
    assert dem.ndim == 2 and dem.shape == valid.shape
    assert valid.sum() >= 9
    assert dx > 0 and dy > 0
    assert np.isfinite(dem[valid]).all()
