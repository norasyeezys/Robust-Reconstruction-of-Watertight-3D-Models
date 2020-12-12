from typing import Sequence, Tuple

import numpy as np
import plotly.graph_objects as go
import tqdm

from model_mesh import MeshModelLoader
from utils import merge_default


class CloudRender:

    def __init__(self, flip_zy=True):
        self.flip_zy = flip_zy

    def _unwrap(self, pts: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        x, y, z = pts.T
        if self.flip_zy:
            return x, z, y
        return x, y, z

    def make_scatter(self, pts: np.ndarray, **kwargs):
        merge_default(kwargs, mode='markers')
        x, y, z = self._unwrap(pts)
        return go.Scatter3d(x=x, y=y, z=z, **kwargs)

    def make_figure(self, **kwargs) -> go.Figure:
        fig = go.Figure()
        camera = dict(
            up=dict(x=0, y=1, z=0)
        )
        fig.update_layout(
            yaxis=dict(scaleanchor="x", scaleratio=1),
            scene=dict(
                aspectmode='data',
                xaxis_title='X',
                yaxis_title='Z' if self.flip_zy else "Y",
                zaxis_title='Y' if self.flip_zy else "Z",
                camera=camera,
                dragmode='turntable'
            ),
            scene_camera=camera
        )
        return fig

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