import type { AgriSenseApi, Decision, Field, Reading, TokenResponse, User } from "./client";

const demoUser: User = {
  id: 1,
  email: "farmer@example.test",
  full_name: "Asha Farmer",
  role: "farmer",
  created_at: new Date().toISOString(),
};

const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();
let nextFieldId = 4;
let nextReadingId = 4;
let nextDecisionId = 3;

const fields: Field[] = [
  { id: 1, user_id: 1, name: "North Meadow", crop: "Tomato", crop_stage: "Flowering", lat: 18.5204, lon: 73.8567, created_at: minutesAgo(60 * 24 * 12) },
  { id: 2, user_id: 1, name: "River Plot", crop: "Rice", crop_stage: "Vegetative", lat: 18.531, lon: 73.84, created_at: minutesAgo(60 * 24 * 8) },
  { id: 3, user_id: 1, name: "East Orchard", crop: "Mango", crop_stage: "Fruiting", lat: null, lon: null, created_at: minutesAgo(60 * 24 * 4) },
];

const readings: Reading[] = [
  { id: 1, field_id: 1, ts: minutesAgo(28), soil_moisture_pct: 26, temp_c: 34, humidity_pct: 68, source: "manual" },
  { id: 2, field_id: 2, ts: minutesAgo(92), soil_moisture_pct: 47, temp_c: 31, humidity_pct: 74, source: "csv" },
  { id: 3, field_id: 3, ts: minutesAgo(60 * 24), soil_moisture_pct: 68, temp_c: 29, humidity_pct: 61, source: "manual" },
];

const decisions: Decision[] = [
  {
    id: 1, field_id: 1, ts: minutesAgo(24), kb_version: "v2", inputs_json: { soil_moisture_pct: 26, rain_forecast_mm_24h: 0, temp_c: 34, humidity_pct: 68, crop_stage: "Flowering" },
    fired_rules_json: ["IR-1"], action: "ON", duration_level: "normal", explanation: "Demo mode: low soil moisture and no forecast rain suggest irrigation.", needs_review: false, decision_type: "structured", override_action: null, override_note: null,
  },
  {
    id: 2, field_id: 2, ts: minutesAgo(60 * 24 * 2), kb_version: "v2", inputs_json: { soil_moisture_pct: 47, rain_forecast_mm_24h: 12, temp_c: 31, humidity_pct: 74, crop_stage: "Vegetative" },
    fired_rules_json: ["IR-2"], action: "OFF", duration_level: "normal", explanation: "Demo mode: heavy forecast rain takes priority, so irrigation stays off.", needs_review: false, decision_type: "structured", override_action: null, override_note: null,
  },
];

function latestReading(fieldId: number): Reading | undefined {
  return readings.filter((item) => item.field_id === fieldId).sort((a, b) => b.ts.localeCompare(a.ts))[0];
}

function makeReading(fieldId: number, body: { soil_moisture_pct: number; temp_c: number; humidity_pct: number; ts?: string | null }, source = "manual"): Reading {
  const reading: Reading = {
    id: nextReadingId++,
    field_id: fieldId,
    ts: body.ts ?? new Date().toISOString(),
    soil_moisture_pct: body.soil_moisture_pct,
    temp_c: body.temp_c,
    humidity_pct: body.humidity_pct,
    source,
  };
  readings.push(reading);
  return reading;
}

const mockApi: AgriSenseApi = {
  async health() { return { status: "ok" }; },
  async register(body) {
    if (!body.consent_accepted) throw new Error("Please accept the privacy notice to create an account.");
    return { access_token: "demo-session-token", token_type: "bearer", user: { ...demoUser, email: body.email, full_name: body.full_name ?? null } };
  },
  async login(body) {
    if (!body.email || !body.password) throw new Error("Enter your email and password.");
    return { access_token: "demo-session-token", token_type: "bearer", user: { ...demoUser, email: body.email } } satisfies TokenResponse;
  },
  async me() { return demoUser; },
  async listFields() { return [...fields]; },
  async getField(fieldId) {
    const field = fields.find((item) => item.id === fieldId);
    if (!field) throw new Error("Field not found.");
    return field;
  },
  async createField(body) {
    const field: Field = { id: nextFieldId++, user_id: demoUser.id, ...body, lat: body.lat ?? null, lon: body.lon ?? null, created_at: new Date().toISOString() };
    fields.push(field);
    return field;
  },
  async updateField(fieldId, body) {
    const field = fields.find((item) => item.id === fieldId);
    if (!field) throw new Error("Field not found.");
    Object.assign(field, body);
    return field;
  },
  async deleteField(fieldId) {
    const fieldIndex = fields.findIndex((item) => item.id === fieldId);
    if (fieldIndex < 0) throw new Error("Field not found.");
    fields.splice(fieldIndex, 1);
    for (let index = readings.length - 1; index >= 0; index -= 1) if (readings[index].field_id === fieldId) readings.splice(index, 1);
    for (let index = decisions.length - 1; index >= 0; index -= 1) if (decisions[index].field_id === fieldId) decisions.splice(index, 1);
  },
  async getReadings(fieldId, limit = 100) {
    return readings.filter((item) => item.field_id === fieldId).sort((a, b) => b.ts.localeCompare(a.ts)).slice(0, limit);
  },
  async createReading(fieldId, body) { return makeReading(fieldId, body); },
  async uploadReadingsCsv(fieldId, file) {
    const rows = (await file.text()).trim().split(/\r?\n/);
    const headers = rows.shift()?.split(",").map((value) => value.trim()) ?? [];
    const index = (name: string) => headers.indexOf(name);
    const values = rows[0]?.split(",").map((value) => value.trim());
    if (!values || index("soil_moisture_pct") < 0 || index("temp_c") < 0 || index("humidity_pct") < 0) {
      throw new Error("CSV needs soil_moisture_pct, temp_c, and humidity_pct columns.");
    }
    const reading = makeReading(fieldId, {
      soil_moisture_pct: Number(values[index("soil_moisture_pct")]),
      temp_c: Number(values[index("temp_c")]),
      humidity_pct: Number(values[index("humidity_pct")]),
      ts: index("ts") >= 0 ? values[index("ts")] : undefined,
    }, "csv");
    return { imported: 1, readings: [reading] };
  },
  async getWeather(fieldId) {
    const reading = latestReading(fieldId);
    const field = fields.find((item) => item.id === fieldId);
    return {
      field_id: fieldId,
      status: field?.lat == null ? "fallback" : "ok",
      source: field?.lat == null ? "latest_reading" : "demo preview",
      temp_c: reading?.temp_c ?? null,
      humidity_pct: reading?.humidity_pct ?? null,
      rain_forecast_mm_24h: field?.lat == null ? null : 1.4,
      warning: field?.lat == null ? "Demo preview: field coordinates are missing, so forecast rain is unavailable." : null,
    };
  },
  async decideIrrigation(fieldId, body) {
    const field = fields.find((item) => item.id === fieldId);
    const reading = latestReading(fieldId);
    if (!field || !reading) throw new Error("Add a sensor reading before running an irrigation decision.");
    const soil = body.soil_moisture_pct ?? reading.soil_moisture_pct;
    const temperature = body.temp_c ?? reading.temp_c;
    const humidity = body.humidity_pct ?? reading.humidity_pct;
    const rain = body.rain_forecast_mm_24h ?? 0;
    const fired: string[] = [];
    let action: Decision["action"] = "OFF";
    let duration: Decision["duration_level"] = "normal";
    if (rain > 10) fired.push("IR-2");
    else if (soil < 30 && rain < 1) {
      action = "ON";
      fired.push("IR-1");
    } else if (soil >= 30 && soil <= 60 && rain < 1 && temperature > 36) {
      action = "ON";
      duration = "short";
      fired.push("IR-4");
    } else if (soil < 30 && rain >= 1 && rain <= 10 && field.crop_stage === "Seedling") {
      action = "ON";
      duration = "low_volume";
      fired.push("IR-5");
    }
    if (action === "ON" && field.crop_stage === "Flowering" && temperature > 36) {
      duration = "increased";
      fired.push("IR-3");
    }
    const decision: Decision = {
      id: nextDecisionId++, field_id: fieldId, ts: new Date().toISOString(), kb_version: "v2",
      inputs_json: { soil_moisture_pct: soil, rain_forecast_mm_24h: rain, temp_c: temperature, humidity_pct: humidity, crop_stage: field.crop_stage },
      fired_rules_json: fired, action, duration_level: duration,
      explanation: fired.length ? `Demo mode: ${fired.join(" and ")} matched the current field conditions.` : "Demo mode: no packaged rule matched these conditions; review the field before acting.",
      needs_review: fired.length === 0, decision_type: fired.length ? "structured" : "semi-structured", override_action: null, override_note: null,
    };
    decisions.push(decision);
    return decision;
  },
  async getIrrigationHistory(fieldId, limit = 100) {
    return decisions.filter((item) => item.field_id === fieldId).sort((a, b) => b.ts.localeCompare(a.ts)).slice(0, limit);
  },
  async overrideIrrigation(decisionId, body) {
    const decision = decisions.find((item) => item.id === decisionId);
    if (!decision) throw new Error("Irrigation decision not found.");
    decision.override_action = body.override_action;
    decision.override_note = body.override_note ?? null;
    return decision;
  },
  async getKnowledgeBase(kind) {
    if (kind !== "irrigation") throw new Error("Knowledge base not found.");
    return { kind, version: "v2", yaml_text: "# Demo preview; the live knowledge base is read from the API.", author_id: null, ts: null };
  },
  async getAboutSystem() {
    return {
      inputs: ["Field crop and growth stage", "Soil moisture and environmental readings", "24-hour weather forecast"],
      outputs: ["Irrigation ON/OFF", "Duration level", "Fired-rule trace and explanation"],
      processor: ["YAML-versioned knowledge base", "Forward-chaining inference engine"],
      feedback: ["Farmer irrigation overrides and notes"],
      interfaces: ["Farmer web client", "FastAPI JSON API"],
      boundary: "Advice is decision support only and does not replace local judgment or an agronomist.",
      environment: ["Field conditions", "Weather services", "SQLite or PostgreSQL"],
    };
  },
};

export { mockApi };
