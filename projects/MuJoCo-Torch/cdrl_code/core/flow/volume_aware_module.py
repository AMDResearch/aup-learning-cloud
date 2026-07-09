import torch as th
from typing import Tuple
from abc import ABC, abstractmethod


class VolumeAwareModule(ABC):
    """
    Define a flow like mapping, when you apply it you get volume changes(determinant) as well."""
    @abstractmethod
    def g(self, z: th.Tensor) -> Tuple[th.Tensor, th.Tensor]:
        pass

    @abstractmethod
    def f(self, x: th.Tensor) -> Tuple[th.Tensor, th.Tensor]:
        pass

    def forward(self, x: th.Tensor) -> Tuple[th.Tensor, th.Tensor]:
        return self.f(x)[0]
    
    def backward(self, z: th.Tensor) -> Tuple[th.Tensor, th.Tensor]:
        return self.g(z)[0]