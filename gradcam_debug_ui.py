import os
import sys
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from model_inference import DR_LABELS, generate_heatmap_debug_steps, predict_image


@dataclass
class StepData:
    name: str
    key: str
    description: str


STEPS = [
    StepData("1) Original", "original", "Resized input image used by the model."),
    StepData("2) Activation mean", "activation_map", "Channel-mean activation from the target conv layer."),
    StepData("3) Gradient mean", "gradient_map", "Mean absolute gradient wrt the selected class logit."),
    StepData("4) Raw CAM", "cam_raw", "ReLU(weighted sum of activations) before post-processing."),
    StepData("5) Percentile clipped", "cam_clipped", "Raw CAM clipped to [p5, p99] to remove outliers."),
    StepData("6) Min-max normalized", "cam_normalized", "Values scaled to [0, 1]."),
    StepData("7) Gamma corrected", "cam_gamma", "Contrast enhancement using gamma = 0.8."),
    StepData("8) Smoothed CAM", "cam_blur", "Resized CAM with a small Gaussian blur."),
    StepData("9) Jet heatmap", "heatmap_rgb", "Color-mapped CAM using a jet palette."),
    StepData("10) Overlay (masked)", "overlay_masked", "Heatmap blended on image, with dark background masked out."),
]


def _normalize_to_uint8(arr: np.ndarray) -> np.ndarray:
    if arr.ndim == 3 and arr.shape[2] == 3:
        return np.clip(arr, 0, 255).astype(np.uint8)

    x = arr.astype(np.float32)
    x_min = float(np.min(x))
    x_max = float(np.max(x))
    if x_max - x_min < 1e-7:
        return np.zeros_like(x, dtype=np.uint8)
    x = (x - x_min) / (x_max - x_min)
    return (x * 255.0).astype(np.uint8)


def _to_qpixmap(arr: np.ndarray) -> QPixmap:
    img = _normalize_to_uint8(arr)

    if img.ndim == 2:
        h, w = img.shape
        qimg = QImage(img.data, w, h, w, QImage.Format_Grayscale8)
        return QPixmap.fromImage(qimg.copy())

    h, w, _ = img.shape
    qimg = QImage(img.data, w, h, 3 * w, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())


class GradCamDebugWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Grad-CAM Debug Viewer (Independent)")
        self.resize(1180, 760)

        self.image_path = ""
        self.debug_data: dict[str, object] | None = None
        self.current_step_index = 0

        self.open_btn = QPushButton("Open Image")
        self.auto_btn = QPushButton("Analyze with Predicted Class")
        self.class_spin = QSpinBox()
        self.class_spin.setMinimum(0)
        self.class_spin.setMaximum(len(DR_LABELS) - 1)
        self.manual_btn = QPushButton("Analyze with Manual Class")
        self.prev_btn = QPushButton("Previous Step")
        self.next_btn = QPushButton("Next Step")

        self.status_label = QLabel("Load an image to start.")
        self.step_title = QLabel("Step")
        self.step_title.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.image_view = QLabel()
        self.image_view.setAlignment(Qt.AlignCenter)
        self.image_view.setMinimumSize(520, 520)
        self.image_view.setStyleSheet("background: #111; border: 1px solid #444;")

        self.info_box = QTextEdit()
        self.info_box.setReadOnly(True)

        self._build_ui()
        self._connect_events()

    def _build_ui(self) -> None:
        top_controls = QHBoxLayout()
        top_controls.addWidget(self.open_btn)
        top_controls.addWidget(self.auto_btn)
        top_controls.addWidget(QLabel("Class index:"))
        top_controls.addWidget(self.class_spin)
        top_controls.addWidget(self.manual_btn)
        top_controls.addWidget(self.prev_btn)
        top_controls.addWidget(self.next_btn)

        left = QVBoxLayout()
        left.addWidget(self.step_title)
        left.addWidget(self.image_view, 1)

        right = QVBoxLayout()
        right.addWidget(QLabel("Step Details"))
        right.addWidget(self.info_box, 1)

        body = QHBoxLayout()
        body.addLayout(left, 3)
        body.addLayout(right, 2)

        root = QVBoxLayout()
        root.addLayout(top_controls)
        root.addWidget(self.status_label)
        root.addLayout(body, 1)

        container = QWidget()
        container.setLayout(root)
        self.setCentralWidget(container)

    def _connect_events(self) -> None:
        self.open_btn.clicked.connect(self._on_open_image)
        self.auto_btn.clicked.connect(self._analyze_auto)
        self.manual_btn.clicked.connect(self._analyze_manual)
        self.prev_btn.clicked.connect(self._show_prev)
        self.next_btn.clicked.connect(self._show_next)

    def _on_open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select retinal image",
            os.getcwd(),
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)",
        )
        if not path:
            return
        self.image_path = path
        self.status_label.setText(f"Selected image: {path}")
        self.debug_data = None
        self.current_step_index = 0

        pix = QPixmap(path)
        if not pix.isNull():
            self.image_view.setPixmap(pix.scaled(540, 540, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.step_title.setText("Input preview")
        self.info_box.setPlainText("Press an analyze button to generate Grad-CAM steps.")

    def _analyze_auto(self) -> None:
        if not self._ensure_image():
            return
        try:
            label, confidence_text, class_idx = predict_image(self.image_path)
            self.class_spin.setValue(class_idx)
            self.debug_data = generate_heatmap_debug_steps(self.image_path, class_idx)
            self.current_step_index = 0
            self.status_label.setText(
                f"Prediction: {label} (class {class_idx}) | {confidence_text}"
            )
            self._render_current_step()
        except Exception as exc:
            self._show_error(exc)

    def _analyze_manual(self) -> None:
        if not self._ensure_image():
            return
        class_idx = int(self.class_spin.value())
        try:
            self.debug_data = generate_heatmap_debug_steps(self.image_path, class_idx)
            self.current_step_index = 0
            self.status_label.setText(
                f"Generated debug steps for manual class index {class_idx}."
            )
            self._render_current_step()
        except Exception as exc:
            self._show_error(exc)

    def _render_current_step(self) -> None:
        if not self.debug_data:
            return

        step = STEPS[self.current_step_index]
        arr = self.debug_data[step.key]
        if not isinstance(arr, np.ndarray):
            self._show_error(RuntimeError(f"Invalid step data for key: {step.key}"))
            return

        pixmap = _to_qpixmap(arr)
        self.image_view.setPixmap(pixmap.scaled(540, 540, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        pmin = self.debug_data.get("percentile_min", 0.0)
        pmax = self.debug_data.get("percentile_max", 0.0)
        raw_min = self.debug_data.get("raw_min", 0.0)
        raw_max = self.debug_data.get("raw_max", 0.0)
        clip_min = self.debug_data.get("clip_min", 0.0)
        clip_max = self.debug_data.get("clip_max", 0.0)
        class_idx = self.debug_data.get("class_idx", "?")

        self.step_title.setText(step.name)
        self.info_box.setPlainText(
            "\n".join([
                f"Step: {step.name}",
                f"Description: {step.description}",
                "",
                f"Selected class index: {class_idx}",
                f"Percentile window: p5={pmin:.6f}, p99={pmax:.6f}",
                f"Raw CAM min/max: {raw_min:.6f} / {raw_max:.6f}",
                f"Clipped CAM min/max: {clip_min:.6f} / {clip_max:.6f}",
                "",
                "Use Previous/Next to walk through the pipeline.",
            ])
        )

    def _show_prev(self) -> None:
        if not self.debug_data:
            return
        self.current_step_index = (self.current_step_index - 1) % len(STEPS)
        self._render_current_step()

    def _show_next(self) -> None:
        if not self.debug_data:
            return
        self.current_step_index = (self.current_step_index + 1) % len(STEPS)
        self._render_current_step()

    def _ensure_image(self) -> bool:
        if self.image_path and os.path.isfile(self.image_path):
            return True
        QMessageBox.warning(self, "No image", "Select an image first.")
        return False

    def _show_error(self, exc: Exception) -> None:
        QMessageBox.critical(self, "Grad-CAM debug error", str(exc))


def main() -> int:
    app = QApplication(sys.argv)
    window = GradCamDebugWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
