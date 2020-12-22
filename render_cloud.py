from typing import Tuple, Optional, List

import numpy as np
import plotly.graph_objects as go

from data.chunks import ChunkGrid, Chunk
from model.model_mesh import MeshModelLoader
from utils import merge_default


class CloudRender:

    def __init__(self, flip_zy=True):
        self.flip_zy = flip_zy

    def _hovertemplate(self):
        if self.flip_zy:
            return """
            <b>x:</b> %{x}<br>
            <b>y:</b> %{z}<br>
            <b>z:</b> %{y}<br>
            """
        else:
            return """
            <b>x:</b> %{x}<br>
            <b>y:</b> %{y}<br>
            <b>z:</b> %{z}<br>
            """

    def _unwrap(self, pts: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        x, y, z = pts.T
        if self.flip_zy:
            return x, z, y
        return x, y, z

    def make_scatter(self, pts: np.ndarray, **kwargs):
        merge_default(kwargs, mode='markers', hovertemplate=self._hovertemplate())
        x, y, z = self._unwrap(pts)
        return go.Scatter3d(x=x, y=y, z=z, **kwargs)

    def make_figure(self, **kwargs) -> go.Figure:
        fig = go.Figure()
        camera = dict(
            up=dict(x=0, y=1, z=0),
            eye=dict(x=-1, y=-1, z=0.5)
        )
        yaxis = dict()
        zaxis = dict()
        if self.flip_zy:
            yaxis.setdefault("autorange", "reversed")
        fig.update_layout(
            yaxis=dict(scaleanchor="x", scaleratio=1),
            scene=dict(
                aspectmode='data',
                yaxis=yaxis,
                zaxis=zaxis,
                xaxis_title='X',
                yaxis_title='Z' if self.flip_zy else "Y",
                zaxis_title='Y' if self.flip_zy else "Z",
                camera=camera,
                dragmode='turntable'
            ),
            scene_camera=camera
        )
        return fig

    def make_value_scatter(self, grid: ChunkGrid, mask: ChunkGrid[bool], **kwargs):

        points: List[np.ndarray] = []
        values: List[np.ndarray] = []
        for m in mask.chunks:  # type: Chunk
            c: Chunk = grid.chunks.get(m.index, None)
            if c.is_array() and c.any():
                p = np.argwhere(m.to_array())
                v = c.to_array()[tuple(p.T)]
                assert len(p) == len(v)
                points.append(p + c.position_low + 0.5)
                values.append(v)
            #
            # if len(points) > 3:
            #     break

        pts = np.concatenate(points)
        val = np.concatenate(values)

        merge_default(kwargs, marker=dict(color=val))
        return self.make_scatter(pts, **kwargs)

    def plot(self, *args: np.ndarray, size=0.5, **kwargs):
        fig = self.make_figure()
        merge_default(kwargs, mode='markers', marker=dict(size=size))
        for d in args:
            fig.add_trace(self.make_scatter(d, **kwargs))
        return fig


if __name__ == '__main__':
    data = MeshModelLoader(20000, noise=0.1).load("models/cat/cat_reference.obj")
    fig = CloudRender().plot(data)
    fig.show()
