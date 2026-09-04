"""GPU runtime checks for the AI-only virtual environment.

These helpers deliberately fail loudly when a GPU is requested but cannot be
loaded.  A CUDA-capable machine must not silently appear healthy while doing
inference on CPU.
"""

import traceback


def require_onnx_cuda():
    try:
        import onnxruntime as ort
        if hasattr(ort, "preload_dlls"):
            ort.preload_dlls()
        providers = ort.get_available_providers()
        if "CUDAExecutionProvider" not in providers:
            raise RuntimeError(
                "CUDAExecutionProvider is unavailable. "
                f"ORT={ort.__version__}, providers={providers}"
            )
        return ort
    except Exception as exc:
        raise RuntimeError(
            "ONNX Runtime CUDA provider failed to load. Check CUDA DLL, "
            "cuDNN, ORT GPU version, Python version and PATH.\n"
            + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        ) from exc


def require_torch_cuda():
    try:
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError(
                f"torch={torch.__version__}, torch.version.cuda={torch.version.cuda}, "
                "torch.cuda.is_available()=False"
            )
        return torch
    except Exception as exc:
        raise RuntimeError(
            "PyTorch CUDA is unavailable; YOLO cannot be allowed to fall back "
            "to CPU.\n" + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        ) from exc


def diagnose():
    ort = require_onnx_cuda()
    torch = require_torch_cuda()
    return {
        "onnxruntime": ort.__version__,
        "providers": ort.get_available_providers(),
        "ort_device": ort.get_device(),
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0),
    }
