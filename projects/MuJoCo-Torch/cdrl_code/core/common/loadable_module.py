import torch as th
from abc import ABC, abstractmethod

class LoadbleModule(ABC):
    """Abstract class to save and load from files. Just add to pytorch module, would work well. overide self.kwargs property to define necessary params"""

    @abstractmethod
    def state_dict(self):
        pass

    @abstractmethod
    def load_state_dict(self):
        pass
    
    def save_module(self, path: str):
        return th.save([self.kwargs, self.state_dict()], path)
    
    @classmethod
    def load_module(cls, path: str, device: str = 'cpu'):
        kwargs, state = th.load(path, map_location=device)
        m =  cls(**kwargs)
        m.load_state_dict(state)
        return m