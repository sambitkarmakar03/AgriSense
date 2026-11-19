import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { AlertCircle, ArrowRight, Check, ChevronDown, Clock3, Droplets, Info, Leaf, Play, RotateCcw, Sprout, Thermometer, Wind } from "lucide-react";
import { api } from "../api/client";
import type { Decision, DecisionRequest, Field, KnowledgeBase, Reading, Weather } from "../api/client";
import { EmptyState, ErrorState, LoadingState, Modal, PageTitle, Panel } from "../components/States";

const ruleCopy: Record<string, { title: string; farmerText: string }> = {
  "IR-1": { title: "Dry soil, little rain expected", farmerText: "Soil moisture is low and the forecast has less than 1 mm of rain, so watering can help." },
  "IR-2": { title: "Heavy rain is expected", farmerText: "More than 10 mm of rain is forecast. The system keeps irrigation off to avoid adding water." },
  "IR-3": { title: "Flowering crop in hot weather", farmerText: "The crop is flowering and the temperature is above 36°C, so the suggested watering duration is increased." },
  "IR-4": { title: "Medium moisture, hot and dry", farmerText: "The soil has medium moisture, little rain is expected, and it is hot. The suggestion is a short watering period." },
  "IR-5": { title: "Young crop with light rain", farmerText: "The soil is dry, light rain is forecast, and the crop is at the seedling stage. The suggestion is low-volume watering." },
  "IR-6": { title: "Recent fungal diagnosis and humid air", farmerText: "A recent fungal diagnosis and high humidity trigger a reminder to avoid overhead or evening watering and prefer drip irrigation." },
};

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function OverrideForm({ decision, busy, onSave }: { decision: Decision; busy: boolean; onSave: (action: "ON" | "OFF", reason: string) => Promise<void> }) {
  const [action, setAction] = useState<"ON" | "OFF">(decision.override_action ?? (decision.action === "ON" ? "OFF" : "ON"));
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (reason.trim().length < 4) {
      setError("Add a short reason so the decision history has useful context.");
      return;
    }
    setError("");
    try { await onSave(action, reason.trim()); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Your override could not be saved."); }
  }

  return <form className="stack-form" onSubmit={submit}>
    {error && <div className="form-alert" role="alert">{error}</div>}
    <p className="override-intro">You remain in control. Your choice and reason will be saved with this irrigation decision.</p>
    <label className="field-label" htmlFor="override-action">Your irrigation choice</label>
    <select id="override-action" className="form-input form-select" value={action} onChange={(event) => setAction(event.target.value as "ON" | "OFF")}><option value="ON">Turn irrigation ON</option><option value="OFF">Keep irrigation OFF</option></select>
    <label className="field-label" htmlFor="override-reason">Reason for changing the advice</label>
    <textarea id="override-reason" className="form-input form-textarea" value={reason} onChange={(event) => setReason(event.target.value)} rows={3} maxLength={1000} required placeholder="For example: I checked the soil and it is still damp." />
    <div className="modal-actions"><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save my choice"}</button></div>
  </form>;
}

export function IrrigationPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialId = Number(searchParams.get("field"));
  const [fields, setFields] = useState<Field[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(Number.isInteger(initialId) && initialId > 0 ? initialId : null);
  const [reading, setReading] = useState<Reading | null>(null);
  const [weather, setWeather] = useState<Weather | null>(null);
  const [history, setHistory] = useState<Decision[]>([]);
  const [knowledgeBase, setKnowledgeBase] = useState<KnowledgeBase | null>(null);
  const [activeDecision, setActiveDecision] = useState<Decision | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  const selectedField = fields.find((field) => field.id === selectedId) ?? null;

  const loadFields = useCallback(async () => {
    try {
      const values = await api.listFields();
      setError("");
      setFields(values);
      setSelectedId((current) => {
        if (current && values.some((field) => field.id === current)) return current;
        return values[0]?.id ?? null;
      });
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Your fields could not be loaded."); }
  }, []);

  useEffect(() => { void loadFields().finally(() => setLoading(false)); }, [loadFields]);

  useEffect(() => {
    if (selectedId == null) return;
    const fieldId = selectedId;
    Promise.all([
      api.getReadings(fieldId, 1).catch(() => []),
      api.getWeather(fieldId).catch(() => null),
      api.getIrrigationHistory(fieldId, 20).catch(() => []),
      api.getKnowledgeBase("irrigation").catch(() => null),
    ]).then(([readings, currentWeather, decisions, kb]) => {
      setError("");
      setReading(readings[0] ?? null);
      setWeather(currentWeather);
      setHistory(decisions);
      setKnowledgeBase(kb);
      setActiveDecision(decisions[0] ?? null);
      setSearchParams((params) => {
        params.set("field", String(fieldId));
        return params;
      }, { replace: true });
    }).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "Field conditions could not be loaded."))
      .finally(() => setLoading(false));
  }, [selectedId, refreshKey, setSearchParams]);

  function retry() {
    setLoading(true);
    setError("");
    if (selectedId == null) void loadFields();
    else setRefreshKey((value) => value + 1);
  }

  const conditionData = useMemo(() => [
    { label: "Soil moisture", value: reading ? `${reading.soil_moisture_pct.toFixed(0)}%` : "No reading", icon: Droplets, detail: reading ? `Recorded ${dateLabel(reading.ts)}` : "Add a sensor reading first" },
    { label: "Rain · next 24h", value: weather?.rain_forecast_mm_24h == null ? "Unavailable" : `${weather.rain_forecast_mm_24h.toFixed(1)} mm`, icon: CloudIcon, detail: weather?.source ?? "Forecast not available" },
    { label: "Temperature", value: (weather?.temp_c ?? reading?.temp_c) == null ? "Unavailable" : `${(weather?.temp_c ?? reading?.temp_c)?.toFixed(1)}°C`, icon: Thermometer, detail: weather?.status === "fallback" ? "Using latest sensor data" : "Latest available" },
    { label: "Humidity", value: (weather?.humidity_pct ?? reading?.humidity_pct) == null ? "Unavailable" : `${Math.round((weather?.humidity_pct ?? reading?.humidity_pct) ?? 0)}%`, icon: Wind, detail: weather?.status === "fallback" ? "Using latest sensor data" : "Latest available" },
  ], [reading, weather]);

  async function runAdvisor() {
    if (!selectedField) return;
    setError("");
    setNotice("");
    setRunning(true);
    const body: DecisionRequest = {};
    if (reading) {
      body.soil_moisture_pct = reading.soil_moisture_pct;
      body.temp_c = reading.temp_c;
      body.humidity_pct = reading.humidity_pct;
    }
    if (weather?.rain_forecast_mm_24h != null) body.rain_forecast_mm_24h = weather.rain_forecast_mm_24h;
    try {
      const result = await api.decideIrrigation(selectedField.id, body);
      setActiveDecision(result);
      setHistory((previous) => [result, ...previous.filter((item) => item.id !== result.id)]);
      if (weather?.rain_forecast_mm_24h == null && result.inputs_json.rain_forecast_mm_24h == null) {
        setNotice("Decision saved. No rain forecast was available, so the rule engine used the data it had.");
      } else setNotice("A new irrigation recommendation is ready.");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "The irrigation decision could not be completed."); }
    finally { setRunning(false); }
  }

  async function saveOverride(action: "ON" | "OFF", reason: string) {
    if (!activeDecision) return;
    setRunning(true);
    try {
      const result = await api.overrideIrrigation(activeDecision.id, { override_action: action, override_note: reason });
      setActiveDecision(result);
      setHistory((previous) => previous.map((item) => item.id === result.id ? result : item));
      setModalOpen(false);
      setNotice("Your choice and reason were added to the decision history.");
    } finally { setRunning(false); }
  }

  if (loading && !selectedField) return <LoadingState label="Opening the irrigation advisor" />;

  return <>
    <PageTitle eyebrow="EXPLAINABLE FIELD GUIDANCE" title="Irrigation advisor" description="Review current conditions, run a recommendation, and keep control of the final decision." action={fields.length > 0 ? <div className="advisor-field-select"><label className="sr-only" htmlFor="advisor-field">Choose a field</label><select id="advisor-field" className="form-input form-select" value={selectedId ?? ""} onChange={(event) => { const next = Number(event.target.value); setLoading(true); setError(""); setSelectedId(next); setActiveDecision(null); setSearchParams({ field: String(next) }); }}><option value="" disabled>Select a field</option>{fields.map((field) => <option key={field.id} value={field.id}>{field.name} · {field.crop}</option>)}</select><ChevronDown className="select-chevron h-4 w-4" aria-hidden="true" /></div> : undefined} />
    {error && <ErrorState message={error} onRetry={retry} />}
    {notice && <div className="success-banner" role="status"><Check className="h-4 w-4" />{notice}<button className="text-button" onClick={() => setNotice("")} aria-label="Dismiss message">×</button></div>}
    {fields.length === 0 && !loading && !error ? <EmptyState title="Add a field before asking for irrigation advice" message="The advisor uses each field’s crop stage and current conditions to evaluate the knowledge base." action={<Link to="/fields" className="button button-primary">Manage fields <ArrowRight className="h-4 w-4" /></Link>} /> : selectedField && <>
      {loading ? <LoadingState label="Refreshing field conditions" /> : <>
        <div className="advisor-context-bar"><div className="advisor-context-field"><span className="context-icon"><Sprout className="h-4 w-4" /></span><span><small>ADVISORY FOR</small><strong>{selectedField.name}</strong></span><span className="context-crop">{selectedField.crop} <span>·</span> {selectedField.crop_stage}</span></div><span className={`kb-version-pill ${knowledgeBase ? "" : "kb-version-muted"}`}><span className="status-dot" /> Knowledge base {activeDecision?.kb_version ?? knowledgeBase?.version ?? "unavailable"}</span></div>

        <Panel className="conditions-panel" title="Current field conditions" subtitle="These are the latest values the advisor can access" action={<Link to={`/fields/${selectedField.id}`} className="subtle-link">View readings <ArrowRight className="h-3.5 w-3.5" /></Link>}>
          <div className="condition-grid">{conditionData.map(({ label, value, icon: Icon, detail }) => <div className="condition-item" key={label}><span className="condition-icon"><Icon className="h-4 w-4" aria-hidden="true" /></span><div><small>{label}</small><strong>{value}</strong><span>{detail}</span></div></div>)}</div>
          {!reading && <div className="condition-missing"><Info className="h-4 w-4" /><span>No sensor reading is available. Add one before running a decision.</span><Link className="text-link" to={`/fields/${selectedField.id}`}>Add reading <ArrowRight className="h-3 w-3" /></Link></div>}
          {weather?.warning && <p className="weather-warning advisor-weather-warning">{weather.warning}</p>}
        </Panel>

        <div className="advisor-run-row"><div><strong>Ready to review?</strong><span>The advisor checks the current readings against the versioned irrigation rules.</span></div><button className="button button-primary advisor-run-button" onClick={() => void runAdvisor()} disabled={running || !reading}><Play className="h-4 w-4" fill="currentColor" />{running ? "Evaluating conditions…" : "Run irrigation decision"}</button></div>

        {activeDecision ? <div className="advisor-result-grid">
          <Panel className="decision-result-panel" title="Recommendation" subtitle={`Recorded ${dateLabel(activeDecision.ts)}`}>
            <div className={`decision-result decision-${activeDecision.override_action ?? activeDecision.action}`}><div className="decision-result-icon">{(activeDecision.override_action ?? activeDecision.action) === "ON" ? <Droplets className="h-6 w-6" /> : <Leaf className="h-6 w-6" />}</div><div><span>{activeDecision.override_action ? "YOUR OVERRIDE" : "SYSTEM SUGGESTION"}</span><strong>{(activeDecision.override_action ?? activeDecision.action) === "ON" ? "Irrigation ON" : "Irrigation OFF"}</strong><small>{activeDecision.override_action ? "Your decision is recorded." : `Duration level · ${activeDecision.duration_level.replace("_", " ")}`}</small></div></div>
            <div className="decision-meta-grid"><div><small>DURATION</small><strong>{activeDecision.duration_level.replace("_", " ")}</strong></div><div><small>DECISION TYPE</small><strong>{activeDecision.decision_type === "structured" ? "Rule-based" : "Needs review"}</strong></div><div><small>RULES FIRED</small><strong>{activeDecision.fired_rules_json.length || "None"}</strong></div></div>
            {activeDecision.needs_review && <div className="review-callout"><AlertCircle className="h-4 w-4" /><span>The current knowledge base does not have a rule for these conditions. Review the field before acting.</span></div>}
            <button className="button button-secondary button-full override-button" onClick={() => setModalOpen(true)}><RotateCcw className="h-4 w-4" /> Record a manual override</button>
          </Panel>

          <Panel className="why-panel" title="Why this decision?" subtitle="A plain-language view of the rules that matched">
            <div className="why-explanation"><span className="why-label">FIELD EXPLANATION</span><p>{activeDecision.explanation}</p></div>
            {activeDecision.fired_rules_json.length ? <div className="fired-rules">{activeDecision.fired_rules_json.map((ruleId) => <div className="fired-rule" key={ruleId}><span className="rule-id">{ruleId}</span><div><strong>{ruleCopy[ruleId]?.title ?? "Irrigation rule matched"}</strong><p>{ruleCopy[ruleId]?.farmerText ?? activeDecision.explanation}</p></div><Check className="rule-check h-4 w-4" aria-label="Rule fired" /></div>)}</div> : <div className="no-rules-fired"><span className="no-rule-mark">—</span><div><strong>No irrigation rule matched</strong><p>The knowledge base has no rule for this combination of conditions. Treat the result as a prompt for local review.</p></div></div>}
            <div className="decision-data-note"><Info className="h-4 w-4" /><span>Rule version <strong>{activeDecision.kb_version}</strong> · {activeDecision.inputs_json.crop_stage ? `Crop stage ${String(activeDecision.inputs_json.crop_stage)}` : `Field stage ${selectedField.crop_stage}`}</span></div>
          </Panel>
        </div> : <div className="advisor-first-run"><span className="advisor-first-icon"><Play className="h-5 w-5" /></span><div><strong>Your next irrigation decision starts with the latest reading.</strong><p>Run the advisor to see the suggested action, duration, matched rules, and a clear explanation.</p></div></div>}

        <Panel title="Decision history" subtitle="Recommendations and farmer overrides for this field" action={<span className="history-count"><Clock3 className="h-3.5 w-3.5" /> {history.length} records</span>}>
          {history.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th scope="col">Date</th><th scope="col">Suggestion</th><th scope="col">Duration</th><th scope="col">Knowledge base</th><th scope="col">Outcome</th></tr></thead><tbody>{history.map((decision) => <tr key={decision.id}><td>{dateLabel(decision.ts)}</td><td><span className={`table-action action-${decision.override_action ?? decision.action}`}>{decision.override_action ?? decision.action}</span></td><td>{decision.duration_level.replace("_", " ")}</td><td>{decision.kb_version}</td><td>{decision.override_action ? <span title={decision.override_note ?? "Farmer override"}>Overridden</span> : decision.needs_review ? "Review" : "Recommendation"}</td></tr>)}</tbody></table></div> : <div className="chart-empty">No decisions yet. Run the advisor to start this field’s history.</div>}
        </Panel>
      </>}
    </>}
    {modalOpen && activeDecision && <Modal title="Record your field decision" onClose={() => !running && setModalOpen(false)}><OverrideForm decision={activeDecision} busy={running} onSave={saveOverride} /></Modal>}
  </>;
}

function CloudIcon({ className }: { className?: string }) {
  return <Droplets className={className} aria-hidden="true" />;
}
