import numpy as np
import enum
from data.chunks import ChunkGrid, ChunkFace
from mathlib import Vec3i, Vec3f
from typing import Tuple, Sequence, List, Set
import torch
from pytorch3d.structures import Meshes

NodeIndex = Tuple[Vec3i, ChunkFace]


class Edge(enum.IntEnum):
    NORTH = 0
    SOUTH = 1
    TOP = 2
    BOTTOM = 3
    EAST = 4
    WEST = 5

    def flip(self) -> "Edge":
        return Edge((self // 2) * 2 + ((self + 1) % 2))


class PolyMesh:
    def __init__(self):
        self.vertices = {}
        self.num_verts = 0
        self.faces = []

    def add_vertex(self, v: Vec3f) -> int:
        if tuple(v) in self.vertices:
            return self.vertices[tuple(v)]
        else:
            self.vertices[tuple(v)] = self.num_verts
            self.num_verts += 1
            return self.num_verts - 1

    def get_vertex_array(self) -> np.array:
        vertices = np.zeros((len(self.vertices), 3), dtype=float)
        for v in self.vertices.keys():
            vertices[self.vertices[v]] = np.array(v)
        return vertices

    def get_vertex_list(self) -> list:
        vertices = [[] for i in self.vertices.keys()]
        for v in self.vertices.keys():
            vertices[self.vertices[v]] = list(v)
        return vertices


class MeshExtraction:
    def __init__(self, segment0: ChunkGrid[np.bool], segment1: ChunkGrid[np.bool], segments: np.ndarray,
                 nodes_index: dict):
        self.segment0 = segment0
        self.segment1 = segment1
        self.s_opt = segment0 & segment1
        self.segments = segments
        self.nodes_index = nodes_index
        self.mesh = PolyMesh()

    def extract_mesh(self):
        block = self.get_block(self.get_first_block())
        block_num = 0
        invalid_faces = 0
        while block is not None:
            if not self.make_face(block):
                print(block)
                invalid_faces += 1
            next_block_pos = self.get_next_block(block[0])
            if next_block_pos is not None:
                block = self.get_block(next_block_pos)
            else:
                break
            block_num += 1
        print('block num ', block_num)
        print('invalid faces ', invalid_faces)
        return self.mesh

    def make_face(self, block: np.ndarray):
        starting_voxel, current_edge = self.get_starting_edge(block[0])
        current_voxel, next_voxel = starting_voxel, -1
        face = []
        while starting_voxel != next_voxel:
            self.mesh.add_vertex(block[current_voxel])
            face.append(self.mesh.add_vertex(block[current_voxel]))
            cut_edges = self.get_cut_edges(current_voxel, self.get_nodes(block[current_voxel]))
            next_edge = set(cut_edges) - {current_edge}
            assert next_edge, "No adjacent cut edge found."
            next_edge = next_edge.pop()
            for i, v in enumerate(block):
                if i == current_voxel:
                    continue
                nodes = self.get_nodes(v)
                if nodes is None:
                    continue
                edges = self.get_cut_edges(i, nodes)
                if next_edge in edges:
                    next_voxel = i
                    current_voxel = next_voxel
                    current_edge = next_edge
                    break

        if len(face) >= 3:
            self.mesh.faces.append(face)
            return True
        else:
            return False

    def get_starting_edge(self, start_pos: Vec3i) -> (int, tuple):
        block = self.get_block(start_pos)
        for i, pos in enumerate(block):
            if self.s_opt.get_value(pos):
                cut_edges = self.get_cut_edges(i, self.get_nodes(pos))
                if len(cut_edges) < 2:
                    continue
                assert len(cut_edges) == 2, "Cut edges must be 2, but is " + str(len(cut_edges))
                return i, cut_edges[0]
        raise RuntimeError("No starting cut edge found.")

    def get_nodes(self, pos: Vec3i) -> np.ndarray:
        indices = []
        for i in range(6):
            index = self.get_node(tuple(pos), ChunkFace(i))
            if index in self.nodes_index:
                indices.append(index)
        if len(indices) == 6:
            return np.array([self.nodes_index[i] for i in indices])
        else:
            print("pos: ", pos, "num nodes: ", len(indices))

    def get_cut_edges(self, block_id, nodes: np.ndarray) -> tuple:
        cut_edges = []
        edges = self.block_idx_to_edges(block_id)
        for e in edges:
            n = self.block_edge_to_nodes(block_id, e, nodes)
            if self.segments[n[0]] != self.segments[n[1]]:
                cut_edges.append(e)
        assert len(cut_edges) <= 2, "Each voxel should have at most 2 cut edges."
        return tuple(cut_edges)

    def get_first_block(self) -> Vec3i:
        for c, chunk in self.s_opt.chunks.items():
            if not chunk.any():
                continue
            for pos_x, x in enumerate(chunk.to_array()):
                for pos_y, y in enumerate(x):
                    for pos_z, z in enumerate(y):
                        pos = np.array((pos_x, pos_y, pos_z)) + np.array(c) * self.s_opt.chunk_size
                        if self.has_face(pos):
                            return pos
        raise RuntimeError("No starting block can be found.")

    def get_next_block(self, start_pos: Vec3i) -> Vec3i:
        inner_pos = np.mod(start_pos, self.s_opt.chunk_size)
        chunk = self.s_opt.chunk_at_pos(start_pos)
        if tuple(inner_pos) is not (self.s_opt.chunk_size - 1,) * 3:
            if inner_pos[2] < self.s_opt.chunk_size - 1:
                for pos_z, z in enumerate(chunk.to_array()[inner_pos[0], inner_pos[1], inner_pos[2] + 1:]):
                    pos = (inner_pos[0], inner_pos[1], pos_z + inner_pos[2] + 1) + np.array(
                        chunk.index) * self.s_opt.chunk_size
                    if self.has_face(pos):
                        return pos
            if inner_pos[1] < self.s_opt.chunk_size - 1:
                for pos_y, y in enumerate(chunk.to_array()[inner_pos[0], inner_pos[1] + 1:]):
                    for pos_z, z in enumerate(y):
                        pos = (inner_pos[0], pos_y + inner_pos[1] + 1, pos_z) + np.array(
                            chunk.index) * self.s_opt.chunk_size
                        if self.has_face(pos):
                            return pos
            if inner_pos[0] < self.s_opt.chunk_size - 1:
                for pos_x, x in enumerate(chunk.to_array()[inner_pos[0] + 1:]):
                    for pos_y, y in enumerate(x):
                        for pos_z, z in enumerate(y):
                            pos = (pos_x + inner_pos[0] + 1, pos_y, pos_z) + np.array(
                                chunk.index) * self.s_opt.chunk_size
                            if self.has_face(pos):
                                return pos
        start_iter = False
        for c, c_ in self.s_opt.chunks.items():
            if c == tuple(chunk.index):
                start_iter = True
                continue
            elif not start_iter:
                continue
            if not c_.any():
                continue
            for pos_x, x in enumerate(chunk.to_array()):
                for pos_y, y in enumerate(x):
                    for pos_z, z in enumerate(y):
                        pos = np.array((pos_x, pos_y, pos_z)) + np.array(c) * self.s_opt.chunk_size
                        if self.has_face(pos):
                            return pos

    def has_face(self, pos: Vec3i):
        block = self.get_block(pos)
        count = 0
        for i, p in enumerate(block):
            if not self.s_opt.get_value(p):
                continue
            nodes = self.get_nodes(p)
            if nodes is not None and (len(self.get_cut_edges(i, nodes)) == 2):
                count += 1
        if count >= 3:
            return True
        else:
            return False

    def get_block(self, pos: Vec3i):
        idx = np.array(((0, 0, 0), (0, 0, 1), (0, 1, 0), (0, 1, 1), (1, 0, 0), (1, 0, 1), (1, 1, 0), (1, 1, 1)))
        return idx + pos

    def block_idx_to_edges(self, idx: int) -> Tuple[Edge, Edge, Edge]:
        """

        :param idx: Index of the voxel in the 2x2x2 block. Can be 0 to 7.
        :return: Edges adjacent to the center corner of the block.
        """
        idx_to_edges = {
            0: (Edge.SOUTH, Edge.BOTTOM, Edge.WEST),
            1: (Edge.SOUTH, Edge.BOTTOM, Edge.EAST),
            2: (Edge.SOUTH, Edge.TOP, Edge.WEST),
            3: (Edge.SOUTH, Edge.TOP, Edge.EAST),
            4: (Edge.NORTH, Edge.BOTTOM, Edge.WEST),
            5: (Edge.NORTH, Edge.BOTTOM, Edge.EAST),
            6: (Edge.NORTH, Edge.TOP, Edge.WEST),
            7: (Edge.NORTH, Edge.TOP, Edge.EAST)
        }
        assert idx in idx_to_edges, "Invalid block index."
        return idx_to_edges[idx]

    def block_edge_to_nodes(self, block_idx: int, edge: Edge, nodes: np.ndarray) -> tuple:
        edges = self.block_idx_to_edges(block_idx)
        edges = set(edges) - {edge}
        return nodes[edges.pop().flip()], nodes[edges.pop().flip()]

    def smooth(self, vertices: np.ndarray, faces: np.ndarray, diffusion: ChunkGrid[float], original_mesh: Meshes,
                max_iteration=50):
        assert max_iteration > -1
        change = True
        iteration = 0
        loss_mesh = original_mesh.clone()
        smooth_verts = loss_mesh.verts_packed().clone()
        neighbors = self.compute_neighbors(vertices, faces)
        neighbor_len = torch.IntTensor([len(neighbors[i]) for i in range(len(vertices))])
        neighbor_valences = torch.FloatTensor(
            [sum([1 / neighbor_len[n] for n in neighbors[i]]) for i in range(len(vertices))])
        d = 1 + 1 / neighbor_len * neighbor_valences

        while change and iteration < max_iteration:
            iteration += 1
            print(iteration)
            change = False

            for i in range(2):
                with torch.no_grad():
                    L = loss_mesh.laplacian_packed()
                loss = L.mm(loss_mesh.verts_packed())
                if i == 0:
                    loss_mesh = Meshes([loss], loss_mesh.faces_list())

            # new_vals = smooth_verts - (1/d).unsqueeze(1) * loss
            # difference = torch.sqrt(torch.sum(torch.pow(original_mesh.verts_packed() - new_vals, 2), dim=1))

            for i, v in enumerate(vertices):
                new_val = smooth_verts[i] - (1 / d[i] * loss[i])
                difference = torch.dist(original_mesh.verts_packed()[i], new_val)
                if difference < 1 + diffusion.get_value(vertices[i]):
                    smooth_verts[i] = new_val
                    change = True

            loss_mesh = Meshes([smooth_verts], original_mesh.faces_list())
        return smooth_verts

    def compute_neighbors(self, vertices: np.ndarray, faces: np.ndarray) -> List[Set]:
        neighbors = [set() for i in vertices]
        for face in faces:
            for v in face:
                neighbors[v].update(face)
        for v, s in enumerate(neighbors):
            s.remove(v)
        return neighbors

    def make_triangles(self):
        triangles = []
        for f in self.mesh.faces:
            if len(f) == 3:
                triangles.append(f)
                continue
            for i in range(len(f) - 2):
                triangles.append([f[0], f[i + 1], f[i + 2]])
        return np.array(triangles)

    def make_triangles_list(self):
        triangles = []
        for f in self.mesh.faces:
            if len(f) == 3:
                triangles.append(f)
                continue
            for i in range(len(f) - 2):
                triangles.append([f[0], f[i + 1], f[i + 2]])
        return triangles

    def get_node(self, pos: Vec3i, face: ChunkFace) -> NodeIndex:
        """Basically forces to have only positive-direction faces"""
        if face % 2 == 0:
            return pos, face
        else:
            return tuple(np.add(pos, face.direction(), dtype=int)), face.flip()

    def to_voxel(self, nodeIndex: NodeIndex) -> Sequence[Vec3i]:
        pos, face = nodeIndex
        return [
            pos,
            np.asarray(face.direction()) * (face.flip() % 2) + pos
        ]

    def get_pytorch_mesh(self) -> Meshes:
        verts = torch.FloatTensor(self.mesh.get_vertex_list())
        faces_idx = torch.LongTensor(self.make_triangles_list())
        return Meshes(verts=[verts], faces=[faces_idx])
