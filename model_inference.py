"""
EfficientNet-B0 inference module for EyeShield DR screening.

Model: Ahmed-Selem/Shifaa-Diabetic-Retinopathy-EfficientNetB0
Source: https://huggingface.co/Ahmed-Selem/Shifaa-Diabetic-Retinopathy-EfficientNetB0
Trained on: APTOS 2019 Blindness Detection dataset
Accuracy: 98.55%

The weights file is expected at:
    Frontend/testSample/models/DiabeticRetinopathy.pth

The state dict matches torchvision EfficientNet-B0 keys with a 5-class head:
    0 → No DR
    1 → Mild DR
    2 → Moderate DR
    3 → Severe DR
    4 → Proliferative DR
"""

import os
import tempfile

import numpy as np
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image


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

# ── EfficientNet-B0 canonical input size ──────────────────────────────────────
_INPUT_SIZE = 224

# ── ImageNet normalisation (must match training pre-processing) ───────────────
_TRANSFORM = transforms.Compose([
    transforms.Resize((_INPUT_SIZE, _INPUT_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225],
    ),
])

_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
MODEL_PATH = os.path.join(_MODEL_DIR, "DiabeticRetinopathy.pth")

_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
_model: nn.Module | None = None   # lazy-loaded singleton


def is_model_available() -> bool:
    """Return True when the weights file exists on disk."""
    return os.path.isfile(MODEL_PATH)


def load_model() -> nn.Module:
    """
    Build an EfficientNet-B0 with a 5-class head and load saved weights.
    Call this once; run_inference() calls it automatically on first use.
    """
    net = models.efficientnet_b0(weights=None)
    in_features = net.classifier[1].in_features
    net.classifier[1] = nn.Linear(in_features, len(DR_LABELS))

    state = torch.load(MODEL_PATH, map_location=_device, weights_only=True)

    # Support common checkpoint wrapper formats
    if isinstance(state, dict):
        for key in ("model_state_dict", "state_dict", "model"):
            if key in state:
                state = state[key]
                break

    net.load_state_dict(state)
    net.to(_device)
    net.eval()
    return net


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


def run_inference(image_path: str) -> tuple[str, str, str]:
    """
    Run EfficientNet-B0 DR inference and Grad-CAM++ on *image_path*.

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
    global _model

    if not is_model_available():
        raise FileNotFoundError(
            f"Model weights not found at:\n{MODEL_PATH}\n\n"
            "Place DiabeticRetinopathy.pth in the models/ folder to enable inference."
        )

    if _model is None:
        _model = load_model()

    check_image_quality(image_path)

    image = Image.open(image_path).convert("RGB")
    tensor = _TRANSFORM(image).unsqueeze(0).to(_device)  # [1, 3, H, W]

    # ── Hook target layer (last feature block) for Grad-CAM++ ────────────────
    _activations: dict[str, torch.Tensor] = {}
    _gradients:   dict[str, torch.Tensor] = {}
    target_layer = _model.features[-1]

    fwd_handle = target_layer.register_forward_hook(
        lambda m, inp, out: _activations.__setitem__("A", out)
    )
    bwd_handle = target_layer.register_full_backward_hook(
        lambda m, gin, gout: _gradients.__setitem__("G", gout[0])
    )

    # ── Single forward + backward pass ───────────────────────────────────────
    _model.zero_grad()
    logits = _model(tensor)                          # autograd ON
    probs  = torch.softmax(logits.detach(), dim=1)[0]
    class_idx  = int(probs.argmax())
    confidence = float(probs[class_idx]) * 100
    logits[0, class_idx].backward()                 # gradients for Grad-CAM++

    fwd_handle.remove()
    bwd_handle.remove()

    label           = DR_LABELS[class_idx]
    confidence_text = f"Confidence: {confidence:.1f}%"

    # ── Grad-CAM++ ────────────────────────────────────────────────────────────
    heatmap_path = ""
    try:
        A = _activations["A"][0].detach()   # [C, H, W]
        G = _gradients["G"][0].detach()     # [C, H, W]

        G2    = G ** 2
        G3    = G ** 3
        A_sum = A.sum(dim=(1, 2), keepdim=True)           # [C, 1, 1]
        alpha = G2 / (2 * G2 + A_sum * G3 + 1e-7)        # [C, H, W]
        weights = (alpha * torch.relu(G)).sum(dim=(1, 2)) # [C]

        cam = torch.relu((weights[:, None, None] * A).sum(dim=0))  # [H, W]
        cam_min, cam_max = cam.min(), cam.max()
        cam = (cam - cam_min) / (cam_max - cam_min + 1e-7)
        cam_np = cam.cpu().numpy()

        # Upsample CAM to input resolution
        cam_up = np.array(
            Image.fromarray((cam_np * 255).astype(np.uint8)).resize(
                (_INPUT_SIZE, _INPUT_SIZE), Image.BILINEAR
            )
        ).astype(np.float32) / 255.0

        heatmap_rgb = _apply_jet(cam_up)                               # H×W×3
        orig_np     = np.array(image.resize((_INPUT_SIZE, _INPUT_SIZE), Image.BILINEAR))
        overlay     = (0.55 * orig_np + 0.45 * heatmap_rgb).clip(0, 255).astype(np.uint8)

        tmp = tempfile.NamedTemporaryFile(
            suffix=".png", delete=False, prefix="eyeshield_cam_"
        )
        Image.fromarray(overlay).save(tmp.name)
        tmp.close()
        heatmap_path = tmp.name
    except Exception:
        pass  # heatmap failure is non-fatal; inference result is still returned

    return label, confidence_text, heatmap_path
