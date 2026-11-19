# AgriSense specification

## 1. Purpose
Decision-support SaaS for a farmer. Two modules sharing one field profile:
(A) Smart Irrigation expert system (rule-based, explainable).
(B) Crop Disease Diagnosis (image model + expert rules + human referral).
The system is advisory. A human can always override. Not a substitute for an agronomist.

## 2. Roles
- farmer: manages own fields, readings, runs advice, uploads leaf photos, confirms/corrects results.
- agronomist: reviews referred diagnoses, edits rule thresholds (versioned), sees analytics.
First registered account may be promoted to agronomist via an ADMIN_EMAIL env var.

## 3. Repo layout
agrisense/
  AGENTS.md  render.yaml  .gitattributes (* text=auto eol=lf)
  docs/ SPEC.md PROGRESS.md DEPLOY.md openapi.json
  backend/  app/{main.py, api/, core/, db/, expert/, ml/}  tests/  alembic/  requirements.txt
    expert/{engine.py, irrigation_kb_v1.yaml, irrigation_kb_v2.yaml, disease_rules.yaml, treatments.yaml}
    ml/{infer.py, model.onnx, labels.json}
  ml/       training notebook/script (NOT deployed)
  frontend/ Vite + React + TypeScript + Tailwind
  scripts/  setup.py, dev.py (cross-platform: create venv, install, run both servers)
  .github/workflows/ci.yml  (ubuntu, macos, windows)

## 4. Expert-system architecture (map to the course)
- Knowledge base: YAML rule files, versioned, editable by agronomist. Not hard-coded.
- Inference engine: small custom forward-chaining engine in expert/engine.py. Rules have id, priority, conditions, action. Returns the list of fired rules.
- Working memory: the facts built from readings + forecast + crop stage + recent diagnosis.
- Explanation facility: every decision stores fired rules and a plain-language "why".
- Knowledge acquisition: rule editor page; each edit creates a new KB version with author and timestamp.
- Feedback: overrides, confirmations and corrections are stored and shown in analytics.
- System identification (show on an About page): inputs, outputs, processor, feedback, interfaces, boundary, environment.

## 5. Irrigation module
Inputs: soil_moisture_pct, rain_forecast_mm_24h, temp_c, humidity_pct, crop_stage.
Derived categories (thresholds live in the KB file):
- moisture: Low < 30, Medium 30-60, High > 60
- rain: none < 1 mm, light 1-10 mm, heavy > 10 mm
- hot: temp_c > 36
- crop_stage: Seedling, Vegetative, Flowering, Fruiting
Outputs: action ON/OFF, duration_level (normal | increased | short | low_volume), explanation, needs_review flag, decision_type (structured | semi-structured).
KB v1 = the original assignment rules:
  IR-1 Low moisture AND rain none -> ON
  IR-2 rain heavy -> OFF (priority 1, beats everything)
  IR-3 Flowering AND hot AND action ON -> duration increased
KB v2 = v1 plus the gap-closing rules:
  IR-4 Medium moisture AND rain none AND hot -> ON, duration short
  IR-5 Low moisture AND rain light AND Seedling -> ON, duration low_volume
  IR-6 recent fungal diagnosis (Powdery Mildew, Blight or Rust within 7 days) AND humidity > 80 AND action ON -> keep action, add advisory "avoid overhead or evening watering; prefer drip"
If no rule fires: action OFF, needs_review = true, decision_type = semi-structured, explanation says the knowledge base has no rule for this case.
Golden tests (must pass):
  Mon: Low, none, 39C, Flowering -> ON, increased, fired IR-1 + IR-3
  Tue: High, heavy, 31C, Vegetative -> OFF, fired IR-2
  Wed: Medium, none, 37C, Fruiting -> v1: OFF + needs_review; v2: ON short (IR-4)
  Thu: Low, light, 35C, Seedling -> v1: OFF + needs_review; v2: ON low_volume (IR-5)

## 6. Disease module
Classes: Leaf Blight, Rust, Powdery Mildew, Healthy.
Model: MobileNetV2 transfer learning, exported to int8 ONNX, served with onnxruntime. Input 224x224. Output softmax probabilities.
Explainability: occlusion-sensitivity heatmap computed with onnxruntime (no torch). Keep it under 3 seconds on CPU by using a coarse grid.
Fusion rules (disease_rules.yaml), applied to CNN label + latest environment reading + field history:
  DR-1 CNN=Powdery Mildew AND humidity > 80 -> confirm
  DR-2 CNN=Rust AND humidity > 70 -> confirm
  DR-3 CNN=Leaf Blight AND humidity > 85 AND temp 20-30 -> confirm
  DR-4 CNN=Healthy AND confidence >= 0.60 -> Healthy
  DR-5 field had Rust before AND CNN=Rust AND humidity > 75 -> confidence band High
  DR-6 CNN=Leaf Blight AND soil_moisture > 80 -> add advice: check drainage and inspect field
  DR-7 CNN confidence < 0.60 OR two rules conflict -> status referred: ask for clearer photo, add to agronomist review queue
Confidence band: High (model + rule agree), Medium (model >= 0.60, environment data missing or only partial agreement), Low -> referred.
Treatment advice comes from treatments.yaml. It must be generic and conservative, never give pesticide dosages, always say "confirm with an agronomist before applying any chemical".
User can confirm, correct (pick the right class) or refer. Corrections are stored for future retraining.
Images: validate type and size (max 5 MB), strip EXIF/GPS, downscale to 224px JPEG, store the small thumbnail in Postgres (never on the host disk).

## 7. Data model (SQLAlchemy 2 + Alembic; Postgres on Neon, SQLite for local dev via DATABASE_URL)
users, fields(user_id, name, crop, crop_stage, lat, lon), readings(field_id, ts, soil_moisture_pct, temp_c, humidity_pct, source: manual|csv|weather),
irrigation_decisions(field_id, ts, kb_version, inputs_json, fired_rules_json, action, duration_level, explanation, needs_review, decision_type, override_action, override_note),
diagnoses(field_id, ts, thumb_bytes, cnn_probs_json, cnn_label, cnn_confidence, fired_rules_json, final_label, confidence_band, status: auto|confirmed|corrected|referred|reviewed, corrected_label, reviewer_id, advice),
kb_versions(kind, version, yaml_text, author_id, ts), consent_log(user_id, ts, text_version).

## 8. API (FastAPI, JWT auth, publish docs/openapi.json)
POST /auth/register  POST /auth/login  GET /me
GET,POST /fields  GET,PUT,DELETE /fields/{id}
POST /fields/{id}/readings  POST /fields/{id}/readings/csv  GET /fields/{id}/readings
GET /fields/{id}/weather   (Open-Meteo proxy with graceful fallback when offline)
POST /fields/{id}/irrigation/decide  GET /fields/{id}/irrigation/history  POST /irrigation/{id}/override
POST /fields/{id}/diagnose (multipart)  POST /diagnoses/{id}/feedback  GET /fields/{id}/diagnoses
GET /review-queue (agronomist)  POST /diagnoses/{id}/review
GET,PUT /kb/{kind}  GET /kb/{kind}/versions
GET /analytics  GET /health  GET /about/system

## 9. Frontend pages
Register/Login (with consent text and privacy notice), Dashboard (fields, latest advice, weather), Field detail (readings chart + history), Irrigation advisor (run, see "Why?", override), Diagnose (upload or camera, result with confidence band, heatmap, advice, confirm/correct/refer), Review queue, Rule editor (diff between versions), Analytics (override rate, correction rate, confusion matrix from feedback), About this system, Limitations and ethics.
Mobile-first, light/dark mode, accessible (labels, contrast, keyboard), "waking server" banner when the API is cold.

## 10. Non-functional
- Runs locally on Windows and macOS: `python scripts/setup.py` then `python scripts/dev.py`.
- CI passes on ubuntu, macOS and windows.
- Security: password hashing (argon2 or bcrypt), JWT with expiry, CORS allowlist, rate-limit uploads, secrets only in env.
- Privacy: collect minimum data, consent logged, DPDP Act 2023 notice, EXIF stripped, user can delete account and data.
- Honesty: Limitations page states lab-image training data, only four classes, region-specific thresholds, advisory use only.

## 11. Definition of done
All golden tests pass (KB v1 and v2). Diagnosis flow works end to end with referral path. Live URLs for frontend and API. CI green on 3 OSes. README with screenshots. docs/DEPLOY.md.
