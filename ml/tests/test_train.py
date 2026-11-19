import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ml.train import (
    CLASS_FOLDER_MAPPING,
    CLASS_NAMES,
    collect_samples,
    make_labels_payload,
    resolve_class_root,
    stratified_split,
)


class TrainPipelineHelpersTest(unittest.TestCase):
    def _write_dataset(self, root: Path, images_per_class: int = 20) -> Path:
        color = root / "color"
        for folders in CLASS_FOLDER_MAPPING.values():
            for folder_name in folders:
                (color / folder_name).mkdir(parents=True, exist_ok=True)
        for label_index, folders in enumerate(CLASS_FOLDER_MAPPING.values()):
            # Put the combined powdery-mildew class in both source folders.
            for image_index in range(images_per_class):
                folder_name = folders[image_index % len(folders)]
                image = Image.new(
                    "RGB",
                    (24, 24),
                    (label_index * 40, image_index * 5, 100),
                )
                image.save(color / folder_name / f"leaf_{image_index:03}.jpg")
        return color

    def test_mapping_is_the_required_model_output_order(self) -> None:
        self.assertEqual(CLASS_NAMES, ("Leaf Blight", "Rust", "Powdery Mildew", "Healthy"))
        self.assertEqual(
            CLASS_FOLDER_MAPPING["Leaf Blight"],
            ("Corn_(maize)___Northern_Leaf_Blight",),
        )
        self.assertEqual(CLASS_FOLDER_MAPPING["Rust"], ("Corn_(maize)___Common_rust_",))
        self.assertEqual(
            set(CLASS_FOLDER_MAPPING["Powdery Mildew"]),
            {"Cherry_(including_sour)___Powdery_mildew", "Squash___Powdery_mildew"},
        )
        self.assertEqual(CLASS_FOLDER_MAPPING["Healthy"], ("Corn_(maize)___healthy",))

    def test_resolver_prefers_color_and_collection_validates_images(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            color = self._write_dataset(root)
            (color / CLASS_FOLDER_MAPPING["Healthy"][0] / "broken.jpg").write_bytes(b"not an image")
            resolved = resolve_class_root(root)
            self.assertEqual(resolved, color.resolve())

            records, manifest = collect_samples(resolved)
            self.assertEqual(len(records), 80)
            self.assertEqual(manifest["corrupt_images_skipped"], 1)
            self.assertEqual(manifest["image_counts"], {name: 20 for name in CLASS_NAMES})
            self.assertEqual(
                manifest["source_folders_found"]["Powdery Mildew"],
                list(CLASS_FOLDER_MAPPING["Powdery Mildew"]),
            )

    def test_split_is_seeded_stratified_and_70_15_15(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            records, _manifest = collect_samples(self._write_dataset(Path(temporary)))
            first = stratified_split(records, seed=71)
            repeated = stratified_split(records, seed=71)
            self.assertEqual(
                [record.path for record in first.train],
                [record.path for record in repeated.train],
            )
            self.assertEqual(len(first.train), 56)
            self.assertEqual(len(first.validation), 12)
            self.assertEqual(len(first.test), 12)
            for split in (first.train, first.validation, first.test):
                self.assertEqual({record.label for record in split}, set(range(4)))

    def test_labels_payload_keeps_output_indices_stable(self) -> None:
        payload = make_labels_payload(
            {label: list(folders) for label, folders in CLASS_FOLDER_MAPPING.items()}
        )
        self.assertEqual(payload["class_order"], list(CLASS_NAMES))
        self.assertEqual([item["index"] for item in payload["classes"]], [0, 1, 2, 3])
        self.assertEqual([item["label"] for item in payload["classes"]], list(CLASS_NAMES))
        self.assertEqual(payload["input"]["size"], [224, 224])
        self.assertEqual(json.loads(json.dumps(payload)), payload)


if __name__ == "__main__":
    unittest.main()
