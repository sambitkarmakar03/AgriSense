"""Quick smoke check for the bundled ONNX graph and its labels metadata.

Run from the backend directory:
    python -m app.ml.verify_model
    python -m app.ml.verify_model --image /path/to/leaf.jpg
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

from PIL import Image

from app.ml.inference import DiseaseInferenceService


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image",
        type=Path,
        action="append",
        help="Image to classify; may be supplied more than once to verify batching.",
    )
    args = parser.parse_args()

    service = DiseaseInferenceService()
    if args.image:
        images = [path.read_bytes() for path in args.image]
    else:
        sample = Image.new("RGB", (224, 224), color=(96, 128, 72))
        sample_bytes = io.BytesIO()
        sample.save(sample_bytes, format="PNG")
        images = [sample_bytes.getvalue()]

    results = service.predict_batch(images)
    print("ONNX metadata verified:")
    print(
        json.dumps(
            {
                "class_order": service.class_order,
                "input_size": service.model_metadata["agrisense.input_size"],
                "output": service.model_metadata["agrisense.output"],
                "providers": ["CPUExecutionProvider"],
            },
            indent=2,
        )
    )
    for index, result in enumerate(results):
        print(f"Image {index + 1}:")
        print(json.dumps(result.as_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
