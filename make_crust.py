from typing import Optional, Tuple, Dict

import numpy as np
from scipy import signal

from data.chunks import ChunkGrid, Chunk
from data.index_dict import Index
from mathlib import Vec3i, Vec3f
from model.model_pts import PtsModelLoader
from filters.dilate import dilate
from filters.fill import flood_fill_at
from render_cloud import CloudRender
from render_voxel import VoxelRender

def scale_model(model: np.ndarray, resolution=64) -> Tuple[np.ndarray, Vec3f, float]:
    assert model.ndim == 2 and model.shape[1] == 3

    model_min, model_max = np.min(model, axis=0), np.max(model, axis=0)
    model_delta_max = np.max(model_max - model_min)
    scale_factor = resolution / model_delta_max
    scaled = (model - model_min) * scale_factor

    return scaled, model_min, scale_factor


def find_empty_point_in_chunk(chunk: Chunk[bool]) -> Optional[Vec3i]:
    pt = np.argwhere(chunk.to_array())
    if len(pt) > 0:
        return pt[0] + chunk.position_low
    return None


def find_empty_fill_position(mask: ChunkGrid[bool]) -> Optional[Vec3i]:
    for i, c in mask.chunks.items():
        if c.any():
            return find_empty_point_in_chunk(c)
    return None


def plot(components: ChunkGrid[int], colors: int = 0,
         model: Optional[np.ndarray] = None,
         fill_points: Optional[ChunkGrid[bool]] = None):
    ren = VoxelRender()
    fig = ren.make_figure()
    if model is not None:
        fig.add_trace(CloudRender().make_scatter(model, marker=dict(size=0.45), mode="text+markers", name="Model"))
    # fig.add_trace(ren.grid_voxel(crust, opacity=0.2, name='Crust'))
    if colors > 2:
        fig.add_trace(ren.grid_voxel(components == 2, opacity=0.1, name=f"Hull 2"))
    for c in range(3, colors):
        fig.add_trace(ren.grid_voxel(components == c, opacity=1.0, name=f"Comp {c}"))

    if fill_points is not None:
        fig.add_trace(ren.grid_voxel(fill_points, opacity=1.0, color='red', name="Fill points"))
    fig.update_layout(showlegend=True)
    fig.show()


def points_on_chunk_hull(grid: ChunkGrid[bool], count: Optional[int] = None) -> Optional[np.ndarray]:
    if len(grid.chunks) == 0:
        return None

    pts_iter = (c.position_low for c in grid.iter_hull() if c.is_filled() and not c.value)
    pts = []
    for p, _ in zip(pts_iter, range(count)):
        pts.append(p)
    if pts:
        return np.asarray(pts, dtype=int)
    else:
        for c in grid.iter_hull():
            if c.any():
                p = find_empty_point_in_chunk(c)
                if p is not None:
                    return p
    return None


def fill(fill_position: Optional[Vec3i], fill_points: ChunkGrid[bool], components: ChunkGrid[int], mask_empty,
         color: int, verbose=0, max_color=5) -> (int, ChunkGrid[int]):
    while fill_position is not None:

        fill_points[fill_position] = True

        if not mask_empty.any():
            raise ValueError("WTF")

        if verbose > 2:
            print(f"c:\t{color} \tpos: {fill_position},")

        # Flood fill the position with the current color
        fill_mask = flood_fill_at(fill_position, mask=mask_empty, verbose=verbose > 5)
        components[fill_mask] = color

        # Update mask
        mask_empty = components == 0

        # Find next fill position
        fill_position = find_empty_fill_position(mask_empty)
        if color > max_color:
            break
        color += 1  # Increment color
    return color, components


def get_crust(chunk_size: int, max_steps: int, revert_steps: int, model: np.ndarray, verbose=0) -> ChunkGrid[bool]:
    crust = ChunkGrid(chunk_size, dtype=bool, fill_value=False)
    crust[model] = True

    # Add a chunk layer around the model (fast-flood-fill can wrap the model immediately)
    crust.pad_chunks(1)

    # A counter of the components per step
    last_crust: [ChunkGrid[bool]] = [crust]
    last_count = 0
    for step in range(0, max_steps):
        # Initialize empty component grid
        components: ChunkGrid[int] = crust.astype(int).copy()

        # Keeping track of starting points for flood fill
        fill_points = ChunkGrid(chunk_size, dtype=bool)

        # find some outer empty chunks that were padded and use it as first fill position of component 2 (= outer fill)
        # fill_position: Optional[Vec3i] = next(crust.hull()).index * chunk_size
        fill_position: Optional[Vec3i] = points_on_chunk_hull(crust, count=1)

        # Mask for filling, when empty abort!
        mask_empty = components == 0

        # Color value of the filled components
        color = 2
        color, components = fill(fill_position, fill_points, components, mask_empty, color)

        plot(components, color, model, fill_points)

        count = color - 1

        if verbose > 1:
            print(last_count, "->", count)
        if count == 2:
            if verbose > 0:
                print("Winner winner chicken dinner!")
            return last_crust[0]

        last_count = count
        last_crust.append(crust.copy())
        if len(last_crust) > revert_steps:
            last_crust.pop(0)
        crust = dilate(crust)
    return crust


def get_diffusion(crust: ChunkGrid[bool], model: np.ndarray, iterations: int = 3) -> ChunkGrid[float]:
    distance: ChunkGrid[float] = ChunkGrid(crust.chunk_size, dtype=float, fill_value=1.0)
    distance[crust] = 1.0
    distance[model] = 0.0
    kernel = np.array([[[0, 0, 0],
                        [0, 1, 0],
                        [0, 0, 0]],
                       [[0, 1, 0],
                        [1, 1, 1],
                        [0, 1, 0]],
                       [[0, 0, 0],
                        [0, 1, 0],
                        [0, 0, 0]]], dtype=float)
    kernel = kernel / 7

    for i in range(iterations):
        points_per_chunk: Dict[Index, np.ndarray] = {}
        for chunk in distance.chunks:
            points_per_chunk[tuple(chunk.index)] = chunk.to_array() == 0
        for chunk in distance.chunks:
            padded_chunk = chunk.padding(distance, 1)
            result = signal.convolve(padded_chunk, kernel, mode='valid')
            # result = result[1:-1, 1:-1, 1:-1]
            result[points_per_chunk[tuple(chunk.index)]] = 0
            chunk.set_array(result)
    distance[crust == False] = 1.0
    return distance


if __name__ == '__main__':
    data = PtsModelLoader().load("models/bunny/bunnyData.pts")
    # data = PlyModelLoader().load("models/dragon_stand/dragonStandRight.conf")
    # data = MeshModelLoader(samples=30000, noise=0.1).load("models/cat/cat_reference.obj")

    num_revert_steps, max_color = 5, 3  # bunny
    # num_revert_steps, max_color = 5, 3  # dragon
    # num_revert_steps, max_color = 5, 3  # cat

    verbose = 2
    chunk_size = 16
    max_steps = 3

    model, model_offset, model_scale = scale_model(data, resolution=64)

    crust = get_crust(chunk_size, max_steps, num_revert_steps, model)
    diffusion = get_diffusion(crust, model)

    ren = VoxelRender()
    fig = ren.make_figure()
    # fig.add_trace(ren.grid_voxel(crust, opacity=0.1, name='Crust'))
    fig.add_trace(CloudRender().make_value_scatter(diffusion, mask=(crust & (diffusion != 1.0)),
                                                   name="Diffusion",
                                                   marker=dict(
                                                       size=2.0,
                                                       opacity=0.7,
                                                       colorscale='Viridis'
                                                   ),
                                                   mode="markers", ))
    fig.show()
