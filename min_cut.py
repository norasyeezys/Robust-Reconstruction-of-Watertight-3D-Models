import maxflow
from model.model_pts import PtsModelLoader
from make_crust import get_crust, get_diffusion, scale_model
import numpy as np

from render_cloud import CloudRender
from render_voxel import VoxelRender

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

num_voxels = diffusion.chunks.__len__() * pow(diffusion.chunk_size, 3)
g = maxflow.Graph[float](num_voxels * 3, num_voxels * 4)
nodes = {}
sorted_keys = sorted(diffusion.chunks.keys())

for key in sorted_keys:
    chunk = diffusion.chunks.get(key)
    crust_chunk = crust.chunks.get(key)
    if not crust_chunk.any():
        continue

    # Add nodes
    shape_x, shape_y, shape_z = chunk.shape[0] + 1, chunk.shape[1] + 1, chunk.shape[2] + 1
    nodes[key] = np.zeros((shape_x, shape_y, shape_z, 3), dtype=int)
    crust_chunk = crust_chunk.to_array()
    for i, i_ in enumerate(nodes[key][:-2]):
        for j, j_ in enumerate(nodes[key][i, :-2]):
            for k, k_ in enumerate(nodes[key][j, :-2]):
                if not crust_chunk[i][j][k]:
                    continue
                nodes[key][i][j][k] = g.add_nodes(3)

for key in sorted_keys:
    if not crust.chunks.get(key).any():
        continue

    # Copy nodes
    set_x = tuple(np.array(key) + (1, 0, 0)) in nodes
    set_y = tuple(np.array(key) + (0, 1, 0)) in nodes
    set_z = tuple(np.array(key) + (0, 0, 1)) in nodes
    if set_x:
        nodes[key][-1] = nodes[tuple(np.array(key) + (1, 0, 0))][0]
    if set_y:
        nodes[key][:, -1] = nodes[tuple(np.array(key) + (0, 1, 0))][:][0]
    if set_z:
        nodes[key][:, :, -1] = nodes[tuple(np.array(key) + (0, 0, 1))][:][:][0]

for key in nodes.keys():
    chunk = diffusion.chunks.get(key)
    crust_chunk = crust.chunks.get(key).to_array()
    # Add edges
    capacities = chunk.to_array()
    for i, i_ in enumerate(nodes[key][:-2]):
        for j, j_ in enumerate(nodes[key][i, :-2]):
            for k, k_ in enumerate(nodes[key][j, :-2]):
                cap = capacities[i][j][k]
                if not crust_chunk[i][j][k]:
                    continue
                n = nodes[key][i][j][k]
                g.add_edge(n[0], n[1], cap, cap)
                g.add_edge(n[0], n[2], cap, cap)
                g.add_edge(n[1], n[2], cap, cap)
                n1 = nodes[key][i + 1][j][k]
                if not n1.any():
                    nodes[key][i + 1][j][k] = g.add_nodes(3)
                    n1 = nodes[key][i + 1][j][k]
                g.add_edge(n[0], n1[1], cap, cap)
                g.add_edge(n[2], n1[1], cap, cap)
                n2 = nodes[key][i][j + 1][k]
                if not n2.any():
                    nodes[key][i][j + 1][k] = g.add_nodes(3)
                    n2 = nodes[key][i][j + 1][k]
                g.add_edge(n[0], n2[2], cap, cap)
                g.add_edge(n[1], n2[2], cap, cap)
                g.add_edge(n2[2], n1[1], cap, cap)
                n3 = nodes[key][i][j][k + 1]
                if not n3.any():
                    nodes[key][i][j][k + 1] = g.add_nodes(3)
                    n3 = nodes[key][i][j][k + 1]
                g.add_edge(n[1], n3[0], cap, cap)
                g.add_edge(n[2], n3[0], cap, cap)
                g.add_edge(n1[1], n3[0], cap, cap)
                g.add_edge(n2[2], n3[0], cap, cap)

flow = g.maxflow()

surface = {}
for key in nodes.keys():
    n = nodes[key]
    surface[key] = []
    for i, i_ in enumerate(n[:-1]):
        for j, j_ in enumerate(n[i, :-1]):
            for k, k_ in enumerate(n[j, :-1]):
                node_ids = np.array(list(n[i][j][k]) + [n[i + 1][j][k][1]] + [n[i][j + 1][k][2]] + [n[i][j][k + 1][0]])
                segs = g.get_grid_segments(node_ids)
                if not segs.all() and segs.any():
                    surface[key].append((i, j, k))

complete_surface = []
for key in surface.keys():
    if not surface[key]:
        continue
    offset = np.array(key)*diffusion.chunk_size
    complete_surface.append(np.array(surface[key]) + offset)
complete_surface = np.array(complete_surface)

ren = VoxelRender()
fig = ren.make_figure()
if model is not None:
    fig.add_trace(CloudRender().make_scatter(complete_surface, marker=dict(size=0.45), mode="text+markers", name="Model"))
fig.update_layout(showlegend=True)
fig.show()
