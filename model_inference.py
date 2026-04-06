"""
DR inference module for EyeShield screening.

The local weights file is expected at:
    models/final_model_deepdrid.pth, models/best_model.pt or models/final_model.pth

Classes:
    0 → No DR
    1 → Mild DR
    2 → Moderate DR
    3 → Severe DR
    4 → Proliferative DR
"""

import os
import tempfile
import threading
import warnings

import numpy as np
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image, ImageFilter

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
class _EDLBackbone(nn.Module):
    """Thin wrapper that gives the EfficientNet features the 'backbone.features' path."""
    def __init__(self, features: nn.Sequential):
        super().__init__()
        self.features = features


class _EDLHead(nn.Module):
    """3-layer MLP evidence head used by the EDL EfficientNet-B3 model."""
    def __init__(self, in_features: int, num_classes: int):
        super().__init__()
        self.evidence_layer = nn.Sequential(
            nn.Linear(in_features, 512),   # 0
            nn.BatchNorm1d(512),           # 1
            nn.ReLU(),                     # 2
            nn.Dropout(0.4),              # 3
            nn.Linear(512, 128),           # 4
            nn.BatchNorm1d(128),           # 5
            nn.ReLU(),                     # 6
            nn.Dropout(0.2),              # 7
            nn.Linear(128, num_classes),   # 8
        )


class _EDLEfficientNetB3(nn.Module):
    """EfficientNet-B3 backbone with Evidential Deep Learning head.

    Outputs evidence (non-negative, via softplus) of shape [B, num_classes].
    For Dirichlet-based uncertainty: alpha = evidence + 1.
    """
    def __init__(self):
        super().__init__()
        eff = models.efficientnet_b3(weights=None)
        self.backbone = _EDLBackbone(eff.features)
        self.edl_head = _EDLHead(1536, len(DR_LABELS))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.backbone.features(x)
        x = x.mean(dim=[-2, -1])   # global average pool
        return torch.nn.functional.softplus(self.edl_head.evidence_layer(x))


def _build_edl_efficientnet_b3() -> nn.Module:
    return _EDLEfficientNetB3()

_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")

def _resolve_default_model_path() -> str:
    """Use final_model_deepdrid as the default weights path, with fallbacks."""
    deepdrid_path = os.path.join(_MODEL_DIR, "final_model_deepdrid.pth")
    if os.path.isfile(deepdrid_path):
        return deepdrid_path
    best_path = os.path.join(_MODEL_DIR, "best_model.pt")
    if os.path.isfile(best_path):
        return best_path
    return os.path.join(_MODEL_DIR, "final_model.pth")

MODEL_PATH = _resolve_default_model_path()

_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
_model: nn.Module | None = None   # lazy-loaded singleton
_model_input_size = 300
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
        for key in ("model_state_dict", "state_dict", "model", "model_state"):
            nested = state.get(key)
            if isinstance(nested, dict):
                state = nested
                break

    if not isinstance(state, dict):
        raise TypeError("Unsupported checkpoint format.")

    return state


def _torch_load(path: str) -> object:
    """Load a checkpoint, falling back to weights_only=False for older or complex checkpoints."""
    try:
        return torch.load(path, map_location=_device, weights_only=True)
    except Exception:
        return torch.load(path, map_location=_device, weights_only=False)


def _load_checkpoint_state() -> dict[str, torch.Tensor]:
    return _unwrap_state_dict(_torch_load(MODEL_PATH))

def load_model() -> nn.Module:
    """Build the EDL EfficientNet-B3 model and load weights."""
    global _model_input_size

    if not is_model_available():
        raise FileNotFoundError(
            f"Model weights not found at:\n{MODEL_PATH}\n\n"
            "Put your offline DR checkpoint in this path and try again."
        )

    state_dict = _load_checkpoint_state()
    net = _build_edl_efficientnet_b3()

    net.load_state_dict(state_dict)
    net.to(_device)
    net.eval()

    if _device.type == "cuda":
        net = net.half()

    _model_input_size = 300
    return net

def _get_heatmap_target_layer(model: nn.Module) -> nn.Module:
    return model.backbone.features[-1]

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

def _image_entropy(gray: np.ndarray) -> float:
    """Calculate Shannon entropy of the image.
    Low entropy indicates uniform/flat images without details."""
    counts, _ = np.histogram(gray, bins=256, range=(0, 256))
    p = counts / counts.sum()
    p = p[p > 0]
    return float(-np.sum(p * np.log2(p)))

def check_image_quality(image_path: str) -> None:
    """Check the uploaded image for focus, blur, poor lighting, or lack of detail before inference."""
    try:
        with Image.open(image_path) as img:
            img_gray = img.convert("L")
            # Resize a bit to normalize the variation checks across image sizes
            img_gray.thumbnail((500, 500))
            gray_np = np.array(img_gray)
    except Exception as e:
        raise ImageUngradableError(f"Could not read the image: {e}")

    lap_var = _laplacian_var(gray_np)
    mean_brightness = float(np.mean(gray_np))
    entropy = _image_entropy(gray_np)

    # Tunable thresholds: Adjust these if too strict or too lenient
    BLUR_THRESHOLD = 15.0    
    DARK_THRESHOLD = 25.0    
    BRIGHT_THRESHOLD = 240.0 
    ENTROPY_THRESHOLD = 3.5  # Typical real photos range from 5 to 8

    if entropy < ENTROPY_THRESHOLD:
        raise ImageUngradableError(
            "Image lacks sufficient detail (too uniform or washed out). Please retake the photo."
        )

    if lap_var < BLUR_THRESHOLD:
        raise ImageUngradableError(
            "Image appears to be blurry or out of focus. Please retake the photo."
        )
        
    if mean_brightness < DARK_THRESHOLD:
        raise ImageUngradableError(
            "Image is too dark. Please retake the photo with better lighting."
        )
        
    if mean_brightness > BRIGHT_THRESHOLD:
        raise ImageUngradableError(
            "Image is overexposed or too bright. Please retake the photo with less glare."
        )

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


def _load_image_tensor(image_path: str, skip_quality_check: bool = False) -> tuple[Image.Image, torch.Tensor]:
    _ensure_model_loaded()
    
    if not skip_quality_check:
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

    # logits are evidence (softplus output); compute Dirichlet expected probabilities
    evidence = logits.float()[0]
    alpha = evidence + 1.0
    S = alpha.sum()
    probs = alpha / S
    class_idx = int(alpha.argmax())
    confidence = float(probs[class_idx]) * 100.0
    vacuity = float(len(DR_LABELS) / S) * 100.0
    conf_text = f"Confidence: {confidence:.1f}%  |  Uncertainty: {vacuity:.1f}%"

    return DR_LABELS[class_idx], conf_text, class_idx

def generate_heatmap(image_path: str, class_idx: int) -> str:
    """Generate a Grad-CAM++ overlay for a previously predicted class."""
    model = _ensure_model_loaded()
    # Skip quality check here because we ALREADY checked it in predict_image
    image, tensor = _load_image_tensor(image_path, skip_quality_check=True)

    # Cast to fp16 if the model is running in half-precision (CUDA)
    if _device.type == "cuda":
        tensor = tensor.half()

    heatmap_path = ""
    fwd_handle = None
    bwd_handle = None
    try:
        activations: dict[str, torch.Tensor] = {}
        gradients: dict[str, torch.Tensor] = {}
        target_layer = _get_heatmap_target_layer(model)

        fwd_handle = target_layer.register_forward_hook(
            lambda m, inp, out: activations.__setitem__(
                "A", out[0] if isinstance(out, (tuple, list)) else out
            )
        )
        bwd_handle = target_layer.register_full_backward_hook(
            lambda m, gin, gout: gradients.__setitem__(
                "G", gout[0] if isinstance(gout, (tuple, list)) else gout
            )
        )

        model.zero_grad()
        logits = model(tensor)
        logits[0, class_idx].backward()
        if "A" not in activations or "G" not in gradients:
            raise RuntimeError("Failed to capture activations/gradients for Grad-CAM++.")

        # Force FP32 for numerically stable CAM math
        A = activations["A"][0].detach().float()
        G = gradients["G"][0].detach().float()

        G2 = G ** 2
        G3 = G ** 3
        A_sum = A.sum(dim=(1, 2), keepdim=True)
        alpha = G2 / (2 * G2 + A_sum * G3 + 1e-7)
        weights = (alpha * torch.relu(G)).sum(dim=(1, 2))

        cam = torch.relu((weights[:, None, None] * A).sum(dim=0))
        
        # 1. Percentile clipping to drop extreme hot/cold noise pixels
        cam_np = cam.cpu().numpy()
        p_min, p_max = np.percentile(cam_np, [5, 99])
        cam_np = np.clip(cam_np, p_min, p_max)
        
        # 2. Min-max normalization
        cam_min, cam_max = cam_np.min(), cam_np.max()
        cam_np = (cam_np - cam_min) / (cam_max - cam_min + 1e-7)
        
        # 3. Gamma correction to make hotspots punchier
        cam_np = cam_np ** 0.8

        cam_pil = Image.fromarray((cam_np * 255).astype(np.uint8)).resize(
            (_model_input_size, _model_input_size), Image.BILINEAR
        )
        # 4. Small blur for smoother overlay
        cam_pil = cam_pil.filter(ImageFilter.GaussianBlur(radius=1.0))
        
        cam_up = np.array(cam_pil).astype(np.float32) / 255.0

        heatmap_rgb = _apply_jet(cam_up)
        orig_np = np.array(image.resize((_model_input_size, _model_input_size), Image.BILINEAR))
        
        # 5. Adjusted blend ratio for better readability (less intense heatmap)
        overlay = (0.70 * orig_np + 0.30 * heatmap_rgb).clip(0, 255).astype(np.uint8)

        # 6. Mask out the empty background to hide corner artifacts
        gray_orig = orig_np.mean(axis=2)
        mask = gray_orig > 10
        overlay[~mask] = orig_np[~mask]

        tmp = tempfile.NamedTemporaryFile(
            suffix=".png", delete=False, prefix="eyeshield_cam_"
        )
        Image.fromarray(overlay).save(tmp.name)
        tmp.close()
        heatmap_path = tmp.name
    except Exception as exc:
        warnings.warn(f"Grad-CAM++ generation failed: {exc}", RuntimeWarning)
        heatmap_path = ""
    finally:
        if fwd_handle is not None:
            fwd_handle.remove()
        if bwd_handle is not None:
            bwd_handle.remove()

    return heatmap_path


def generate_heatmap_debug_steps(image_path: str, class_idx: int) -> dict[str, object]:
    """Return Grad-CAM++ intermediate arrays and metadata for step-by-step debugging.

    This helper is intended for standalone visualization tools and discussions.
    The returned arrays are all resized to the model input size and are safe to display.
    """
    model = _ensure_model_loaded()
    image, tensor = _load_image_tensor(image_path, skip_quality_check=True)

    if _device.type == "cuda":
        tensor = tensor.half()

    fwd_handle = None
    bwd_handle = None
    try:
        activations: dict[str, torch.Tensor] = {}
        gradients: dict[str, torch.Tensor] = {}
        target_layer = _get_heatmap_target_layer(model)

        fwd_handle = target_layer.register_forward_hook(
            lambda m, inp, out: activations.__setitem__(
                "A", out[0] if isinstance(out, (tuple, list)) else out
            )
        )
        bwd_handle = target_layer.register_full_backward_hook(
            lambda m, gin, gout: gradients.__setitem__(
                "G", gout[0] if isinstance(gout, (tuple, list)) else gout
            )
        )

        model.zero_grad()
        logits = model(tensor)
        logits[0, class_idx].backward()

        if "A" not in activations or "G" not in gradients:
            raise RuntimeError("Failed to capture activations/gradients for Grad-CAM++.")

        A = activations["A"][0].detach().float()
        G = gradients["G"][0].detach().float()

        G2 = G ** 2
        G3 = G ** 3
        A_sum = A.sum(dim=(1, 2), keepdim=True)
        alpha = G2 / (2 * G2 + A_sum * G3 + 1e-7)
        weights = (alpha * torch.relu(G)).sum(dim=(1, 2))

        cam_raw = torch.relu((weights[:, None, None] * A).sum(dim=0))
        cam_raw_np = cam_raw.cpu().numpy()

        p_min, p_max = np.percentile(cam_raw_np, [5, 99])
        cam_clipped_np = np.clip(cam_raw_np, p_min, p_max)

        cam_min, cam_max = cam_clipped_np.min(), cam_clipped_np.max()
        cam_norm_np = (cam_clipped_np - cam_min) / (cam_max - cam_min + 1e-7)

        cam_gamma_np = cam_norm_np ** 0.8

        cam_pil = Image.fromarray((cam_gamma_np * 255).astype(np.uint8)).resize(
            (_model_input_size, _model_input_size), Image.BILINEAR
        )
        cam_pil = cam_pil.filter(ImageFilter.GaussianBlur(radius=1.0))
        cam_blur_np = np.array(cam_pil).astype(np.float32) / 255.0

        heatmap_rgb = _apply_jet(cam_blur_np)
        orig_np = np.array(image.resize((_model_input_size, _model_input_size), Image.BILINEAR))

        overlay = (0.70 * orig_np + 0.30 * heatmap_rgb).clip(0, 255).astype(np.uint8)

        gray_orig = orig_np.mean(axis=2)
        mask = gray_orig > 10
        overlay_masked = overlay.copy()
        overlay_masked[~mask] = orig_np[~mask]

        # Channel-mean maps are useful for explaining what hooks captured.
        act_map = A.mean(dim=0).cpu().numpy()
        grad_map = G.abs().mean(dim=0).cpu().numpy()

        return {
            "class_idx": int(class_idx),
            "input_size": int(_model_input_size),
            "percentile_min": float(p_min),
            "percentile_max": float(p_max),
            "raw_min": float(cam_raw_np.min()),
            "raw_max": float(cam_raw_np.max()),
            "clip_min": float(cam_min),
            "clip_max": float(cam_max),
            "original": orig_np,
            "activation_map": act_map,
            "gradient_map": grad_map,
            "cam_raw": cam_raw_np,
            "cam_clipped": cam_clipped_np,
            "cam_normalized": cam_norm_np,
            "cam_gamma": cam_gamma_np,
            "cam_blur": cam_blur_np,
            "heatmap_rgb": heatmap_rgb,
            "overlay": overlay,
            "overlay_masked": overlay_masked,
            "background_mask": mask,
        }
    finally:
        if fwd_handle is not None:
            fwd_handle.remove()
        if bwd_handle is not None:
            bwd_handle.remove()


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

def list_available_models() -> list[str]:
    """Return sorted list of model file paths in the models directory."""
    try:
        files = sorted(
            os.path.join(_MODEL_DIR, f)
            for f in os.listdir(_MODEL_DIR)
            if f.endswith((".pth", ".pt")) and os.path.getsize(os.path.join(_MODEL_DIR, f)) > 1024
        )
    except OSError:
        files = []
    return files

