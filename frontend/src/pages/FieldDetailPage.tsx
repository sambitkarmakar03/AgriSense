import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, ArrowRight, CloudDrizzle, Droplets, MapPin, Thermometer, Upload, Wind } from "lucide-react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { Field, Reading, ReadingCreate, Weather } from "../api/client";
import { ErrorState, LoadingState, PageTitle, Panel } from "../components/States";

function ChartPanel({ title, unit, dataKey, color, readings }: { title: string; unit: string; dataKey: keyof Reading; color: string; readings: Reading[] }) {
  const data = useMemo(() => [...readings].reverse(), [readings]);
  return <Panel title={title} subtitle="Sensor history">
    {readings.length === 0 ? <div className="chart-empty">Add readings to see this trend.</div> : <div className="chart-wrap" role="img" aria-label={`${title} chart showing ${readings.length} readings`}>
      <ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ top: 8, right: 10, bottom: 0, left: -18 }}>
        <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="4 5" vertical={false} />
        <XAxis dataKey="ts" tickFormatter={(value: string) => new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" })} tick={{ fill: "var(--muted)", fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={22} />
        <YAxis unit={unit} tick={{ fill: "var(--muted)", fontSize: 11 }} tickLine={false} axisLine={false} width={48} />
        <Tooltip labelFormatter={(value) => new Date(String(value)).toLocaleString()} formatter={(value) => [`${Number(value).toFixed(1)}${unit}`, title]} contentStyle={{ borderRadius: 12, borderColor: "var(--border)", background: "var(--panel)" }} />
        <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2.5} dot={{ r: 3, fill: color, strokeWidth: 0 }} activeDot={{ r: 5, strokeWidth: 0 }} />
      </LineChart></ResponsiveContainer>
    </div>}
  </Panel>;
}

function ManualReadingForm({ onSave, busy }: { onSave: (reading: ReadingCreate) => Promise<void>; busy: boolean }) {
  const [moisture, setMoisture] = useState("");
  const [temperature, setTemperature] = useState("");
  const [humidity, setHumidity] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");
    const data: ReadingCreate = { soil_moisture_pct: Number(moisture), temp_c: Number(temperature), humidity_pct: Number(humidity) };
    try {
      await onSave(data);
      setMoisture(""); setTemperature(""); setHumidity("");
      setSuccess("Reading added to this field.");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Reading could not be saved."); }
  }

  return <Panel title="Add a manual reading" subtitle="Enter current sensor measurements">
    {error && <div className="form-alert" role="alert">{error}</div>}{success && <div className="form-success" role="status">{success}</div>}
    <form className="reading-form" onSubmit={submit}>
      <div><label className="field-label" htmlFor="soil-reading">Soil moisture (%)</label><input id="soil-reading" className="form-input" type="number" min="0" max="100" step="any" required value={moisture} onChange={(event) => setMoisture(event.target.value)} /></div>
      <div><label className="field-label" htmlFor="temp-reading">Temperature (°C)</label><input id="temp-reading" className="form-input" type="number" min="-80" max="70" step="any" required value={temperature} onChange={(event) => setTemperature(event.target.value)} /></div>
      <div><label className="field-label" htmlFor="humidity-reading">Humidity (%)</label><input id="humidity-reading" className="form-input" type="number" min="0" max="100" step="any" required value={humidity} onChange={(event) => setHumidity(event.target.value)} /></div>
      <button className="button button-primary reading-submit" type="submit" disabled={busy}>{busy ? "Saving…" : "Save reading"}</button>
    </form>
  </Panel>;
}

export function FieldDetailPage() {
  const route = useParams();
  const fieldId = Number(route.fieldId);
  const invalidFieldId = !Number.isInteger(fieldId) || fieldId < 1;
  const [field, setField] = useState<Field | null>(null);
  const [readings, setReadings] = useState<Reading[]>([]);
  const [weather, setWeather] = useState<Weather | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [csvMessage, setCsvMessage] = useState("");

  const load = useCallback(async () => {
    try {
      const loadedField = await api.getField(fieldId);
      setError("");
      setField(loadedField);
      const [loadedReadings, loadedWeather] = await Promise.all([
        api.getReadings(fieldId, 100).catch(() => []),
        api.getWeather(fieldId).catch(() => null),
      ]);
      setReadings(loadedReadings.sort((a, b) => b.ts.localeCompare(a.ts)));
      setWeather(loadedWeather);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "This field could not be loaded."); }
    finally { setLoading(false); }
  }, [fieldId]);

  useEffect(() => { if (!invalidFieldId) void load(); }, [invalidFieldId, load]);

  function retry() { setLoading(true); setError(""); void load(); }

  async function addReading(body: ReadingCreate) {
    setBusy(true);
    try { await api.createReading(fieldId, body); await load(); }
    finally { setBusy(false); }
  }

  async function uploadCsv(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setCsvMessage("");
    try {
      const result = await api.uploadReadingsCsv(fieldId, file);
      setCsvMessage(`${result.imported} reading${result.imported === 1 ? "" : "s"} imported.`);
      await load();
    } catch (caught) { setCsvMessage(caught instanceof Error ? caught.message : "CSV upload failed."); }
    finally { setBusy(false); }
  }

  if (invalidFieldId) return <><Link to="/fields" className="back-link"><ArrowLeft className="h-4 w-4" /> All fields</Link><ErrorState message="That field address is not valid." /></>;
  if (loading) return <LoadingState label="Loading field conditions" />;
  if (error && !field) return <><Link to="/fields" className="back-link"><ArrowLeft className="h-4 w-4" /> All fields</Link><ErrorState message={error} onRetry={retry} /></>;
  if (!field) return null;

  const newest = readings[0];
  return <>
    <Link to="/fields" className="back-link"><ArrowLeft className="h-4 w-4" /> All fields</Link>
    <PageTitle eyebrow={`${field.crop.toUpperCase()} · ${field.crop_stage.toUpperCase()}`} title={field.name} description={field.lat != null && field.lon != null ? `Field location · ${field.lat.toFixed(4)}, ${field.lon.toFixed(4)}` : "Add a location to get a local weather forecast."} action={<Link className="button button-primary" to={`/irrigation?field=${field.id}`}>Open irrigation advisor <ArrowRight className="h-4 w-4" /></Link>} />
    {error && <ErrorState message={error} onRetry={retry} />}
    <div className="field-summary-grid">
      <div className="field-summary-card"><span className="field-summary-icon summary-blue"><Droplets className="h-4 w-4" /></span><div><small>SOIL MOISTURE</small><strong>{newest ? `${newest.soil_moisture_pct.toFixed(0)}%` : "—"}</strong><span>{newest ? "Latest sensor reading" : "No reading yet"}</span></div></div>
      <div className="field-summary-card"><span className="field-summary-icon summary-amber"><Thermometer className="h-4 w-4" /></span><div><small>TEMPERATURE</small><strong>{newest ? `${newest.temp_c.toFixed(1)}°C` : weather?.temp_c == null ? "—" : `${weather.temp_c.toFixed(1)}°C`}</strong><span>{weather?.source ?? "Latest available"}</span></div></div>
      <div className="field-summary-card"><span className="field-summary-icon summary-violet"><Wind className="h-4 w-4" /></span><div><small>HUMIDITY</small><strong>{newest ? `${newest.humidity_pct.toFixed(0)}%` : weather?.humidity_pct == null ? "—" : `${weather.humidity_pct.toFixed(0)}%`}</strong><span>{weather?.status === "fallback" ? "Weather fallback" : "Latest available"}</span></div></div>
      <div className="field-summary-card"><span className="field-summary-icon summary-green"><MapPin className="h-4 w-4" /></span><div><small>RAIN · NEXT 24H</small><strong>{weather?.rain_forecast_mm_24h == null ? "—" : `${weather.rain_forecast_mm_24h.toFixed(1)} mm`}</strong><span>{weather?.status === "ok" ? "Open-Meteo forecast" : "Forecast unavailable"}</span></div></div>
    </div>
    {weather?.warning && <div className="weather-warning-banner"><CloudDrizzle className="h-4 w-4" />{weather.warning}</div>}

    <div className="chart-grid">
      <ChartPanel title="Soil moisture" unit="%" dataKey="soil_moisture_pct" color="#4c9261" readings={readings} />
      <ChartPanel title="Temperature" unit="°C" dataKey="temp_c" color="#d98548" readings={readings} />
      <ChartPanel title="Humidity" unit="%" dataKey="humidity_pct" color="#6385bb" readings={readings} />
    </div>

    <div className="detail-actions-grid">
      <ManualReadingForm busy={busy} onSave={addReading} />
      <Panel title="Import a sensor file" subtitle="Upload a CSV with field readings">
        <div className="csv-dropzone"><span className="csv-icon"><Upload className="h-5 w-5" /></span><p><strong>Choose a CSV file</strong><small>UTF-8 · up to 10 MB · timestamps are optional</small></p><label className="button button-secondary button-small">Browse files<input type="file" accept=".csv,text/csv" aria-label="Upload CSV sensor readings" onChange={(event) => { void uploadCsv(event.target.files?.[0]); event.target.value = ""; }} disabled={busy} /></label></div>
        <p className="csv-format-note">Required columns: <code>soil_moisture_pct</code>, <code>temp_c</code>, <code>humidity_pct</code>. Optional: <code>ts</code>.</p>
        {csvMessage && <div className={csvMessage.includes("imported") ? "form-success" : "form-alert"} role="status">{csvMessage}</div>}
      </Panel>
    </div>

    <Panel title="Sensor history" subtitle={`${readings.length} most recent readings`}>
      {readings.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th scope="col">Recorded</th><th scope="col">Soil moisture</th><th scope="col">Temperature</th><th scope="col">Humidity</th><th scope="col">Source</th></tr></thead><tbody>{readings.map((reading) => <tr key={reading.id}><td><time dateTime={reading.ts}>{new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(reading.ts))}</time></td><td><strong>{reading.soil_moisture_pct.toFixed(1)}%</strong></td><td>{reading.temp_c.toFixed(1)}°C</td><td>{reading.humidity_pct.toFixed(1)}%</td><td><span className="source-chip">{reading.source}</span></td></tr>)}</tbody></table></div> : <div className="chart-empty">No readings yet. Add a manual reading or import a CSV above.</div>}
    </Panel>
  </>;
}
