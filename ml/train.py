"""Train and export the AgriSense PlantVillage MobileNetV2 classifier.

The module keeps torch/torchvision imports inside training functions so its
dataset mapping and split helpers remain inspectable without a GPU runtime.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw


# Verified against the Kaggle PlantVillage folder listing. The order here is
# the public model output order and is copied unchanged to backend labels.json.
CLASS_FOLDER_MAPPING: dict[str, tuple[str, ...]] = {
    "Leaf Blight": ("Corn_(maize)___Northern_Leaf_Blight",),
    "Rust": ("Corn_(maize)___Common_rust_",),
    "Powdery Mildew": (
        "Cherry_(including_sour)___Powdery_mildew",
        "Squash___Powdery_mildew",
    ),
    "Healthy": ("Corn_(maize)___healthy",),
}
CLASS_NAMES: tuple[str, ...] = tuple(CLASS_FOLDER_MAPPING)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
IMAGE_SIZE = 224
SEED = 42
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


@dataclass(frozen=True)
class SampleRecord:
    path: Path
    label: int
    source_folder: str


@dataclass(frozen=True)
class DatasetSplits:
    train: list[SampleRecord]
    validation: list[SampleRecord]
    test: list[SampleRecord]


def _class_folders_present(path: Path) -> bool:
    for label, folders in CLASS_FOLDER_MAPPING.items():
        present = [name for name in folders if (path / name).is_dir()]
        if label == "Powdery Mildew":
            if not present:
                return False
        elif len(present) != len(folders):
            return False
    return True


def resolve_class_root(dataset_root: str | Path) -> Path:
    """Resolve the folder containing the mapped PlantVillage class folders.

    Kaggle copies commonly put the 38 class folders inside ``color/`` (with
    sibling ``grayscale/`` and ``segmented/`` folders). A direct class-folder
    root is also accepted. When multiple copies exist, ``color`` is preferred.
    """
    root = Path(dataset_root).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Dataset path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Dataset path is not a directory: {root}")
    if _class_folders_present(root):
        return root

    preferred_names = ("color", "PlantVillage", "plantvillage")
    for name in preferred_names:
        candidate = root / name
        if candidate.is_dir() and _class_folders_present(candidate):
            return candidate.resolve()

    candidates: list[Path] = []
    for current, directories, _files in os.walk(root):
        current_path = Path(current)
        if _class_folders_present(current_path):
            candidates.append(current_path.resolve())
            directories[:] = []
    if not candidates:
        required = [
            folder
            for folders in CLASS_FOLDER_MAPPING.values()
            for folder in folders
        ]
        raise ValueError(
            "Could not locate all mapped PlantVillage class folders under "
            f"{root}. Expected these exact names (at least one powdery mildew folder): {required}"
        )
    candidates.sort(key=lambda path: (path.name.casefold() != "color", len(path.parts), str(path)))
    return candidates[0]


def collect_samples(class_root: str | Path) -> tuple[list[SampleRecord], dict[str, Any]]:
    """Validate images and return records in the stable output class order."""
    root = Path(class_root).expanduser().resolve()
    if not root.is_dir() or not _class_folders_present(root):
        raise ValueError(f"Not a valid mapped PlantVillage class root: {root}")

    records: list[SampleRecord] = []
    counts: dict[str, int] = {}
    corrupt: list[str] = []
    mapped_sources: dict[str, list[str]] = {}
    for class_index, (label_name, folder_names) in enumerate(CLASS_FOLDER_MAPPING.items()):
        sources = [name for name in folder_names if (root / name).is_dir()]
        mapped_sources[label_name] = sources
        class_count = 0
        for folder_name in sources:
            folder = root / folder_name
            for image_path in sorted(folder.rglob("*")):
                if not image_path.is_file() or image_path.suffix.casefold() not in IMAGE_EXTENSIONS:
                    continue
                try:
                    with Image.open(image_path) as image:
                        image.verify()
                except (OSError, ValueError, SyntaxError):
                    corrupt.append(str(image_path))
                    continue
                records.append(SampleRecord(image_path, class_index, folder_name))
                class_count += 1
        counts[label_name] = class_count

    too_small = {label: count for label, count in counts.items() if count < 4}
    if too_small:
        raise ValueError(
            "Each class needs at least four readable images for a stratified "
            f"train/validation/test split; found {too_small}."
        )
    manifest = {
        "dataset_root": str(root),
        "mapping": {label: list(folders) for label, folders in CLASS_FOLDER_MAPPING.items()},
        "source_folders_found": mapped_sources,
        "image_counts": counts,
        "corrupt_images_skipped": len(corrupt),
        "corrupt_image_examples": corrupt[:20],
        "class_order": list(CLASS_NAMES),
    }
    return records, manifest


def stratified_split(
    records: Sequence[SampleRecord],
    seed: int = SEED,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
    test_fraction: float = 0.15,
) -> DatasetSplits:
    """Split records 70/15/15 while preserving all four class proportions."""
    fractions = (train_fraction, validation_fraction, test_fraction)
    if any(value <= 0 or value >= 1 for value in fractions) or not np.isclose(sum(fractions), 1.0):
        raise ValueError("Train, validation, and test fractions must be positive and sum to 1.")
    if not records:
        raise ValueError("No image records were supplied for splitting.")
    labels = np.asarray([record.label for record in records], dtype=np.int64)
    present = set(labels.tolist())
    expected = set(range(len(CLASS_NAMES)))
    if present != expected:
        raise ValueError(f"Expected class ids {sorted(expected)}, found {sorted(present)}.")
    counts = np.bincount(labels, minlength=len(CLASS_NAMES))
    if np.any(counts < 4):
        small = {CLASS_NAMES[index]: int(count) for index, count in enumerate(counts) if count < 4}
        raise ValueError(f"At least four images per class are required for stratification; found {small}.")

    # Split each class independently with ceil-based holdout sizing, matching
    # sklearn's deterministic fractional split behavior without loading SciPy.
    rng = random.Random(seed)
    class_groups = {
        label: [record for record in records if record.label == label]
        for label in range(len(CLASS_NAMES))
    }
    train_records: list[SampleRecord] = []
    validation_records: list[SampleRecord] = []
    test_records: list[SampleRecord] = []
    for label in range(len(CLASS_NAMES)):
        group = class_groups[label]
        rng.shuffle(group)
        holdout_size = int(np.ceil((validation_fraction + test_fraction) * len(group)))
        train_size = len(group) - holdout_size
        test_size = int(np.ceil((test_fraction / (validation_fraction + test_fraction)) * holdout_size))
        validation_size = holdout_size - test_size
        if min(train_size, validation_size, test_size) < 1:
            raise ValueError(
                f"Class {CLASS_NAMES[label]} needs enough images to place at least one sample "
                "in train, validation, and test splits."
            )
        train_records.extend(group[:train_size])
        validation_records.extend(group[train_size : train_size + validation_size])
        test_records.extend(group[train_size + validation_size :])
    rng.shuffle(train_records)
    rng.shuffle(validation_records)
    rng.shuffle(test_records)
    return DatasetSplits(
        train=list(train_records),
        validation=list(validation_records),
        test=list(test_records),
    )


def make_labels_payload(source_folders_found: dict[str, list[str]]) -> dict[str, Any]:
    """Describe class indices and input preprocessing for backend inference."""
    return {
        "class_order": list(CLASS_NAMES),
        "classes": [
            {
                "index": index,
                "label": label,
                "source_folders": source_folders_found.get(label, []),
            }
            for index, label in enumerate(CLASS_NAMES)
        ],
        "input": {
            "name": "images",
            "layout": "NCHW",
            "color": "RGB",
            "size": [IMAGE_SIZE, IMAGE_SIZE],
            "dtype": "float32",
            "normalization": {"mean": list(IMAGENET_MEAN), "std": list(IMAGENET_STD)},
        },
        "output": {"name": "probabilities", "type": "softmax probabilities"},
        "quantization": "ONNX Runtime static QDQ int8 weights and uint8 activations",
    }


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch
    except ImportError:
        return
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


class RandomBackgroundVariation:
    """Vary background/context while keeping the center of a leaf mostly intact."""

    def __init__(self, probability: float = 0.20) -> None:
        self.probability = probability

    def __call__(self, image: Image.Image) -> Image.Image:
        if random.random() >= self.probability:
            return image
        image = image.convert("RGB")
        width, height = image.size
        blur_radius = max(4.0, min(width, height) * random.uniform(0.035, 0.08))
        background = image.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        background = ImageEnhance.Color(background).enhance(random.uniform(0.45, 1.6))
        background = ImageEnhance.Brightness(background).enhance(random.uniform(0.72, 1.32))

        # A soft central mask protects most leaf detail; its randomized boundary
        # and blurred, relit perimeter introduce varied contextual backgrounds.
        mask = Image.new("L", image.size, 0)
        draw = ImageDraw.Draw(mask)
        inset_x = int(width * random.uniform(0.06, 0.13))
        inset_y = int(height * random.uniform(0.05, 0.12))
        draw.ellipse((inset_x, inset_y, width - inset_x, height - inset_y), fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=max(2.0, width * 0.025)))
        return Image.composite(image, background, mask)


def create_transforms() -> tuple[Any, Any]:
    """Return augmented train and deterministic evaluation transforms."""
    from torchvision import transforms

    train_transform = transforms.Compose(
        [
            transforms.RandomResizedCrop(IMAGE_SIZE, scale=(0.72, 1.0), ratio=(0.86, 1.16)),
            transforms.RandomHorizontalFlip(p=0.50),
            transforms.RandomVerticalFlip(p=0.08),
            transforms.RandomRotation(degrees=22),
            transforms.RandomAffine(degrees=10, translate=(0.07, 0.07), scale=(0.90, 1.10), shear=7),
            transforms.RandomPerspective(distortion_scale=0.16, p=0.24),
            RandomBackgroundVariation(probability=0.20),
            transforms.ColorJitter(brightness=0.28, contrast=0.24, saturation=0.22, hue=0.035),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
            transforms.RandomErasing(p=0.18, scale=(0.02, 0.12), ratio=(0.35, 2.8), value="random"),
        ]
    )
    evaluation_transform = transforms.Compose(
        [
            transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ]
    )
    return train_transform, evaluation_transform


def _make_datasets_and_loaders(
    splits: DatasetSplits,
    batch_size: int,
    workers: int,
    seed: int,
) -> tuple[Any, Any, Any, Any, Any]:
    import torch
    from torch.utils.data import DataLoader, Dataset

    train_transform, evaluation_transform = create_transforms()

    class LeafDataset(Dataset):
        def __init__(self, records: Sequence[SampleRecord], transform: Any) -> None:
            self.records = list(records)
            self.transform = transform

        def __len__(self) -> int:
            return len(self.records)

        def __getitem__(self, index: int) -> tuple[Any, int]:
            record = self.records[index]
            with Image.open(record.path) as source:
                image = source.convert("RGB")
            return self.transform(image), record.label

    def worker_init_fn(worker_id: int) -> None:
        worker_seed = seed + worker_id
        random.seed(worker_seed)
        np.random.seed(worker_seed)
        torch.manual_seed(worker_seed)

    generator = torch.Generator()
    generator.manual_seed(seed)
    train_dataset = LeafDataset(splits.train, train_transform)
    train_eval_dataset = LeafDataset(splits.train, evaluation_transform)
    validation_dataset = LeafDataset(splits.validation, evaluation_transform)
    test_dataset = LeafDataset(splits.test, evaluation_transform)
    loader_options = {
        "batch_size": batch_size,
        "num_workers": workers,
        "pin_memory": torch.cuda.is_available(),
        "persistent_workers": workers > 0,
        "worker_init_fn": worker_init_fn,
    }
    train_loader = DataLoader(
        train_dataset,
        shuffle=True,
        generator=generator,
        drop_last=False,
        **loader_options,
    )
    validation_loader = DataLoader(validation_dataset, shuffle=False, **loader_options)
    test_loader = DataLoader(test_dataset, shuffle=False, **loader_options)
    calibration_loader = DataLoader(
        train_eval_dataset,
        shuffle=False,
        **loader_options,
    )
    class_counts = np.bincount(
        np.asarray([record.label for record in splits.train], dtype=np.int64),
        minlength=len(CLASS_NAMES),
    )
    if np.any(class_counts == 0):
        raise ValueError(f"Training split is missing one or more classes: {class_counts.tolist()}")
    weights = len(splits.train) / (len(CLASS_NAMES) * class_counts)
    return train_loader, validation_loader, test_loader, calibration_loader, torch.tensor(weights, dtype=torch.float32)


def _make_model(pretrained: bool = True) -> Any:
    import torch.nn as nn
    from torchvision.models import MobileNet_V2_Weights, mobilenet_v2

    weights = MobileNet_V2_Weights.DEFAULT if pretrained else None
    model = mobilenet_v2(weights=weights)
    in_features = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(in_features, len(CLASS_NAMES))
    return model


def _run_epoch(
    model: Any,
    loader: Any,
    criterion: Any,
    device: Any,
    optimizer: Any | None = None,
    scaler: Any | None = None,
) -> tuple[float, float]:
    import torch

    training = optimizer is not None
    model.train(training)
    loss_sum = 0.0
    correct = 0
    total = 0
    amp_enabled = device.type == "cuda"
    for images, labels in loader:
        images = images.to(device, non_blocking=amp_enabled)
        labels = labels.to(device, non_blocking=amp_enabled)
        if training:
            optimizer.zero_grad(set_to_none=True)
        with torch.set_grad_enabled(training):
            with torch.autocast(device_type=device.type, enabled=amp_enabled):
                logits = model(images)
                loss = criterion(logits, labels)
            if training:
                if scaler is not None and amp_enabled:
                    scaler.scale(loss).backward()
                    scaler.step(optimizer)
                    scaler.update()
                else:
                    loss.backward()
                    optimizer.step()
        batch_size = labels.size(0)
        loss_sum += float(loss.detach().item()) * batch_size
        correct += int((logits.detach().argmax(dim=1) == labels).sum().item())
        total += batch_size
    if total == 0:
        raise ValueError("A data loader produced no images.")
    return loss_sum / total, correct / total


def _train_model(
    model: Any,
    train_loader: Any,
    validation_loader: Any,
    class_weights: Any,
    device: Any,
    epochs: int,
    patience: int,
    learning_rate: float,
    max_minutes: float,
) -> tuple[dict[str, list[float]], bool]:
    import torch

    model.to(device)
    criterion = torch.nn.CrossEntropyLoss(weight=class_weights.to(device))
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=1, min_lr=1e-6
    )
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    history: dict[str, list[float]] = {
        "train_loss": [],
        "validation_loss": [],
        "train_accuracy": [],
        "validation_accuracy": [],
        "learning_rate": [],
    }
    best_state: dict[str, Any] | None = None
    best_validation_loss = float("inf")
    best_epoch = 0
    stale_epochs = 0
    deadline = time.monotonic() + max_minutes * 60.0
    stopped_by_time = False

    for epoch in range(1, epochs + 1):
        train_loss, train_accuracy = _run_epoch(
            model, train_loader, criterion, device, optimizer=optimizer, scaler=scaler
        )
        validation_loss, validation_accuracy = _run_epoch(
            model, validation_loader, criterion, device
        )
        scheduler.step(validation_loss)
        learning_rate_now = float(optimizer.param_groups[0]["lr"])
        history["train_loss"].append(train_loss)
        history["validation_loss"].append(validation_loss)
        history["train_accuracy"].append(train_accuracy)
        history["validation_accuracy"].append(validation_accuracy)
        history["learning_rate"].append(learning_rate_now)
        print(
            f"epoch {epoch:02d}/{epochs}: train loss={train_loss:.4f} acc={train_accuracy:.4f}; "
            f"validation loss={validation_loss:.4f} acc={validation_accuracy:.4f}; "
            f"lr={learning_rate_now:.2g}"
        )

        if validation_loss < best_validation_loss - 1e-4:
            best_validation_loss = validation_loss
            best_epoch = epoch
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            stale_epochs = 0
        else:
            stale_epochs += 1

        if stale_epochs >= patience:
            print(f"early stopping: validation loss did not improve for {patience} epochs")
            break
        if time.monotonic() >= deadline:
            stopped_by_time = True
            print("training time budget reached; restoring the best validation checkpoint")
            break

    if best_state is None:
        raise RuntimeError("Training completed without a best validation checkpoint.")
    model.load_state_dict(best_state)
    history["best_epoch"] = [float(best_epoch)]
    history["best_validation_loss"] = [best_validation_loss]
    return history, stopped_by_time


def _predict(model: Any, loader: Any, device: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    import torch

    model.eval()
    logits_parts: list[np.ndarray] = []
    label_parts: list[np.ndarray] = []
    amp_enabled = device.type == "cuda"
    with torch.inference_mode():
        for images, labels in loader:
            images = images.to(device, non_blocking=amp_enabled)
            with torch.autocast(device_type=device.type, enabled=amp_enabled):
                logits = model(images)
            logits_parts.append(logits.float().cpu().numpy())
            label_parts.append(labels.numpy())
    logits_array = np.concatenate(logits_parts, axis=0)
    label_array = np.concatenate(label_parts, axis=0)
    probabilities = torch.softmax(torch.from_numpy(logits_array), dim=1).numpy()
    return label_array, logits_array, probabilities


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _save_training_history(history: dict[str, list[float]], reports_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _write_json(reports_dir / "training_history.json", history)
    epochs = range(1, len(history["train_loss"]) + 1)
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    axes[0].plot(epochs, history["train_loss"], marker="o", label="Training")
    axes[0].plot(epochs, history["validation_loss"], marker="o", label="Validation")
    axes[0].set(title="Loss", xlabel="Epoch", ylabel="Cross-entropy")
    axes[0].legend()
    axes[1].plot(epochs, history["train_accuracy"], marker="o", label="Training")
    axes[1].plot(epochs, history["validation_accuracy"], marker="o", label="Validation")
    axes[1].set(title="Accuracy", xlabel="Epoch", ylabel="Accuracy", ylim=(0, 1))
    axes[1].legend()
    figure.suptitle("MobileNetV2 training history")
    figure.tight_layout()
    figure.savefig(reports_dir / "training_history.png", dpi=160, bbox_inches="tight")
    plt.close(figure)


def _save_evaluation(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    reports_dir: Path,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, precision_recall_fscore_support

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    y_pred = probabilities.argmax(axis=1)
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=np.arange(len(CLASS_NAMES)), zero_division=0
    )
    accuracy = float(accuracy_score(y_true, y_pred))
    report_dict = classification_report(
        y_true,
        y_pred,
        labels=np.arange(len(CLASS_NAMES)),
        target_names=list(CLASS_NAMES),
        output_dict=True,
        zero_division=0,
    )
    report_text = classification_report(
        y_true,
        y_pred,
        labels=np.arange(len(CLASS_NAMES)),
        target_names=list(CLASS_NAMES),
        zero_division=0,
        digits=4,
    )
    matrix = confusion_matrix(y_true, y_pred, labels=np.arange(len(CLASS_NAMES)))
    per_class = [
        {
            "class": label,
            "precision": float(precision[index]),
            "recall": float(recall[index]),
            "f1_score": float(f1[index]),
            "support": int(support[index]),
        }
        for index, label in enumerate(CLASS_NAMES)
    ]
    metrics = {
        **metadata,
        "overall_accuracy": accuracy,
        "per_class": per_class,
        "classification_report": report_dict,
        "confusion_matrix": matrix.tolist(),
        "class_order": list(CLASS_NAMES),
        "test_examples": int(len(y_true)),
    }
    _write_json(reports_dir / "metrics.json", metrics)
    _write_json(reports_dir / "classification_report.json", report_dict)
    (reports_dir / "classification_report.txt").write_text(report_text, encoding="utf-8")
    with (reports_dir / "per_class_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("class", "precision", "recall", "f1_score", "support"))
        writer.writeheader()
        writer.writerows(per_class)
    with (reports_dir / "confusion_matrix.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["actual \\ predicted", *CLASS_NAMES])
        for label, row in zip(CLASS_NAMES, matrix.tolist()):
            writer.writerow([label, *row])

    figure, axis = plt.subplots(figsize=(7.2, 6.1))
    image = axis.imshow(matrix, interpolation="nearest", cmap="Greens")
    figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    axis.set(
        xticks=np.arange(len(CLASS_NAMES)),
        yticks=np.arange(len(CLASS_NAMES)),
        xticklabels=CLASS_NAMES,
        yticklabels=CLASS_NAMES,
        ylabel="Actual class",
        xlabel="Predicted class",
        title="Test-set confusion matrix",
    )
    plt.setp(axis.get_xticklabels(), rotation=25, ha="right", rotation_mode="anchor")
    threshold = matrix.max() / 2.0 if matrix.size else 0
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            axis.text(
                column,
                row,
                str(matrix[row, column]),
                ha="center",
                va="center",
                color="white" if matrix[row, column] > threshold else "black",
            )
    figure.tight_layout()
    figure.savefig(reports_dir / "confusion_matrix.png", dpi=160, bbox_inches="tight")
    plt.close(figure)
    return metrics


def _choose_verification_records(records: Sequence[SampleRecord]) -> list[SampleRecord]:
    selected: list[SampleRecord] = []
    used: set[Path] = set()
    for label_index in range(len(CLASS_NAMES)):
        matching = next((record for record in records if record.label == label_index), None)
        if matching is not None:
            selected.append(matching)
            used.add(matching.path)
    for record in records:
        if len(selected) >= 5:
            break
        if record.path not in used:
            selected.append(record)
            used.add(record.path)
    if len(selected) < 5:
        raise ValueError("At least five test images are required for ONNX parity verification.")
    return selected[:5]


def _export_int8_onnx(
    model: Any,
    test_records: Sequence[SampleRecord],
    calibration_loader: Any,
    reports_dir: Path,
    model_output: Path,
    labels_output: Path,
    source_folders_found: dict[str, list[str]],
    calibration_batches: int,
) -> dict[str, Any]:
    import onnx
    import onnxruntime as ort
    import torch
    import torch.nn as nn
    from onnxruntime.quantization import CalibrationDataReader, QuantFormat, QuantType, quantize_static

    class ProbabilityModel(nn.Module):
        def __init__(self, classifier: Any) -> None:
            super().__init__()
            self.classifier = classifier

        def forward(self, images: Any) -> Any:
            return torch.softmax(self.classifier(images), dim=1)

    class ImageCalibrationReader(CalibrationDataReader):
        def __init__(self, loader: Any, input_name: str, max_batches: int) -> None:
            self.loader = loader
            self.input_name = input_name
            self.max_batches = max_batches
            self.rewind()

        def rewind(self) -> None:
            self.iterator = iter(self.loader)
            self.read_count = 0

        def get_next(self) -> dict[str, np.ndarray] | None:
            if self.read_count >= self.max_batches:
                return None
            try:
                images, _labels = next(self.iterator)
            except StopIteration:
                return None
            self.read_count += 1
            return {self.input_name: images.numpy().astype(np.float32, copy=False)}

    import torch.utils.data as torch_data
    from torchvision import transforms

    class VerificationDataset(torch_data.Dataset):
        def __init__(self, items: Sequence[SampleRecord]) -> None:
            self.items = list(items)
            self.transform = transforms.Compose(
                [
                    transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
                    transforms.ToTensor(),
                    transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
                ]
            )

        def __len__(self) -> int:
            return len(self.items)

        def __getitem__(self, index: int) -> tuple[Any, int]:
            record = self.items[index]
            with Image.open(record.path) as source:
                image = source.convert("RGB")
            return self.transform(image), record.label

    model_output = model_output.expanduser().resolve()
    labels_output = labels_output.expanduser().resolve()
    model_output.parent.mkdir(parents=True, exist_ok=True)
    labels_output.parent.mkdir(parents=True, exist_ok=True)
    input_name = "images"
    output_name = "probabilities"
    model = model.cpu().eval()
    probability_model = ProbabilityModel(model).eval()
    dummy_input = torch.zeros((1, 3, IMAGE_SIZE, IMAGE_SIZE), dtype=torch.float32)
    verification_records = _choose_verification_records(test_records)
    verification_dataset = VerificationDataset(verification_records)
    verification_images = torch.stack([verification_dataset[index][0] for index in range(len(verification_dataset))])
    with tempfile.TemporaryDirectory(prefix="agrisense_onnx_") as temporary_dir:
        float_path = Path(temporary_dir) / "mobilenetv2_float.onnx"
        quantized_path = Path(temporary_dir) / "mobilenetv2_int8.onnx"
        torch.onnx.export(
            probability_model,
            dummy_input,
            str(float_path),
            input_names=[input_name],
            output_names=[output_name],
            dynamic_axes={input_name: {0: "batch_size"}, output_name: {0: "batch_size"}},
            opset_version=17,
            do_constant_folding=True,
            dynamo=False,
        )
        calibration_reader = ImageCalibrationReader(calibration_loader, input_name, calibration_batches)
        quantize_static(
            model_input=str(float_path),
            model_output=str(quantized_path),
            calibration_data_reader=calibration_reader,
            quant_format=QuantFormat.QDQ,
            activation_type=QuantType.QUInt8,
            weight_type=QuantType.QInt8,
            per_channel=True,
            op_types_to_quantize=["Conv", "Gemm"],
        )
        quantized_model = onnx.load(str(quantized_path))
        onnx.checker.check_model(quantized_model)
        quant_nodes = sum(node.op_type in {"QuantizeLinear", "QLinearConv", "ConvInteger"} for node in quantized_model.graph.node)
        int8_initializers = sum(
            initializer.data_type in {onnx.TensorProto.INT8, onnx.TensorProto.UINT8}
            for initializer in quantized_model.graph.initializer
        )
        if quant_nodes == 0 or int8_initializers == 0:
            raise RuntimeError("The exported ONNX graph contains no verified int8 quantization nodes/weights.")
        metadata = {
            "agrisense.class_order": json.dumps(list(CLASS_NAMES)),
            "agrisense.input_size": str(IMAGE_SIZE),
            "agrisense.output": "softmax probabilities",
        }
        existing_metadata = {item.key: item for item in quantized_model.metadata_props}
        for key, value in metadata.items():
            if key in existing_metadata:
                existing_metadata[key].value = value
            else:
                item = quantized_model.metadata_props.add()
                item.key = key
                item.value = value
        onnx.save(quantized_model, str(quantized_path))

        session_options = ort.SessionOptions()
        session_options.intra_op_num_threads = max(1, min(4, os.cpu_count() or 1))
        session = ort.InferenceSession(
            str(quantized_path),
            sess_options=session_options,
            providers=["CPUExecutionProvider"],
        )
        with torch.inference_mode():
            torch_probabilities = probability_model(verification_images).cpu().numpy()
        onnx_probabilities = session.run([output_name], {input_name: verification_images.numpy()})[0]
        absolute_difference = np.abs(torch_probabilities - onnx_probabilities)
        top1_equal = (torch_probabilities.argmax(axis=1) == onnx_probabilities.argmax(axis=1)).tolist()
        within_tolerance = np.allclose(torch_probabilities, onnx_probabilities, rtol=0.15, atol=0.12)
        verification = {
            "sample_count": len(verification_records),
            "samples": [
                {
                    "image": str(record.path),
                    "true_label": CLASS_NAMES[record.label],
                    "pytorch_prediction": CLASS_NAMES[int(torch_probabilities[index].argmax())],
                    "onnx_prediction": CLASS_NAMES[int(onnx_probabilities[index].argmax())],
                    "max_absolute_probability_difference": float(absolute_difference[index].max()),
                    "top1_match": bool(top1_equal[index]),
                }
                for index, record in enumerate(verification_records)
            ],
            "top1_matches_all_samples": all(top1_equal),
            "max_absolute_probability_difference": float(absolute_difference.max()),
            "tolerance": {"rtol": 0.15, "atol": 0.12},
            "probabilities_within_tolerance": bool(within_tolerance),
            "int8_quantization_nodes": int(quant_nodes),
            "int8_or_uint8_initializers": int(int8_initializers),
            "providers": session.get_providers(),
        }
        _write_json(reports_dir / "onnx_validation.json", verification)
        if not verification["top1_matches_all_samples"] or not within_tolerance:
            raise RuntimeError(
                "INT8 ONNX/PyTorch parity verification failed on the five stratified samples. "
                f"See {reports_dir / 'onnx_validation.json'}; no new model artifact was installed."
            )

        temporary_model_output = model_output.with_name(model_output.name + ".tmp")
        temporary_labels_output = labels_output.with_name(labels_output.name + ".tmp")
        temporary_model_output.write_bytes(quantized_path.read_bytes())
        _write_json(temporary_labels_output, make_labels_payload(source_folders_found))
        os.replace(temporary_model_output, model_output)
        os.replace(temporary_labels_output, labels_output)

    return {
        **verification,
        "model_path": str(model_output),
        "model_size_bytes": model_output.stat().st_size,
        "model_sha256": _sha256_file(model_output),
        "labels_path": str(labels_output),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _split_counts(records: Sequence[SampleRecord]) -> dict[str, int]:
    counts = {name: 0 for name in CLASS_NAMES}
    for record in records:
        counts[CLASS_NAMES[record.label]] += 1
    return counts


def _default_dataset_candidates(project_root: Path) -> list[Path]:
    return [Path("/kaggle/input"), project_root / "data"]


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=None, help="PlantVillage directory, its color directory, or a parent containing it.")
    parser.add_argument("--reports-dir", type=Path, default=project_root / "ml" / "reports")
    parser.add_argument("--model-output", type=Path, default=project_root / "backend" / "app" / "ml" / "model.onnx")
    parser.add_argument("--labels-output", type=Path, default=project_root / "backend" / "app" / "ml" / "labels.json")
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--patience", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--max-minutes", type=float, default=23.0, help="Maximum model-training time before restoring the best epoch.")
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--calibration-batches", type=int, default=12)
    args = parser.parse_args(argv)
    if args.epochs < 1 or args.patience < 1 or args.batch_size < 1 or args.workers < 0:
        parser.error("epochs, patience, and batch-size must be positive; workers cannot be negative")
    if args.max_minutes <= 0 or args.learning_rate <= 0 or args.calibration_batches < 1:
        parser.error("max-minutes, learning-rate, and calibration-batches must be positive")
    if args.dataset_root is None:
        args.dataset_root = next((candidate for candidate in _default_dataset_candidates(project_root) if candidate.exists()), None)
        if args.dataset_root is None:
            parser.error("provide --dataset-root pointing to the Kaggle PlantVillage input directory")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        import torch
    except ImportError as error:
        raise RuntimeError("Install the training environment with `pip install -r ml/requirements.txt`.") from error

    seed_everything(args.seed)
    class_root = resolve_class_root(args.dataset_root)
    records, manifest = collect_samples(class_root)
    splits = stratified_split(records, seed=args.seed)
    manifest["split_counts"] = {
        "train": _split_counts(splits.train),
        "validation": _split_counts(splits.validation),
        "test": _split_counts(splits.test),
    }
    manifest["split_sizes"] = {
        "train": len(splits.train),
        "validation": len(splits.validation),
        "test": len(splits.test),
    }
    manifest["random_seed"] = args.seed

    run_id = datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S_%f_utc")
    reports_root = args.reports_dir.expanduser().resolve()
    reports_dir = reports_root / run_id
    reports_dir.mkdir(parents=True, exist_ok=False)
    _write_json(reports_dir / "dataset_manifest.json", manifest)
    print(f"dataset root: {class_root}")
    print(f"validated image counts: {manifest['image_counts']}")
    print(f"stratified split sizes: {manifest['split_sizes']}")
    print(f"fixed seed: {args.seed}")

    train_loader, validation_loader, test_loader, calibration_loader, class_weights = _make_datasets_and_loaders(
        splits, args.batch_size, args.workers, args.seed
    )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}; ImageNet-pretrained MobileNetV2 will be used")
    model = _make_model(pretrained=True)
    history, stopped_by_time = _train_model(
        model,
        train_loader,
        validation_loader,
        class_weights,
        device,
        epochs=args.epochs,
        patience=args.patience,
        learning_rate=args.learning_rate,
        max_minutes=args.max_minutes,
    )
    _save_training_history(history, reports_dir)
    y_true, _logits, probabilities = _predict(model, test_loader, device)
    training_metadata = {
        "model_architecture": "torchvision.mobilenet_v2",
        "pretrained_weights": "MobileNet_V2_Weights.DEFAULT",
        "input_size": [IMAGE_SIZE, IMAGE_SIZE],
        "random_seed": args.seed,
        "device": str(device),
        "epochs_completed": len(history["train_loss"]),
        "best_epoch": int(history["best_epoch"][0]),
        "stopped_by_time_budget": stopped_by_time,
        "training_time_budget_minutes": args.max_minutes,
        "class_weights": class_weights.tolist(),
        "split_sizes": manifest["split_sizes"],
        "class_order": list(CLASS_NAMES),
    }
    metrics = _save_evaluation(y_true, probabilities, reports_dir, training_metadata)
    print(f"test accuracy: {metrics['overall_accuracy']:.4f}")
    print(f"classification report: {reports_dir / 'classification_report.txt'}")

    export_report = _export_int8_onnx(
        model,
        splits.test,
        calibration_loader,
        reports_dir,
        args.model_output,
        args.labels_output,
        manifest["source_folders_found"],
        calibration_batches=args.calibration_batches,
    )
    _write_json(reports_dir / "onnx_export.json", export_report)
    print(f"verified int8 ONNX model: {export_report['model_path']}")
    print(f"class labels: {export_report['labels_path']}")
    print(f"reports: {reports_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
