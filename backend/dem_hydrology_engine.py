"""Hydrological terrain analysis for georeferenced DEMs.

This module computes depression conditioning, D8 flow accumulation, slope, and
Topographic Wetness Index (TWI). Rainfall-scaled output is an experimental
terrain/wetness screening index, NOT an inundation probability or official alert.

The priority-flood and D8 routines are transparent reference implementations.
Use basin-scale tiles and inspect edge/nodata artefacts before operational use.
"""
from __future__ import annotations

import heapq
import math
from typing import Optional

import numpy as np
from scipy.ndimage import distance_transform_edt


class DEMHydrologyEngine:
    """Hydrological analysis for a two-dimensional elevation grid in metres."""

    _NEIGHBOURS = (
        (-1, -1), (-1, 0), (-1, 1),
        (0, -1),            (0, 1),
        (1, -1),  (1, 0),   (1, 1),
    )

    def __init__(
        self,
        elevation_grid: np.ndarray,
        cell_size_meters: float = 30.0,
        *,
        dx_meters: Optional[float] = None,
        dy_meters: Optional[float] = None,
        valid_mask: Optional[np.ndarray] = None,
    ) -> None:
        dem = np.asarray(elevation_grid, dtype=np.float64)
        if dem.ndim != 2 or min(dem.shape, default=0) < 3:
            raise ValueError("DEM must be a 2-D grid at least 3 by 3 cells.")
        if not np.isfinite(cell_size_meters) or cell_size_meters <= 0:
            raise ValueError("cell_size_meters must be positive and finite.")
        self.dx = float(dx_meters if dx_meters is not None else cell_size_meters)
        self.dy = float(dy_meters if dy_meters is not None else cell_size_meters)
        if not (math.isfinite(self.dx) and self.dx > 0 and math.isfinite(self.dy) and self.dy > 0):
            raise ValueError("DEM x/y cell sizes must be positive, finite metres.")
        mask = np.isfinite(dem)
        if valid_mask is not None:
            supplied = np.asarray(valid_mask, dtype=bool)
            if supplied.shape != dem.shape:
                raise ValueError("valid_mask must have the same shape as the DEM.")
            mask &= supplied
        if mask.sum() < 9:
            raise ValueError("DEM has fewer than nine valid elevation cells.")
        self.dem = dem
        self.valid_mask = mask
        self._conditioned: Optional[np.ndarray] = None
        self._parent: Optional[np.ndarray] = None
        self._receiver: Optional[np.ndarray] = None
        self._accumulation: Optional[np.ndarray] = None

    @staticmethod
    def _neighbour_indices(row: int, col: int, rows: int, cols: int):
        for dr, dc in DEMHydrologyEngine._NEIGHBOURS:
            rr, cc = row + dr, col + dc
            if 0 <= rr < rows and 0 <= cc < cols:
                yield rr, cc

    def condition_dem(self) -> np.ndarray:
        """Fill enclosed depressions using a priority-flood traversal.

        Valid cells touching the raster edge or nodata are treated as outlets.
        Nodata cells remain nodata. The returned array is a copy.
        """
        if self._conditioned is not None:
            return self._conditioned.copy()

        rows, cols = self.dem.shape
        total = rows * cols
        valid = self.valid_mask.ravel()
        elevations = self.dem.ravel()
        filled = np.full(total, np.nan, dtype=np.float64)
        parent = np.full(total, -1, dtype=np.int64)
        visited = np.zeros(total, dtype=bool)
        heap: list[tuple[float, int]] = []

        # Seed outer edges and valid cells adjacent to nodata so masked tiles
        # have explicit outlets and do not force flow across missing elevation.
        for r in range(rows):
            for c in range(cols):
                idx = r * cols + c
                if not valid[idx]:
                    continue
                on_edge = r == 0 or c == 0 or r == rows - 1 or c == cols - 1
                touches_nodata = False
                if not on_edge:
                    for rr, cc in self._neighbour_indices(r, c, rows, cols):
                        if not self.valid_mask[rr, cc]:
                            touches_nodata = True
                            break
                if on_edge or touches_nodata:
                    visited[idx] = True
                    filled[idx] = elevations[idx]
                    heapq.heappush(heap, (float(filled[idx]), idx))

        if not heap:
            raise ValueError("No valid DEM outlet cells were found.")

        while heap:
            level, idx = heapq.heappop(heap)
            r, c = divmod(idx, cols)
            for rr, cc in self._neighbour_indices(r, c, rows, cols):
                nxt = rr * cols + cc
                if not valid[nxt] or visited[nxt]:
                    continue
                visited[nxt] = True
                filled[nxt] = max(float(elevations[nxt]), level)
                parent[nxt] = idx
                heapq.heappush(heap, (float(filled[nxt]), nxt))

        if np.any(valid & ~np.isfinite(filled)):
            raise RuntimeError("Priority-flood conditioning did not reach every valid DEM cell.")
        filled = filled.reshape(self.dem.shape)
        filled[~self.valid_mask] = np.nan
        self._conditioned = filled
        self._parent = parent.reshape(self.dem.shape)
        return filled.copy()

    def calculate_slope(self) -> np.ndarray:
        """Return terrain slope angle in radians, with a 0.001-radian floor."""
        conditioned = self.condition_dem()
        # The raster mask is retained for outputs; nearest valid elevations are
        # used only to prevent NaNs in central-difference calculations at edges.
        if not np.all(self.valid_mask):
            indices = distance_transform_edt(~self.valid_mask, return_distances=False, return_indices=True)
            gradient_dem = conditioned[tuple(indices)]
        else:
            gradient_dem = conditioned
        dz_dy, dz_dx = np.gradient(gradient_dem, self.dy, self.dx, edge_order=1)
        slope = np.arctan(np.hypot(dz_dx, dz_dy))
        slope = np.maximum(slope, 0.001)
        slope[~self.valid_mask] = np.nan
        return slope

    def flow_direction(self) -> np.ndarray:
        """Return D8 downstream receiver indices; -1 denotes an outlet/nodata."""
        if self._receiver is not None:
            return self._receiver.copy()
        filled = self.condition_dem()
        parent = self._parent
        assert parent is not None
        rows, cols = filled.shape
        receiver = np.full(rows * cols, -1, dtype=np.int64)

        for r in range(rows):
            for c in range(cols):
                if not self.valid_mask[r, c]:
                    continue
                idx = r * cols + c
                level = filled[r, c]
                best_slope = 0.0
                best_idx = -1
                for rr, cc in self._neighbour_indices(r, c, rows, cols):
                    if not self.valid_mask[rr, cc]:
                        continue
                    drop = level - filled[rr, cc]
                    if drop <= 1e-10:
                        continue
                    distance = math.hypot((rr - r) * self.dy, (cc - c) * self.dx)
                    grade = float(drop / distance)
                    if grade > best_slope:
                        best_slope, best_idx = grade, rr * cols + cc
                if best_idx >= 0:
                    receiver[idx] = best_idx
                else:
                    # Priority-flood parent resolves flat surfaces without
                    # inventing loops: a parent was visited before its child.
                    parent_idx = int(parent[r, c])
                    if parent_idx >= 0:
                        pr, pc = divmod(parent_idx, cols)
                        if self.valid_mask[pr, pc] and filled[pr, pc] <= level + 1e-10:
                            receiver[idx] = parent_idx

        self._receiver = receiver.reshape(filled.shape)
        return self._receiver.copy()

    def flow_accumulation(self) -> np.ndarray:
        """Return D8 contributing-cell count (includes each cell itself).

        This is true grid-based upstream accumulation for the conditioned DEM,
        not the local-depression proxy sometimes used in illustrative examples.
        """
        if self._accumulation is not None:
            return self._accumulation.copy()
        receiver = self.flow_direction().ravel()
        valid = self.valid_mask.ravel()
        total = valid.size
        incoming = np.zeros(total, dtype=np.int32)
        for idx in np.flatnonzero(valid):
            downstream = int(receiver[idx])
            if downstream >= 0:
                incoming[downstream] += 1

        accumulation = np.zeros(total, dtype=np.float64)
        accumulation[valid] = 1.0
        queue = [int(i) for i in np.flatnonzero(valid & (incoming == 0))]
        head = 0
        processed = 0
        while head < len(queue):
            idx = queue[head]
            head += 1
            processed += 1
            downstream = int(receiver[idx])
            if downstream < 0:
                continue
            accumulation[downstream] += accumulation[idx]
            incoming[downstream] -= 1
            if incoming[downstream] == 0:
                queue.append(downstream)

        if processed != int(valid.sum()):
            raise RuntimeError(
                "D8 flow graph contains a cycle. Check the DEM mask or conditioning result."
            )
        result = accumulation.reshape(self.dem.shape)
        result[~self.valid_mask.reshape(self.dem.shape)] = np.nan
        self._accumulation = result
        return result.copy()

    def specific_catchment_area(self) -> np.ndarray:
        """Approximate specific contributing area in metres from D8 cell counts.

        Cell area is divided by the square-root of cell area as a representative
        contour width; this is a raster approximation, not surveyed catchment area.
        """
        accumulation = self.flow_accumulation()
        cell_area = self.dx * self.dy
        representative_width = math.sqrt(cell_area)
        result = accumulation * cell_area / representative_width
        result[~self.valid_mask] = np.nan
        return result

    def compute_twi(self) -> np.ndarray:
        """Compute TWI = ln(specific catchment area / tan(slope angle))."""
        slope = self.calculate_slope()
        area = self.specific_catchment_area()
        denominator = np.maximum(np.tan(slope), 1e-6)
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            twi = np.log(np.maximum(area, 1e-9) / denominator)
        twi[~self.valid_mask] = np.nan
        return np.nan_to_num(twi, nan=np.nan, posinf=30.0, neginf=np.nan)

    def generate_hazard_grid(
        self,
        twi_matrix: np.ndarray,
        rainfall_24h_mm: float,
    ) -> np.ndarray:
        """Return an experimental normalized terrain/rainfall index in [0, 1].

        This is not a calibrated inundation probability. Rainfall is assumed
        spatially uniform across this DEM tile when represented by one number.
        """
        if not isinstance(rainfall_24h_mm, (int, float)) or not math.isfinite(rainfall_24h_mm) or rainfall_24h_mm < 0:
            raise ValueError("A finite, non-negative 24-hour rainfall estimate is required.")
        twi = np.asarray(twi_matrix, dtype=np.float64)
        if twi.shape != self.dem.shape:
            raise ValueError("TWI matrix shape must match the DEM.")
        valid = self.valid_mask & np.isfinite(twi)
        if not valid.any():
            raise ValueError("TWI contains no valid cells.")
        values = twi[valid]
        low, high = np.percentile(values, [5, 95])
        normalized = np.zeros(twi.shape, dtype=np.float64)
        if high > low:
            normalized[valid] = np.clip((twi[valid] - low) / (high - low), 0.0, 1.0)
        rain_scale = min(float(rainfall_24h_mm) / 150.0, 1.0)
        hazard = normalized * rain_scale
        hazard[~valid] = np.nan
        return hazard
