# AgriSense crop disease training

This directory contains the Phase 3 training and export pipeline for a four-class crop leaf classifier. It fine-tunes an ImageNet-pretrained MobileNetV2 in PyTorch, evaluates the held-out test set, exports a static quantized int8 ONNX model, and checks ONNX Runtime parity against PyTorch on five test images.

The trained model and run reports from the supplied Kaggle execution are now installed in this repository. Its report records 12 CUDA epochs, a 3,485/746/749 train/validation/test split, 100% accuracy on those 749 held-out PlantVillage images, and successful five-image PyTorch/ONNX parity with a maximum probability difference of 0.0194. These are results on a random PlantVillage split, not evidence of field-photo accuracy; the notebook notes background and crop-source shortcuts in this dataset.

The delivered model is `backend/app/ml/model.onnx` (SHA-256 `315b53e105e29331391dc0b3a66bf8d6f965ae6d1981dc217f4b0817ff994779`), with matching output order in `backend/app/ml/labels.json`. Full evaluation and export reports are under `ml/reports/run_20261119_123144_283924_utc/`.

## Dataset and class mapping

The source dataset is [PlantVillage on Kaggle](https://www.kaggle.com/datasets/abdallahalidev/plantvillage-dataset). The mapping below is the single source of truth in `train.py`; output indices follow dictionary insertion order:

| Model index | Output label | PlantVillage source folder |
| ---: | --- | --- |
| 0 | Leaf Blight | `Corn_(maize)___Northern_Leaf_Blight` |
| 1 | Rust | `Corn_(maize)___Common_rust_` |
| 2 | Powdery Mildew | `Cherry_(including_sour)___Powdery_mildew`, `Squash___Powdery_mildew` |
| 3 | Healthy | `Corn_(maize)___healthy` |

The exact source names were checked against Kaggle's PlantVillage folder listing, including the trailing underscore in `Corn_(maize)___Common_rust_` ([Kaggle notebook dataset listing](https://www.kaggle.com/code/atharvaingle/plant-disease-classification-resnet-99-2/log)). The loader accepts either or both Powdery Mildew folders and combines them into one model class. It prefers the dataset's `color/` tree when present, otherwise it searches for the mapped class-folder root.

Kaggle lists the dataset under the CC BY-NC-SA 4.0 license. Review that license against the intended model training, distribution, and product use before publishing the resulting model or reports.

## Pipeline

- Validates mapped class folders and image readability; records corrupt image counts and examples in the dataset manifest.
- Splits the data into stratified 70% train, 15% validation, and 15% test sets using seed `42` by default.
- Resizes inputs to `224 x 224`, converts to RGB, and applies ImageNet normalization.
- Augments training images with random crops, horizontal/vertical flips, rotation, affine angle/translation/scale/shear, perspective changes, lighting/color jitter, random erasing, and background/context variation.
- Uses balanced class weights in the loss function.
- Fine-tunes torchvision MobileNetV2 with early stopping on validation loss; the defaults allow up to 12 epochs, patience 3, and a 23-minute training budget.
- Saves overall accuracy, per-class precision/recall/F1, a classification report, confusion matrix, split manifest, and training history/plots.
- Exports ONNX with static QDQ quantization (int8 weights and uint8 activations). It checks the graph and requires the top prediction to match for all five parity samples, with probability comparison tolerance `rtol=0.15, atol=0.12`. Artifacts are installed only after those checks pass.

Reports are written under a unique `ml/reports/run_<UTC timestamp>/` directory. Expected files include `metrics.json`, `per_class_metrics.csv`, `classification_report.json`, `classification_report.txt`, `confusion_matrix.csv`, `confusion_matrix.png`, `training_history.json`, `training_history.png`, `dataset_manifest.json`, and ONNX export/validation reports.

## Run locally

Use Python 3.11 or newer and a CUDA-enabled PyTorch installation for practical training speed. Install the training stack in a dedicated environment. PyTorch, torchvision, scikit-learn, and matplotlib stay out of the backend; the backend installs only ONNX Runtime, NumPy, and Pillow for inference:

```bash
python -m venv .venv-ml
# macOS/Linux
source .venv-ml/bin/activate
# Windows PowerShell: .venv-ml\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r ml/requirements.txt
python ml/train.py --dataset-root /path/to/PlantVillage --max-minutes 23
```

The dataset root may be the Kaggle download directory, its `color/` directory, or a parent containing it. The script also supports `--reports-dir`, `--model-output`, and `--labels-output` for alternate output locations. Run `python ml/train.py --help` for all options.

## Run on Kaggle (recommended)

1. Create a Kaggle Notebook with a free GPU accelerator (for example, T4 or P100) and enable Internet so torchvision can fetch the pretrained MobileNetV2 weights if they are not cached.
2. Make the repository available in the notebook. Clone the repository if it is accessible to Kaggle, or upload a repository ZIP as a Kaggle input and extract it under `/kaggle/working/AgriSense`:

   ```bash
   git clone --depth 1 https://github.com/sambitkarmakar03/AgriSense.git /kaggle/working/AgriSense
   ```

3. In the notebook's **Add Input** panel, attach the PlantVillage dataset. Kaggle typically mounts it under `/kaggle/input/plantvillage-dataset`; the script searches that tree for the verified class folders and prefers `color/`.
4. Open and run `ml/train_kaggle.ipynb` from top to bottom. It installs the ML requirements, validates the mounted dataset, runs the training/export script with the 23-minute training budget, then packages the model, labels, and reports into `/kaggle/working/agrisense_phase3_artifacts.zip`.
5. Download that ZIP from the notebook's **Output** panel. The individual model and labels are also under `backend/app/ml/`, and reports are under `ml/reports/` in the Kaggle working copy.

You can run the same commands in notebook cells without the notebook wrapper:

```bash
python -m pip install -r ml/requirements.txt
python ml/train.py --dataset-root /kaggle/input/plantvillage-dataset --max-minutes 23
```

For future retraining runs, artifacts are installed only after training, evaluation, and five-image ONNX parity succeed. If validation or parity fails, the script exits without installing a new model/labels pair; inspect that run's timestamped reports before trying again.

## Backend inference

The CPU-only service in `backend/app/ml/inference.py` checks the ONNX graph metadata, `labels.json`, and dynamic tensor shapes when it loads the session. It converts grayscale/RGBA inputs to RGB, applies the same resize and ImageNet normalization, and returns the graph's softmax probabilities without applying another softmax. The authenticated `POST /fields/{field_id}/diagnose` endpoint stores the raw model result and an EXIF-free 224x224 JPEG thumbnail. Rule fusion, confidence-band assignment, and human review are still pending.

From the `backend/` directory, install `requirements.txt` and run `python -m app.ml.verify_model` for a synthetic-image smoke check. Use `python -m app.ml.verify_model --image /path/to/leaf.jpg` for a real image or repeat `--image` to check batching.
