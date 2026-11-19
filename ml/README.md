# AgriSense crop disease training

This directory contains the Phase 3 training and export pipeline for a four-class crop leaf classifier. It fine-tunes an ImageNet-pretrained MobileNetV2 in PyTorch, evaluates the held-out test set, exports a static quantized int8 ONNX model, and checks ONNX Runtime parity against PyTorch on five test images.

No training has been run in this repository yet. There is no dataset or usable training GPU in the current development environment, so no model, labels file, or evaluation report is claimed as generated. A successful run writes the actual artifacts to `backend/app/ml/model.onnx`, `backend/app/ml/labels.json`, and a timestamped directory under `ml/reports/`.

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

Use Python 3.11 or newer and a CUDA-enabled PyTorch installation for practical training speed. Install the ML dependencies in a dedicated environment; these requirements are separate from the backend runtime:

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

Training and export must complete successfully before model artifacts exist. If validation or five-image ONNX parity fails, the script exits with an error and does not install a new model/labels pair; inspect the timestamped run reports before trying again.
