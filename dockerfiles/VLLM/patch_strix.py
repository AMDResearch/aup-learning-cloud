# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# ----------------------------------------------------------------------------
# gfx1151 (Strix Halo / RDNA 3.5) enablement patches for vLLM.
#
# Each block in `patch_vllm()` is a workaround for a specific upstream gap.
# Re-check against vLLM HEAD periodically and delete blocks whose sentinel no
# longer matches — that means upstream landed real support and we don't need
# the patch anymore.
#
# Run from inside a `git clone https://github.com/vllm-project/vllm.git`
# (current working directory must be the vLLM repo root) BEFORE building the
# wheel. Idempotent — each block checks for its sentinel before applying.
# ----------------------------------------------------------------------------

import re
import site
from pathlib import Path


def patch_vllm():
    print("Applying gfx1151 (Strix Halo) enablement patches to vLLM...")

    # ------------------------------------------------------------------------
    # GAP 1 — amdsmi does not work on Strix Halo APUs in containers.
    # vLLM unconditionally imports it from vllm/platforms/__init__.py. Stub
    # the calls until the runtime exists for APUs.
    # ------------------------------------------------------------------------
    p_init = Path("vllm/platforms/__init__.py")
    if p_init.exists():
        txt = p_init.read_text()
        txt = txt.replace("import amdsmi", "# import amdsmi")
        txt = re.sub(
            r"if len\(amdsmi\.amdsmi_get_processor_handles\(\)\) > 0:",
            "if True:",
            txt,
        )
        txt = txt.replace("amdsmi.amdsmi_init()", "pass")
        txt = txt.replace("amdsmi.amdsmi_shut_down()", "pass")
        p_init.write_text(txt)
        print(" -> Patched vllm/platforms/__init__.py (stubbed amdsmi)")

    # ------------------------------------------------------------------------
    # GAP 2 — vLLM's _get_gcn_arch() reads /opt/rocm/bin/rocminfo which can
    # be missing or report the wrong arch on a Strix Halo APU; also MagicMock
    # any remaining `amdsmi` reference inside rocm.py so it doesn't crash
    # when `import amdsmi` was stubbed in GAP 1.
    # ------------------------------------------------------------------------
    p_rocm_plat = Path("vllm/platforms/rocm.py")
    if p_rocm_plat.exists():
        txt = p_rocm_plat.read_text()
        if 'sys.modules["amdsmi"] = MagicMock()' not in txt:
            header = 'import sys\nfrom unittest.mock import MagicMock\nsys.modules["amdsmi"] = MagicMock()\n'
            txt = header + txt
        if 'def _get_gcn_arch() -> str:\n    return "gfx1151"' not in txt:
            txt = txt.replace(
                "def _get_gcn_arch() -> str:",
                'def _get_gcn_arch() -> str:\n    return "gfx1151"\n\ndef _old_get_gcn_arch() -> str:',
            )
        p_rocm_plat.write_text(txt)
        print(" -> Patched vllm/platforms/rocm.py (MagicMock amdsmi + forced gfx1151)")

    # ------------------------------------------------------------------------
    # GAP 3 — vLLM's AITER feature gates only recognise `on_mi3xx()` (CDNA).
    # Teach them about `on_gfx1x()` (RDNA 3/3.5) AND opt-out of two AITER
    # paths that emit CDNA-only ISA on gfx1x today:
    #   * is_linear_fp8_enabled : AITER FP8 linear -> emits v_cvt_pk_fp8_f32
    #   * is_fused_moe_enabled  : AITER fused MoE -> emits dpp_mov / row_bcast
    # When upstream AITER lands proper RDNA fallbacks we can drop these.
    # ------------------------------------------------------------------------
    p_aiter = Path("vllm/_aiter_ops.py")
    if p_aiter.exists():
        txt = p_aiter.read_text()
        if "from vllm.platforms.rocm import on_gfx1x" not in txt:
            txt = txt.replace(
                "from vllm.platforms import current_platform",
                "from vllm.platforms import current_platform\nfrom vllm.platforms.rocm import on_gfx1x",
            )
        if "or on_gfx1x()" not in txt:
            txt = txt.replace("import on_mi3xx", "import on_mi3xx, on_gfx1x")
            txt = txt.replace("on_mi3xx()", "(on_mi3xx() or on_gfx1x())")
        if "is_linear_fp8_enabled" in txt:
            txt = re.sub(
                r"(def is_linear_fp8_enabled.*?:\n\s+return) (.*?)\n",
                r"\1 False\n",
                txt,
                count=1,
                flags=re.DOTALL,
            )
        if "is_fused_moe_enabled" in txt:
            txt = re.sub(
                r"(def is_fused_moe_enabled.*?:\n\s+return) (cls\._AITER_ENABLED and cls\._FMOE_ENABLED)\n",
                r'\1 \2 and not getattr(on_gfx1x, "__call__", lambda: False)()\n',
                txt,
                count=1,
                flags=re.DOTALL,
            )
        p_aiter.write_text(txt)
        print(" -> Patched vllm/_aiter_ops.py (gfx1x support; FP8-linear + AITER-MoE disabled)")

    # ------------------------------------------------------------------------
    # GAP 4 — Same arch-gate fix in the v1 attention backend.
    # ------------------------------------------------------------------------
    p_fa = Path("vllm/v1/attention/backends/rocm_aiter_fa.py")
    if p_fa.exists():
        txt = p_fa.read_text()
        if "on_gfx1x" not in txt:
            txt = txt.replace(
                "from vllm.platforms.rocm import on_mi3xx",
                "from vllm.platforms.rocm import on_mi3xx, on_gfx1x",
            )
            txt = txt.replace("on_mi3xx()", "(on_mi3xx() or on_gfx1x())")
            p_fa.write_text(txt)
            print(" -> Patched vllm/v1/attention/backends/rocm_aiter_fa.py (gfx1x support)")

    # ------------------------------------------------------------------------
    # GAP 5 — VLLM_ROCM_USE_AITER_MOE can force the AITER MoE path even when
    # the feature gate says no. On gfx1x that ends up scheduling CDNA-only
    # kernels (see GAP 3). Hard-block the override here.
    # ------------------------------------------------------------------------
    p_unquant = Path("vllm/model_executor/layers/fused_moe/oracle/unquantized.py")
    if p_unquant.exists():
        txt = p_unquant.read_text()
        if "from vllm.platforms.rocm import on_gfx1x" not in txt:
            txt = txt.replace(
                'if envs.is_set("VLLM_ROCM_USE_AITER")',
                'from vllm.platforms.rocm import on_gfx1x\n    if envs.is_set("VLLM_ROCM_USE_AITER")',
            )
            txt = txt.replace(
                "if not envs.VLLM_ROCM_USE_AITER or not envs.VLLM_ROCM_USE_AITER_MOE:",
                'if getattr(on_gfx1x, "__call__", lambda: False)() '
                "or not envs.VLLM_ROCM_USE_AITER "
                "or not envs.VLLM_ROCM_USE_AITER_MOE:",
            )
            p_unquant.write_text(txt)
            print(" -> Patched fused_moe/oracle/unquantized.py (blocked AITER-MoE override on gfx1x)")

    # ------------------------------------------------------------------------
    # GAP 6 — IrOpPriorityConfig prefers the AITER rms_norm impl, which hangs
    # under CUDA-graph capture on gfx1x. Fall back to the default order.
    # ------------------------------------------------------------------------
    p_rocm = Path("vllm/platforms/rocm.py")
    if p_rocm.exists():
        txt = p_rocm.read_text()
        if 'rms_norm = ["aiter"] + default' in txt and "on_gfx1x()" not in txt.split('rms_norm = ["aiter"]')[1][:200]:
            txt = txt.replace(
                'rms_norm = ["aiter"] + default',
                'rms_norm = ["aiter"] + default if not on_gfx1x() else default',
            )
            p_rocm.write_text(txt)
            print(" -> Patched vllm/platforms/rocm.py (IrOpPriorityConfig rms_norm bypassed on gfx1x)")

    # ------------------------------------------------------------------------
    # GAP 7 — rocm_aiter_fusion.py registers several pm replacement patterns
    # that happen to share keys post-rewrite, causing PatternMatcher to throw
    # `duplicate pattern` at compile time. `skip_duplicates=True` is benign
    # on CDNA too; upstream just hasn't set it.
    # ------------------------------------------------------------------------
    p_fusion = Path("vllm/compilation/passes/fusion/rocm_aiter_fusion.py")
    if p_fusion.exists():
        txt = p_fusion.read_text()
        if "skip_duplicates=True" not in txt:
            txt = re.sub(
                r"(pm\.register_replacement\s*\((?:(?!\bpm\.register_replacement\b).)*?)pm_pass(\s*[\),])",
                r"\1pm_pass, skip_duplicates=True\2",
                txt,
                flags=re.DOTALL,
            )
            p_fusion.write_text(txt)
            print(" -> Patched rocm_aiter_fusion.py (skip_duplicates=True)")

    # ------------------------------------------------------------------------
    # GAP 8 — AITER's JIT builds .so modules into ~/.aiter/jit/ but Python
    # imports `aiter.jit.<mod>` from the installed package dir. Extend the
    # package's __path__ so JIT artefacts are importable.
    # ------------------------------------------------------------------------
    jit_path_fix = """
# PATCHED: JIT cache path for gfx1151 enablement.
# aiter's JIT compiles .so modules into ~/.aiter/jit/ but importlib looks
# in the installed package directory. Add the JIT cache to __path__.
import os as _os
_jit_cache = _os.path.join(_os.path.expanduser("~"), ".aiter", "jit")
if _os.path.isdir(_jit_cache) and _jit_cache not in __path__:
    __path__.append(_jit_cache)
"""
    for sp in site.getsitepackages():
        aiter_jit_init = Path(sp) / "aiter/jit/__init__.py"
        if aiter_jit_init.exists():
            txt = aiter_jit_init.read_text()
            if "# PATCHED: JIT cache path" not in txt:
                aiter_jit_init.write_text(txt + jit_path_fix)
                print(f" -> Patched {aiter_jit_init} (JIT cache added to __path__)")

    # ------------------------------------------------------------------------
    # GAP 9 — flash-attention's main_perf branch imports the AITER triton
    # kernel hard. If the AITER JIT trips, all of flash_attn fails to load
    # and vLLM falls off the TRITON_ATTN fallback too. Soft-import so
    # TRITON_ATTN keeps working even if ROCM_ATTN doesn't.
    # ------------------------------------------------------------------------
    hard_import_bare = (
        "from aiter.ops.triton._triton_kernels.flash_attn_triton_amd import flash_attn_2 as flash_attn_gpu"
    )

    def _patch_flash_interface(fa_iface):
        txt = fa_iface.read_text()
        if hard_import_bare not in txt or "except (ImportError" in txt:
            return False
        m = re.search(r"^( *)" + re.escape(hard_import_bare), txt, re.MULTILINE)
        if not m:
            return False
        indent = m.group(1)
        original_line = indent + hard_import_bare
        soft_import = (
            f"{indent}try:\n"
            f"{indent}    {hard_import_bare}\n"
            f"{indent}except (ImportError, KeyError, ModuleNotFoundError):\n"
            f"{indent}    flash_attn_gpu = None"
        )
        txt = txt.replace(original_line, soft_import)
        fa_iface.write_text(txt)
        print(f" -> Patched {fa_iface} (aiter import made resilient)")
        return True

    for sp in site.getsitepackages():
        for fa_egg in Path(sp).glob("flash_attn*.egg"):
            fa_iface = fa_egg / "flash_attn/flash_attn_interface.py"
            if fa_iface.exists():
                _patch_flash_interface(fa_iface)
        fa_iface = Path(sp) / "flash_attn/flash_attn_interface.py"
        if fa_iface.exists():
            _patch_flash_interface(fa_iface)

    # ------------------------------------------------------------------------
    # GAP 10 — vLLM caps the MXFP4 Triton MoE kernels at compute capability
    # < (11, 0), which excludes RDNA 3.5 (cap = 11.5). Lift the ceiling to
    # 12.0 so gfx1151 is in scope.
    # ------------------------------------------------------------------------
    p_triton_moe = Path("vllm/model_executor/layers/fused_moe/experts/gpt_oss_triton_kernels_moe.py")
    if p_triton_moe.exists():
        txt = p_triton_moe.read_text()
        if "cap.minor) < (11, 0)" in txt:
            txt = txt.replace("cap.minor) < (11, 0)", "cap.minor) < (12, 0)")
            p_triton_moe.write_text(txt)
            print(f" -> Patched {p_triton_moe} (Triton MoE cap 11.0 -> 12.0)")

    # ------------------------------------------------------------------------
    # GAP 11 — ROCm 7.12 nightly clamps APU total VRAM to 50 % of GTT to
    # prevent OOM kernel panics on headless hosts (ROCM-21812). vLLM's memory
    # profiler reads that clamped total and refuses to load large models.
    # Proxy torch.cuda.{mem_get_info,get_device_properties} so they return
    # the actual GTT limits minus an 8 GiB OS safety margin.
    # Remove once ROCm/rocm-systems#5113 lands in the nightly tarballs.
    # ------------------------------------------------------------------------
    if p_rocm.exists():
        txt = p_rocm.read_text()
        if "_patched_mem_info" not in txt:
            mem_patch = """
# --- ROCM-21812 GTT VRAM dynamic margin patch ---
import torch
import glob
import os

try:
    _orig_mem_info = torch.cuda.mem_get_info
    _orig_get_dev_prop = torch.cuda.get_device_properties

    class MockCudaDeviceProperties:
        def __init__(self, prop, override_total):
            self._prop = prop
            self.total_memory = override_total

        def __getattr__(self, name):
            return getattr(self._prop, name)

        def __dir__(self):
            return dir(self._prop)

    def _patched_mem_info(device=None):
        free, total = _orig_mem_info(device)
        try:
            if total < 70 * 1024**3:
                drm_cards = glob.glob('/sys/class/drm/card*/device/mem_info_gtt_total')
                if drm_cards:
                    card_dir = os.path.dirname(drm_cards[0])
                    with open(os.path.join(card_dir, 'mem_info_gtt_total'), 'r') as f:
                        gtt_total = int(f.read().strip())
                    with open(os.path.join(card_dir, 'mem_info_gtt_used'), 'r') as f:
                        gtt_used = int(f.read().strip())
                    safe_ceiling = gtt_total - (8 * 1024**3)
                    real_total = safe_ceiling
                    real_free = max(0, safe_ceiling - gtt_used)
                    total = max(total, real_total)
                    free = real_free
        except Exception:
            pass
        return int(free), int(total)

    def _patched_get_dev_prop(device=None):
        prop = _orig_get_dev_prop(device)
        free, total = _patched_mem_info(device)
        if hasattr(prop, 'total_memory') and prop.total_memory < total:
            return MockCudaDeviceProperties(prop, total)
        return prop

    torch.cuda.mem_get_info = _patched_mem_info
    torch.cuda.get_device_properties = _patched_get_dev_prop
except Exception:
    pass
# ---
"""
            txt = mem_patch + txt
            p_rocm.write_text(txt)
            print(" -> Patched vllm/platforms/rocm.py (ROCM-21812 GTT VRAM margin)")

    # ------------------------------------------------------------------------
    # GAP — csrc/spinloop.cpp #include <mwaitxintrin.h> directly. ROCm 7.12
    # ships Clang 22, whose mwaitxintrin.h was hardened to refuse direct
    # inclusion:
    #     /opt/rocm/.../clang/22/include/mwaitxintrin.h:11:2:
    #         error: "Never use <mwaitxintrin.h> directly;
    #                 include <x86intrin.h> instead."
    # The umbrella <x86intrin.h> exposes the same _mm_monitorx / _mm_mwaitx
    # intrinsics when -mmwaitx is set, so swap the include. Drop this once
    # vLLM upstream switches to <x86intrin.h>.
    # ------------------------------------------------------------------------
    p_spin = Path("csrc/spinloop.cpp")
    if p_spin.exists():
        txt = p_spin.read_text()
        if "<mwaitxintrin.h>" in txt:
            txt = txt.replace("<mwaitxintrin.h>", "<x86intrin.h>")
            p_spin.write_text(txt)
            print(" -> Patched csrc/spinloop.cpp (mwaitxintrin.h -> x86intrin.h)")

    print("Successfully patched vLLM for gfx1151.")


if __name__ == "__main__":
    patch_vllm()
