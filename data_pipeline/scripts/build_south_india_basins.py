#!/usr/bin/env python3
"""Build a compact South India HydroBASINS GeoJSON layer from the official level-6 ZIP.

The layer is for geographic context and basin-ID/routing candidates, not a flood forecast.
HydroBASINS polygons should be paired with separately verified station coordinates and
river-network checks before a gauge is treated as upstream of a selected location.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import pathlib
import tempfile
import zipfile
import sys

import geopandas as gpd
import pandas as pd

OFFICIAL_SOURCE = 'https://services2.arcgis.com/PYn6bWCjT6bhw1z3/ArcGIS/rest/services/Global_Loaches_2022_WFL1/FeatureServer/2/query'
ARCGIS_LAYER = 'https://services2.arcgis.com/PYn6bWCjT6bhw1z3/ArcGIS/rest/services/Global_Loaches_2022_WFL1/FeatureServer/2'
ATTRIBUTION = 'HydroBASINS v1c, Lehner & Grill (2013), HydroSHEDS; https://www.hydrosheds.org/products/hydrobasins'

def find_field(columns, options):
    lookup = {str(column).strip().upper(): column for column in columns}
    for option in options:
        if option.upper() in lookup:
            return lookup[option.upper()]
    return None

def extract_shapefile(zip_path: pathlib.Path, work_dir: pathlib.Path) -> pathlib.Path:
    required = {'.shp', '.shx', '.dbf', '.prj'}
    with zipfile.ZipFile(zip_path) as zf:
        members = [name for name in zf.namelist() if pathlib.PurePosixPath(name).suffix.lower() in required]
        shp = next((name for name in members if pathlib.PurePosixPath(name).name.lower() == 'hybas_as_lev06_v1c.shp'), None)
        if not shp:
            names = [pathlib.PurePosixPath(name).name for name in members if pathlib.PurePosixPath(name).suffix.lower() == '.shp']
            if len(names) == 1:
                shp = next(name for name in members if pathlib.PurePosixPath(name).name == names[0])
        if not shp:
            raise ValueError('ZIP does not contain an unambiguous HydroBASINS Asia level-6 shapefile.')
        base = pathlib.PurePosixPath(shp).stem
        for member in members:
            if pathlib.PurePosixPath(member).stem == base:
                (work_dir / pathlib.PurePosixPath(member).name).write_bytes(zf.read(member))
        result = work_dir / (base + '.shp')
        if not result.is_file():
            raise ValueError('Failed to extract the selected basin shapefile.')
        return result

def build_layer(basin_path: pathlib.Path, states_path: pathlib.Path, output_path: pathlib.Path, simplify_degrees: float = 0.012):
    basins = gpd.read_file(basin_path)
    states = gpd.read_file(states_path)
    if basins.crs is None or states.crs is None:
        raise ValueError('Both basin and South India mask files must declare a CRS.')
    basins = basins.to_crs('EPSG:4326')
    states = states.to_crs('EPSG:4326')
    states = states[states.geometry.notna() & ~states.geometry.is_empty]
    if states.empty:
        raise ValueError('South India state mask contains no usable polygons.')
    id_col = find_field(basins.columns, ['HYBAS_ID'])
    down_col = find_field(basins.columns, ['NEXT_DOWN'])
    pfaf_col = find_field(basins.columns, ['PFAF_ID'])
    main_col = find_field(basins.columns, ['MAIN_BAS'])
    sub_col = find_field(basins.columns, ['SUB_AREA'])
    up_col = find_field(basins.columns, ['UP_AREA'])
    if not id_col or not down_col:
        raise ValueError('HydroBASINS file must include HYBAS_ID and NEXT_DOWN attributes.')
    region = states.geometry.union_all()
    candidate = basins[basins.geometry.notna() & ~basins.geometry.is_empty & basins.geometry.intersects(region)].copy()
    if candidate.empty:
        raise ValueError('No HydroBASINS polygons intersect the configured regional mask.')
    # Clip to the existing five-state map mask; preserve HYBAS_ID and downstream ID.
    candidate['geometry'] = candidate.geometry.intersection(region)
    candidate = candidate[candidate.geometry.notna() & ~candidate.geometry.is_empty].copy()
    candidate['HYBAS_ID'] = pd.to_numeric(candidate[id_col], errors='coerce')
    candidate['NEXT_DOWN'] = pd.to_numeric(candidate[down_col], errors='coerce').fillna(0).astype('int64')
    candidate['PFAF_ID'] = pd.to_numeric(candidate[pfaf_col], errors='coerce') if pfaf_col else None
    candidate['MAIN_BAS'] = pd.to_numeric(candidate[main_col], errors='coerce') if main_col else None
    candidate['SUB_AREA'] = pd.to_numeric(candidate[sub_col], errors='coerce') if sub_col else None
    candidate['UP_AREA'] = pd.to_numeric(candidate[up_col], errors='coerce') if up_col else None
    candidate = candidate[candidate['HYBAS_ID'].notna()].copy()
    candidate['HYBAS_ID'] = candidate['HYBAS_ID'].astype('int64')
    candidate = candidate.drop_duplicates('HYBAS_ID').copy()
    if candidate['HYBAS_ID'].duplicated().any() or len(candidate) < 10:
        raise ValueError(f'Unexpected basin layer cardinality/IDs: {len(candidate)} features.')
    candidate['geometry'] = candidate.geometry.simplify(simplify_degrees, preserve_topology=True)
    candidate = candidate[['HYBAS_ID', 'NEXT_DOWN', 'PFAF_ID', 'MAIN_BAS', 'SUB_AREA', 'UP_AREA', 'geometry']].to_crs('EPSG:4326')
    candidate = candidate[candidate.geometry.is_valid & ~candidate.geometry.is_empty].copy()
    if len(candidate) < 10:
        raise ValueError('Too few valid basin polygons remain after clipping/simplification.')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    candidate.to_file(output_path, driver='GeoJSON', index=False)
    # Read it back to catch malformed/empty output before CI commits it.
    check = gpd.read_file(output_path)
    if len(check) != len(candidate) or check.crs is None or check.geometry.is_empty.any() or (~check.geometry.is_valid).any():
        raise ValueError('Written basin GeoJSON failed read-back integrity checks.')
    return {
        'source': OFFICIAL_SOURCE, 'attribution': ATTRIBUTION, 'dataset': 'HydroBASINS standard Asia level 6 v1c',
        'level': 6, 'crs': 'EPSG:4326', 'feature_count': int(len(check)),
        'simplify_tolerance_degrees': simplify_degrees, 'mask': str(states_path),
        'output': str(output_path), 'generated_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'attributes': ['HYBAS_ID', 'NEXT_DOWN', 'PFAF_ID', 'MAIN_BAS', 'SUB_AREA', 'UP_AREA'],
        'limits': 'HydroBASINS level 6 is a generalized global watershed product, not an official Indian river-basin boundary or real-time risk map. Clipped polygons support basin IDs only. Gauge-to-target upstream relationships remain candidates until validated with river flowlines and station metadata.',
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument('--basins-zip', type=pathlib.Path, help='Official HydroBASINS Asia ZIP, when directly downloadable.')
    source_group.add_argument('--basins-geojson', type=pathlib.Path, help='Regional GeoJSON queried from the documented HydroBASINS feature service.')
    parser.add_argument('--states', type=pathlib.Path, default=pathlib.Path('data/south-india-states.geojson'))
    parser.add_argument('--output', type=pathlib.Path, default=pathlib.Path('data/south-india-basins.geojson'))
    parser.add_argument('--metadata', type=pathlib.Path, default=pathlib.Path('data/south-india-basins.metadata.json'))
    parser.add_argument('--simplify-degrees', type=float, default=0.012)
    args = parser.parse_args()
    source_path = args.basins_zip or args.basins_geojson
    if source_path is None or not source_path.is_file():
        raise SystemExit(f'Basin source file not found: {source_path}')
    if args.simplify_degrees <= 0 or args.simplify_degrees > 0.1:
        raise SystemExit('--simplify-degrees must be >0 and <=0.1 degrees.')
    with tempfile.TemporaryDirectory(prefix='floodwatch-hydrobasins-') as temp:
        shape = extract_shapefile(args.basins_zip, pathlib.Path(temp)) if args.basins_zip else args.basins_geojson
        metadata = build_layer(shape, args.states, args.output, args.simplify_degrees)
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(metadata, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
