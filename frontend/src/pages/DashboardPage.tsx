import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, ArrowDownRight, ArrowRight, ArrowUpRight, CloudDrizzle, Droplets, Leaf, MapPin, Sprout, Thermometer, Wind } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Decision, Field, Reading, Weather } from "../api/client";
import { EmptyState, ErrorState, LoadingState, PageTitle, Panel } from "../components/States";

interface FieldSnapshot {
  field: Field;
  readings: Reading[];
  weather: Weather | null;
  decisions: Decision[];
}

interface ActivityItem {
  id: string;
  field: Field;
  timestamp: string;
  label: string;
  detail: string;
  kind: "reading" | "decision";
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value));
}

function MetricCard({ label, value, unit, icon: Icon, detail, tone }: { label: string; value: string; unit?: string; icon: typeof Droplets; detail: string; tone: string }) {
  return <article className="metric-card"><div className="metric-top"><span className={`metric-icon ${tone}`}><Icon className="h-[18px] w-[18px]" aria-hidden="true" /></span><span className="metric-label">{label}</span></div><div className="metric-value">{value}<small>{unit}</small></div><p className="metric-detail">{detail}</p></article>;
}

export function DashboardPage() {
  const [fields, setFields] = useState<Field[]>([]);
  const [snapshots, setSnapshots] = useState<FieldSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const fieldList = await api.listFields();
      setError("");
      setFields(fieldList);
      const results: FieldSnapshot[] = [];
      for (let index = 0; index < fieldList.length; index += 4) {
        const batch = fieldList.slice(index, index + 4);
        const current = await Promise.all(batch.map(async (field) => {
          const [readings, weather, decisions] = await Promise.all([
            api.getReadings(field.id, 2).catch(() => []),
            api.getWeather(field.id).catch(() => null),
            api.getIrrigationHistory(field.id, 3).catch(() => []),
          ]);
          return { field, readings, weather, decisions };
        }));
        results.push(...current);
      }
      setSnapshots(results);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Your farm overview could not be loaded.");
    } finally { setLoading(false); }
  }, []);

  function retry() { setLoading(true); setError(""); void load(); }

  useEffect(() => { void load(); }, [load]);

  const latestReading = useMemo(() => snapshots.flatMap((snapshot) => snapshot.readings).sort((a, b) => b.ts.localeCompare(a.ts))[0], [snapshots]);
  const recentDecisions = useMemo(() => snapshots.flatMap((snapshot) => snapshot.decisions.map((decision) => ({ decision, field: snapshot.field }))).sort((a, b) => b.decision.ts.localeCompare(a.decision.ts)), [snapshots]);
  const activities = useMemo<ActivityItem[]>(() => snapshots.flatMap((snapshot) => [
    ...snapshot.readings.map((reading) => ({ id: `reading-${reading.id}`, field: snapshot.field, timestamp: reading.ts, label: "Sensor reading added", detail: `${reading.soil_moisture_pct}% soil moisture · ${reading.source}`, kind: "reading" as const })),
    ...snapshot.decisions.map((decision) => ({ id: `decision-${decision.id}`, field: snapshot.field, timestamp: decision.ts, label: `Irrigation advice: ${decision.action}`, detail: decision.override_action ? `Adjusted to ${decision.override_action} by you` : `Knowledge base ${decision.kb_version}`, kind: "decision" as const })),
  ]).sort((a, b) => b.timestamp.localeCompare(a.timestamp)).slice(0, 5), [snapshots]);

  const weatherField = snapshots.find((snapshot) => snapshot.weather)?.field;
  const activeWeather = snapshots.find((snapshot) => snapshot.field.id === weatherField?.id)?.weather ?? null;
  const currentTemp = activeWeather?.temp_c ?? latestReading?.temp_c ?? null;
  const currentHumidity = activeWeather?.humidity_pct ?? latestReading?.humidity_pct ?? null;
  const freshestDecision = recentDecisions[0];

  return <>
    <PageTitle eyebrow="FIELD OPERATIONS · TODAY" title="A clear view of your farm." description="Your fields, conditions, and the latest irrigation guidance at a glance." action={<Link to="/fields" className="button button-secondary"><Sprout className="h-4 w-4" /> Manage fields</Link>} />
    {error && <ErrorState message={error} onRetry={retry} />}
    {loading ? <LoadingState label="Gathering your latest field conditions" /> : error ? null : fields.length === 0 ? <EmptyState title="Start with the fields you know best" message="Create your first field to see crop conditions, weather, and irrigation guidance here." action={<Link className="button button-primary" to="/fields">Add your first field <ArrowRight className="h-4 w-4" /></Link>} /> : <>
      <div className="metric-grid">
        <MetricCard label="Registered fields" value={String(fields.length).padStart(2, "0")} icon={Sprout} detail="Across your workspace" tone="tone-green" />
        <MetricCard label="Latest soil moisture" value={latestReading ? String(Math.round(latestReading.soil_moisture_pct)) : "—"} unit={latestReading ? "%" : ""} icon={Droplets} detail={latestReading ? `${snapshots.find((snapshot) => snapshot.readings.includes(latestReading))?.field.name ?? "Field"} · ${formatDate(latestReading.ts)}` : "Add a sensor reading"} tone="tone-blue" />
        <MetricCard label="Current temperature" value={currentTemp == null ? "—" : currentTemp.toFixed(1)} unit={currentTemp == null ? "" : "°C"} icon={Thermometer} detail={weatherField ? `Forecast for ${weatherField.name}` : "No weather location yet"} tone="tone-amber" />
        <MetricCard label="Relative humidity" value={currentHumidity == null ? "—" : String(Math.round(currentHumidity))} unit={currentHumidity == null ? "" : "%"} icon={Wind} detail={activeWeather?.status === "fallback" ? "Using latest sensor data" : "Latest available weather"} tone="tone-violet" />
      </div>

      <div className="dashboard-feature-grid">
        <Panel className="recommendation-panel" title="Latest irrigation guidance" subtitle={freshestDecision ? `${freshestDecision.field.name} · ${formatDate(freshestDecision.decision.ts)}` : "Based on your recorded field conditions"} action={<Link to="/irrigation" className="subtle-link">Open advisor <ArrowRight className="h-3.5 w-3.5" /></Link>}>
          {freshestDecision ? <div className="recommendation-content">
            <div className={`recommendation-state recommendation-${freshestDecision.decision.override_action ?? freshestDecision.decision.action}`}><span className="recommendation-state-label">RECOMMENDATION</span><strong>{(freshestDecision.decision.override_action ?? freshestDecision.decision.action) === "ON" ? "Water the field" : "Keep irrigation off"}</strong><span>{freshestDecision.decision.override_action ? "Farmer override" : `Duration · ${freshestDecision.decision.duration_level.replace("_", " ")}`}</span></div>
            <div className="recommendation-explanation"><span className="recommendation-rule-count">{freshestDecision.decision.fired_rules_json.length ? `${freshestDecision.decision.fired_rules_json.length} rule${freshestDecision.decision.fired_rules_json.length > 1 ? "s" : ""} matched` : "Needs a field review"}</span><p>{freshestDecision.decision.explanation}</p><Link to={`/irrigation?field=${freshestDecision.field.id}`} className="text-link">See why this was suggested <ArrowRight className="h-3.5 w-3.5" /></Link></div>
          </div> : <div className="recommendation-empty"><span className="empty-recommendation-icon"><Leaf className="h-5 w-5" /></span><div><strong>No advice recorded yet</strong><p>Add a reading and run the irrigation advisor to see a recommendation here.</p></div><Link to="/irrigation" className="button button-primary button-small">Open advisor <ArrowRight className="h-3.5 w-3.5" /></Link></div>}
          <div className="advisory-note"><span className="advisory-dot" /> Advice is a decision aid. Check local conditions before acting.</div>
        </Panel>

        <Panel className="weather-panel" title="Weather outlook" subtitle={weatherField ? <><MapPin className="inline h-3 w-3" /> {weatherField.name}</> : "Field forecast"} action={<CloudDrizzle className="weather-heading-icon h-4 w-4" aria-hidden="true" />}>
          {activeWeather ? <div className="weather-content">
            <div className="weather-main"><div className="weather-sun" aria-hidden="true"><span /></div><div><span className="weather-value">{activeWeather.temp_c == null ? "—" : `${activeWeather.temp_c.toFixed(1)}°`}</span><span className="weather-caption">{activeWeather.status === "ok" ? "Current conditions" : "Latest available"}</span></div></div>
            <div className="weather-stats"><div><Wind className="h-4 w-4" /><span>Humidity</span><strong>{activeWeather.humidity_pct == null ? "—" : `${Math.round(activeWeather.humidity_pct)}%`}</strong></div><div><CloudDrizzle className="h-4 w-4" /><span>Rain · 24h</span><strong>{activeWeather.rain_forecast_mm_24h == null ? "—" : `${activeWeather.rain_forecast_mm_24h.toFixed(1)} mm`}</strong></div></div>
            {activeWeather.warning && <p className="weather-warning">{activeWeather.warning}</p>}
          </div> : <div className="weather-unavailable"><CloudDrizzle className="h-6 w-6" /><p>Set field coordinates to get a local forecast.</p><Link to={weatherField ? `/fields/${weatherField.id}` : "/fields"}>Review field location <ArrowRight className="h-3.5 w-3.5" /></Link></div>}
        </Panel>
      </div>

      <div className="dashboard-lower-grid">
        <Panel title="Recent field activity" subtitle="Readings and irrigation decisions across your fields" action={<span className="live-indicator"><span className="status-dot" /> LIVE</span>}>
          {activities.length ? <div className="activity-list">{activities.map((activity) => <div className="activity-row" key={activity.id}><span className={`activity-icon ${activity.kind === "reading" ? "activity-reading" : "activity-decision"}`}>{activity.kind === "reading" ? <Droplets className="h-4 w-4" /> : <Activity className="h-4 w-4" />}</span><div className="activity-copy"><strong>{activity.label}</strong><span><Link to={`/fields/${activity.field.id}`}>{activity.field.name}</Link> <span className="activity-separator">·</span> {activity.detail}</span></div><time dateTime={activity.timestamp}>{formatDate(activity.timestamp)}</time></div>)}</div> : <EmptyState title="No recent activity" message="New sensor readings and decisions will appear here." />}
        </Panel>

        <Panel title="Field snapshot" subtitle={`${fields.length} field${fields.length === 1 ? "" : "s"} in your workspace`} action={<Link to="/fields" className="text-link">View all <ArrowRight className="h-3.5 w-3.5" /></Link>}>
          <div className="snapshot-list">{fields.slice(0, 5).map((field) => {
            const snapshot = snapshots.find((item) => item.field.id === field.id);
            const moisture = snapshot?.readings[0]?.soil_moisture_pct;
            const decision = snapshot?.decisions[0];
            return <Link className="snapshot-row" to={`/fields/${field.id}`} key={field.id}><span className="snapshot-plant"><Sprout className="h-4 w-4" /></span><span className="snapshot-main"><strong>{field.name}</strong><small>{field.crop} <span>·</span> {field.crop_stage}</small></span><span className="snapshot-moisture"><span>SOIL</span><strong>{moisture == null ? "—" : `${Math.round(moisture)}%`}</strong></span><span className={`snapshot-trend ${moisture != null && moisture < 30 ? "trend-low" : ""}`}>{moisture != null && moisture < 30 ? <ArrowDownRight className="h-4 w-4" /> : <ArrowUpRight className="h-4 w-4" />}</span><span className="sr-only">Latest decision: {decision ? decision.action : "none"}</span></Link>;
          })}</div>
          {fields.length > 5 && <Link className="snapshot-more" to="/fields">+ {fields.length - 5} more field{fields.length - 5 > 1 ? "s" : ""} <ArrowRight className="h-3.5 w-3.5" /></Link>}
        </Panel>
      </div>
    </>}
  </>;
}
