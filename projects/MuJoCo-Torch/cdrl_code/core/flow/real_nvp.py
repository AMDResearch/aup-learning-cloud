from typing import Tuple
from torch import nn
import torch as th
from core.flow.volume_aware_module import VolumeAwareModule
from core.common.loadable_module import LoadbleModule

class RealNvp(VolumeAwareModule, th.nn.Module, LoadbleModule):
    """Define a simple real nvp module, does not include the prior."""

    def __init__(self, var_count, transform_count, conditional_param_count=0, hidden_size=256, dtype="float64"):
        super(RealNvp, self).__init__()
        assert transform_count % 2 == 0
        self.dtype = getattr(th, dtype)
        self.var_count = var_count
        self.conditional_param_count = conditional_param_count
        self.dim = self.var_count + self.conditional_param_count
        self.transform_count = transform_count
        self.hidden_size = hidden_size
        self.kwargs = {'var_count': var_count, 'transform_count': transform_count, "conditional_param_count": conditional_param_count, "hidden_size": hidden_size, "dtype": dtype}
        self.mask = nn.Parameter(self._get_masks(transform_count), requires_grad=False)
        self.t = self._get_t()
        self.s = self._get_s()

    def f(self, x: th.Tensor) -> Tuple[th.Tensor, th.Tensor]:
        y =  x[:, self.var_count:]
        x =  x[:, :self.var_count]
        log_det_J, z = th.zeros(x.shape[0], device=x.device).float(), x
        for i in reversed(range(len(self.t))):
            z_ = self.mask[i] * z
            s = self.s[i](th.cat([z_, y], dim=1)) * (1-self.mask[i])
            t = self.t[i](th.cat([z_, y], dim=1)) * (1-self.mask[i])
            z = (1 - self.mask[i]) * (z - t) * th.exp(-s) + z_
            log_det_J -= th.sum(s, dim=1)
        return th.concat([z, y], dim=1), log_det_J

    def g(self, z):
        y =  z[:, self.var_count:]
        z =  z[:, :self.var_count]
        log_det_J, x = th.zeros(z.shape[0], device=z.device).float(), z
        for i in range(len(self.t)):
            x_ = x*self.mask[i]
            s = self.s[i](th.cat([x_, y], dim=1))*(1 - self.mask[i])
            t = self.t[i](th.cat([x_, y], dim=1))*(1 - self.mask[i])
            x = x_ + (1 - self.mask[i]) * (x * th.exp(s) + t)
            log_det_J = th.sum(s, dim=1)
        return th.concat([x, y], dim=1), log_det_J

    def _get_nets(self):
        return nn.Sequential(
            nn.Linear(self.dim, self.hidden_size, dtype=self.dtype),
            nn.LeakyReLU(),
            nn.Linear(self.hidden_size, self.hidden_size, dtype=self.dtype),
            nn.LeakyReLU(),
            nn.Linear(self.hidden_size, self.var_count, dtype=self.dtype),
            nn.Tanh()
        )

    def _get_nett(self):
        return nn.Sequential(
            nn.Linear(self.dim, self.hidden_size, dtype=self.dtype),
            nn.LeakyReLU(),
            nn.Linear(self.hidden_size, self.hidden_size, dtype=self.dtype),
            nn.LeakyReLU(),
            nn.Linear(self.hidden_size, self.var_count, dtype=self.dtype),
        )


    def _get_t(self):
        return th.nn.ModuleList([self._get_nett() for _ in range(len(self.mask))])

    def _get_s(self):
        return th.nn.ModuleList([self._get_nets() for _ in range(len(self.mask))])

    def _get_masks(self, transform_count):
        mask_one = th.cat([th.ones(self.var_count//2), th.zeros(self.var_count - self.var_count//2)])
        mask_two = 1 - mask_one
        mask = th.stack([mask_one, mask_two]).repeat(transform_count//2, 1)
        return mask

    def disable_grad(self, disable=True):
        req_grad = not disable
        if req_grad:
            self.train()
        else:
            self.eval()
        for i in range(self.transform_count):
            for module in list(self.t[i]) + list(self.s[i]):
                for p in module.parameters():
                    p.requires_grad = req_grad


def test_real_nvp():
    flow = RealNvp(2, 6, 3, 256).to('cpu')
    x = th.tensor([[2, 3, 4, 5, 6], [0, 0, 0, 0, 0]]).double()
    z, logDet = flow.f(x)
    assert z.shape == (2, 5)
    assert logDet.shape == (2, )

    # save and load from file test
    save_path = "/tmp/test_model.pt"
    flow.save_module(save_path)
    flow2: RealNvp = RealNvp.load_module(save_path)
    z2, logDet2 = flow2.f(x)
    assert th.eq(z, z2).all()
    assert th.eq(logDet, logDet2).all()
