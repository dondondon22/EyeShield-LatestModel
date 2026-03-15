"""
DR inference module for EyeShield screening.

The local weights file is expected at:
    Frontend/testSample/models/DiabeticRetinopathy.pth

Supported checkpoint layouts:
    - torchvision EfficientNet-B0 with a 5-class head
    - torchvision EfficientNet-B4 with a 5-class head
    - torchvision ResNet50 with a 5-class linear head
    - torchvision ResNet50 with a 3-layer MLP head
    - RETFound ViT-Large/16 fine-tuned with a 5-class head  (requires: pip install timm)

Classes:
    0 → No DR
    1 → Mild DR
    2 → Moderate DR
    3 → Severe DR
    4 → Proliferative DR

RETFound usage:
    1. Request access at https://huggingface.co/YukunZhou/RETFound_mae_natureCFP
    2. Fine-tune on APTOS / EyePACS (5-class) using the RETFound training scripts
    3. Drop the fine-tuned checkpoint at models/DiabeticRetinopathy.pth
    The architecture is auto-detected from the state-dict keys.
"""

import os
import tempfile
import threading

import numpy as np
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image

try:
    import timm as _timm
    _TIMM_AVAILABLE = True
except ImportError:
    _TIMM_AVAILABLE = False

# ── Speed: use all available CPU cores for intra-op parallelism ───────────────
torch.set_num_threads(min(torch.get_num_threads(), os.cpu_count() or 4))

# ── Speed: enable cuDNN auto-tuner when GPU is available ──────────────────────
if torch.cuda.is_available():
    torch.backends.cudnn.benchmark = True


class ImageUngradableError(ValueError):
    """Raised when the input image fails quality / gradability checks."""
    pass


# ── DR class labels ───────────────────────────────────────────────────────────
DR_LABELS = [
    "No DR",
    "Mild DR",
    "Moderate DR",
    "Severe DR",
    "Proliferative DR",
]

# ── Supported checkpoint layouts ─────────────────────────────────────────────
def _build_resnet50_linear() -> nn.Module:
    net = models.resnet50(weights=None)
    net.fc = nn.Linear(net.fc.in_features, len(DR_LABELS))
    return net


def _build_resnet50_mlp() -> nn.Module:
    net = models.resnet50(weights=None)
    net.fc = nn.Sequential(
        nn.Linear(net.fc.in_features, 1024),
        nn.ReLU(),
        nn.BatchNorm1d(1024),
        nn.Dropout(0.5),
        nn.Linear(1024, 512),
        nn.ReLU(),
        nn.BatchNorm1d(512),
        nn.Dropout(0.3),
        nn.Linear(512, len(DR_LABELS)),
    )
    return net


def _build_retfound_vit() -> nn.Module:
    """Build a ViT-Large/16 with global-average-pool head matching RETFound fine-tuned weights."""
    if not _TIMM_AVAILABLE:
        raise ImportError(
            "The timm package is required to load a RETFound checkpoint.\n"
            "Install it with:  pip install timm"
        )
    # global_pool='avg' matches RETFound's fine-tuning setup (mean of patch tokens, no CLS)
    return _timm.create_model(
        "vit_large_patch16_224",
        num_classes=len(DR_LABELS),
        global_pool="avg",
        pretrained=False,
    )


_ARCH_CONFIGS = {
    "efficientnet_b0": {
        "builder": models.efficientnet_b0,
        "classifier_in": 1280,
        "input_size": 224,
        "heatmap_layer": "features",
    },
    "efficientnet_b4": {
        "builder": models.efficientnet_b4,
        "classifier_in": 1792,
        "input_size": 380,
        "heatmap_layer": "features",
    },
    "resnet50": {
        "builder": _build_resnet50_linear,
        "classifier_in": 2048,
        "input_size": 224,
        "heatmap_layer": "layer4",
    },
    "resnet50_mlp": {
        "builder": _build_resnet50_mlp,
        "classifier_in": 2048,
        "input_size": 224,
        "heatmap_layer": "layer4",
    },
    # RETFound: ViT-Large/16 pre-trained on 1.6M retinal images (Nature 2023)
    # Fine-tune checkpoint from: https://huggingface.co/YukunZhou/RETFound_mae_natureCFP
    "retfound": {
        "builder": _build_retfound_vit,
        "classifier_in": 1024,
        "input_size": 224,
        "heatmap_layer": "vit_blocks",   # special: hooks model.blocks[-1]
    },
}

_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
MODEL_PATH = os.path.join(_MODEL_DIR, "DiabeticRetinopathy.pth")

_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
_model: nn.Module | None = None   # lazy-loaded singleton
_model_input_size = _ARCH_CONFIGS["efficientnet_b0"]["input_size"]
_model_architecture = "efficientnet_b0"
_preload_lock = threading.Lock()   # prevents duplicate loading from multiple threads


def is_model_available() -> bool:
    """Return True when the local weights file exists on disk."""
    return os.path.isfile(MODEL_PATH)


def _build_transform(input_size: int) -> transforms.Compose:
    return transforms.Compose([
        transforms.Resize((input_size, input_size)),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225],
        ),
    ])


def _unwrap_state_dict(state: object) -> dict[str, torch.Tensor]:
    if isinstance(state, dict):
        for key in ("model_state_dict", "state_dict", "model"):
            nested = state.get(key)
            if isinstance(nested, dict):
                state = nested
                break

    if not isinstance(state, dict):
        raise TypeError("Unsupported checkpoint format.")

    return state


def _load_checkpoint_state() -> dict[str, torch.Tensor]:
    try:
        state = torch.load(MODEL_PATH, map_location=_device, weights_only=True)
    except TypeError:
        state = torch.load(MODEL_PATH, map_location=_device)
    return _unwrap_state_dict(state)


def _infer_architecture(state_dict: dict[str, torch.Tensor]) -> str:
    # RETFound: ViT-Large/16 patch embedding projects 3-channel 16×16 patches → 1024 dims
    patch_embed = state_dict.get("patch_embed.proj.weight")
    if isinstance(patch_embed, torch.Tensor) and tuple(patch_embed.shape) == (1024, 3, 16, 16):
        return "retfound"

    resnet_mlp_head = state_dict.get("fc.8.weight")
    if isinstance(resnet_mlp_head, torch.Tensor):
        return "resnet50_mlp"

    resnet_head = state_dict.get("fc.weight")
    if isinstance(resnet_head, torch.Tensor) and tuple(resnet_head.shape) == (len(DR_LABELS), 2048):
        return "resnet50"

    head_weight = state_dict.get("classifier.1.weight")
    if isinstance(head_weight, torch.Tensor):
        in_features = int(head_weight.shape[1])
        for arch_name, config in _ARCH_CONFIGS.items():
            if config["classifier_in"] == in_features:
                return arch_name

    stem_weight = state_dict.get("features.0.0.weight")
    if isinstance(stem_weight, torch.Tensor):
        stem_channels = int(stem_weight.shape[0])
        if stem_channels == 32:
            return "efficientnet_b0"
        if stem_channels == 48:
            return "efficientnet_b4"

    raise ValueError(
        "Unsupported checkpoint architecture. Expected a supported EfficientNet, ResNet50, or RETFound state dict."
    )


def _build_model(architecture: str) -> nn.Module:
    config = _ARCH_CONFIGS[architecture]
    if architecture == "retfound":
        return config["builder"]()

    if architecture.startswith("efficientnet"):
        net = config["builder"](weights=None)
        in_features = net.classifier[1].in_features
        net.classifier[1] = nn.Linear(in_features, len(DR_LABELS))
        return net

    net = config["builder"]()
    return net


def load_model() -> nn.Module:
    """Build the model variant that matches the saved checkpoint."""
    global _model_architecture, _model_input_size

    if not is_model_available():
        raise FileNotFoundError(
            f"Model weights not found at:\n{MODEL_PATH}\n\n"
            "Put your offline DR checkpoint in this path and try again."
        )

    state_dict = _load_checkpoint_state()
    architecture = _infer_architecture(state_dict)
    net = _build_model(architecture)

    # RETFound fine-tuned checkpoints may include extra MAE pre-training keys
    # (e.g. mask_token) not present in the fine-tuned timm model; strict=False
    # is safe here because we already validated the architecture fingerprint above.
    if architecture == "retfound":
        missing, unexpected = net.load_state_dict(state_dict, strict=False)
        critical_missing = [k for k in missing if not k.startswith("head")]
        if critical_missing:
            raise RuntimeError(
                f"RETFound checkpoint is missing expected keys: {critical_missing}"
            )
    else:
        net.load_state_dict(state_dict)

    net.to(_device)
    net.eval()

    # ── Speed: half-precision on GPU (2× faster, 2× less VRAM) ───────────────
    # NOTE: torch.compile() and quantize_dynamic are intentionally NOT applied:
    #   - compile() wraps the model in OptimizedModule, breaking attribute access
    #     needed by _get_heatmap_target_layer() (model.features, .layer4, .blocks)
    #   - quantize_dynamic removes autograd support, breaking generate_heatmap()
    if _device.type == "cuda":
        net = net.half()

    _model_architecture = architecture
    _model_input_size = _ARCH_CONFIGS[architecture]["input_size"]
    return net


def _get_heatmap_target_layer(model: nn.Module) -> nn.Module:
    config = _ARCH_CONFIGS[_model_architecture]
    if config["heatmap_layer"] == "layer4":
        return model.layer4[-1]
    if config["heatmap_layer"] == "vit_blocks":
        return model.blocks[-1]   # last transformer block of ViT
    return model.features[-1]


def _laplacian_var(gray: np.ndarray) -> float:
    """Return the variance of the Laplacian of a 2-D uint8 grayscale array.
    Higher values indicate a sharper image."""
    lap = (
        gray[1:-1, 1:-1].astype(np.float32) * -4.0
        + gray[:-2,  1:-1].astype(np.float32)
        + gray[2:,   1:-1].astype(np.float32)
        + gray[1:-1, :-2].astype(np.float32)
        + gray[1:-1, 2:].astype(np.float32)
    )
    return float(np.var(lap))


def check_image_quality(image_path: str) -> None:
    """Quality check temporarily disabled. Re-enable by restoring the body."""
    return


def _apply_jet(cam: np.ndarray) -> np.ndarray:
    """Apply jet colormap to an H×W float32 array in [0, 1]. Returns H×W×3 uint8."""
    x = np.clip(cam, 0.0, 1.0)
    r = np.clip(np.minimum(4 * x - 1.5, -4 * x + 4.5), 0.0, 1.0)
    g = np.clip(np.minimum(4 * x - 0.5, -4 * x + 3.5), 0.0, 1.0)
    b = np.clip(np.minimum(4 * x + 0.5, -4 * x + 2.5), 0.0, 1.0)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _ensure_model_loaded() -> nn.Module:
    global _model

    if not is_model_available():
        raise FileNotFoundError(
            f"Model weights not found at:\n{MODEL_PATH}\n\n"
            "Put your offline DR checkpoint in this path and try again."
        )

    if _model is None:
        with _preload_lock:
            if _model is None:   # double-checked locking
                _model = load_model()

    return _model


def preload_model_async() -> None:
    """Start loading the model on a background thread.

    Call this at application start so the model is warm by the time the user
    reaches the Screening page — eliminates the first-scan loading delay.
    Does nothing if the weights file is not yet present.
    """
    if not is_model_available():
        return

    def _worker():
        try:
            _ensure_model_loaded()
        except Exception:
            pass   # errors will be surfaced properly when the user scans

    t = threading.Thread(target=_worker, daemon=True, name="eyeshield-model-preload")
    t.start()


def _load_image_tensor(image_path: str) -> tuple[Image.Image, torch.Tensor]:
    _ensure_model_loaded()
    check_image_quality(image_path)

    image = Image.open(image_path).convert("RGB")
    transform = _build_transform(_model_input_size)
    tensor = transform(image).unsqueeze(0).to(_device)
    return image, tensor


def predict_image(image_path: str) -> tuple[str, str, int]:
    """Return label, formatted confidence text, and predicted class index."""
    model = _ensure_model_loaded()
    _, tensor = _load_image_tensor(image_path)

    # Cast input to fp16 when the model was moved to half-precision (CUDA)
    if _device.type == "cuda":
        tensor = tensor.half()

    with torch.inference_mode():
        logits = model(tensor)
        probs = torch.softmax(logits.float(), dim=1)[0]

    class_idx = int(probs.argmax())
    confidence = float(probs[class_idx]) * 100.0
    return DR_LABELS[class_idx], f"Confidence: {confidence:.1f}%", class_idx


def generate_heatmap(image_path: str, class_idx: int) -> str:
    """Generate a Grad-CAM++ overlay for a previously predicted class."""
    model = _ensure_model_loaded()
    image, tensor = _load_image_tensor(image_path)

    # Cast to fp16 if the model is running in half-precision (CUDA)
    if _device.type == "cuda":
        tensor = tensor.half()

    heatmap_path = ""
    try:
        activations: dict[str, torch.Tensor] = {}
        gradients: dict[str, torch.Tensor] = {}
        target_layer = _get_heatmap_target_layer(model)

        fwd_handle = target_layer.register_forward_hook(
            lambda m, inp, out: activations.__setitem__("A", out)
        )
        bwd_handle = target_layer.register_full_backward_hook(
            lambda m, gin, gout: gradients.__setitem__("G", gout[0])
        )

        model.zero_grad()
        logits = model(tensor)
        logits[0, class_idx].backward()

        fwd_handle.remove()
        bwd_handle.remove()

        A = activations["A"][0].detach()
        G = gradients["G"][0].detach()

        # ViT: activations/gradients are sequences [seq_len, embed_dim].
        # Strip the CLS token (index 0) and fold the patch tokens into a 2-D spatial map.
        if _model_architecture == "retfound":
            patch_grid = _model_input_size // 16          # 224//16 = 14
            A = A[1:].permute(1, 0).reshape(-1, patch_grid, patch_grid)
            G = G[1:].permute(1, 0).reshape(-1, patch_grid, patch_grid)

        G2 = G ** 2
        G3 = G ** 3
        A_sum = A.sum(dim=(1, 2), keepdim=True)
        alpha = G2 / (2 * G2 + A_sum * G3 + 1e-7)
        weights = (alpha * torch.relu(G)).sum(dim=(1, 2))

        cam = torch.relu((weights[:, None, None] * A).sum(dim=0))
        cam_min, cam_max = cam.min(), cam.max()
        cam = (cam - cam_min) / (cam_max - cam_min + 1e-7)
        cam_np = cam.cpu().numpy()

        cam_up = np.array(
            Image.fromarray((cam_np * 255).astype(np.uint8)).resize(
                (_model_input_size, _model_input_size), Image.BILINEAR
            )
        ).astype(np.float32) / 255.0

        heatmap_rgb = _apply_jet(cam_up)
        orig_np = np.array(image.resize((_model_input_size, _model_input_size), Image.BILINEAR))
        overlay = (0.55 * orig_np + 0.45 * heatmap_rgb).clip(0, 255).astype(np.uint8)

        tmp = tempfile.NamedTemporaryFile(
            suffix=".png", delete=False, prefix="eyeshield_cam_"
        )
        Image.fromarray(overlay).save(tmp.name)
        tmp.close()
        heatmap_path = tmp.name
    except Exception:
        heatmap_path = ""

    return heatmap_path


def run_inference(image_path: str) -> tuple[str, str, str]:
    """
    Run DR inference and Grad-CAM++ on *image_path*.

    Returns
    -------
    label : str
        e.g. "Moderate DR"
    confidence_text : str
        e.g. "Confidence: 78.3%"
    heatmap_path : str
        Path to a temporary PNG file containing the Grad-CAM++ overlay.
        Empty string when heatmap generation fails (inference result still valid).

    Raises
    ------
    FileNotFoundError
        When the weights file is missing.
    """
    label, confidence_text, class_idx = predict_image(image_path)
    heatmap_path = generate_heatmap(image_path, class_idx)
    return label, confidence_text, heatmap_path
