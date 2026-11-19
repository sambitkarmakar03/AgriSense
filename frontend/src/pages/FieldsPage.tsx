import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ArrowRight, MapPin, Pencil, Plus, Sprout, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Field, FieldCreate } from "../api/client";
import { EmptyState, ErrorState, LoadingState, Modal, PageTitle } from "../components/States";

const cropStages: Field["crop_stage"][] = ["Seedling", "Vegetative", "Flowering", "Fruiting"];

function FieldForm({ field, busy, onSave }: { field?: Field; busy: boolean; onSave: (body: FieldCreate) => Promise<void> }) {
  const [name, setName] = useState(field?.name ?? "");
  const [crop, setCrop] = useState(field?.crop ?? "");
  const [stage, setStage] = useState<Field["crop_stage"]>(field?.crop_stage ?? "Seedling");
  const [lat, setLat] = useState(field?.lat == null ? "" : String(field.lat));
  const [lon, setLon] = useState(field?.lon == null ? "" : String(field.lon));
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const latitude = lat.trim() ? Number(lat) : null;
    const longitude = lon.trim() ? Number(lon) : null;
    if ((latitude === null) !== (longitude === null)) {
      setError("Add both latitude and longitude, or leave both empty.");
      return;
    }
    if (latitude !== null && (latitude < -90 || latitude > 90)) {
      setError("Latitude must be between −90 and 90.");
      return;
    }
    if (longitude !== null && (longitude < -180 || longitude > 180)) {
      setError("Longitude must be between −180 and 180.");
      return;
    }
    try {
      await onSave({ name: name.trim(), crop: crop.trim(), crop_stage: stage, lat: latitude, lon: longitude });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "We could not save this field.");
    }
  }

  return <form className="stack-form" onSubmit={submit}>
    {error && <div className="form-alert" role="alert">{error}</div>}
    <label className="field-label" htmlFor="field-name">Field name</label>
    <input id="field-name" className="form-input" value={name} onChange={(event) => setName(event.target.value)} maxLength={120} required placeholder="e.g. North Meadow" />
    <div className="form-grid-two">
      <div><label className="field-label" htmlFor="field-crop">Crop</label><input id="field-crop" className="form-input" value={crop} onChange={(event) => setCrop(event.target.value)} maxLength={120} required placeholder="e.g. Tomato" /></div>
      <div><label className="field-label" htmlFor="crop-stage">Crop stage</label><select id="crop-stage" className="form-input form-select" value={stage} onChange={(event) => setStage(event.target.value as Field["crop_stage"])}>{cropStages.map((value) => <option key={value}>{value}</option>)}</select></div>
    </div>
    <div className="form-grid-two">
      <div><label className="field-label" htmlFor="latitude">Latitude <span className="optional-label">OPTIONAL</span></label><input id="latitude" className="form-input" type="number" inputMode="decimal" min="-90" max="90" step="any" value={lat} onChange={(event) => setLat(event.target.value)} placeholder="18.5204" /></div>
      <div><label className="field-label" htmlFor="longitude">Longitude <span className="optional-label">OPTIONAL</span></label><input id="longitude" className="form-input" type="number" inputMode="decimal" min="-180" max="180" step="any" value={lon} onChange={(event) => setLon(event.target.value)} placeholder="73.8567" /></div>
    </div>
    <p className="form-helper">Location is used to request a local weather forecast. You can leave it blank.</p>
    <div className="modal-actions"><button type="submit" className="button button-primary" disabled={busy}>{busy ? "Saving…" : field ? "Save changes" : "Add field"}</button></div>
  </form>;
}

export function FieldsPage() {
  const [fields, setFields] = useState<Field[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modalField, setModalField] = useState<Field | null | undefined>(undefined);
  const [pendingDelete, setPendingDelete] = useState<Field | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const loadFields = useCallback(async () => {
    try {
      const values = await api.listFields();
      setError("");
      setFields(values);
    }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Fields could not be loaded."); }
    finally { setLoading(false); }
  }, []);

  function retryLoad() { setLoading(true); setError(""); void loadFields(); }

  useEffect(() => { void loadFields(); }, [loadFields]);

  async function saveField(body: FieldCreate) {
    if (modalField === undefined) return;
    setBusy(true);
    try {
      if (modalField) await api.updateField(modalField.id, body);
      else await api.createField(body);
      setModalField(undefined);
      setNotice(modalField ? "Field details updated." : "Field added to your workspace.");
      await loadFields();
    } finally { setBusy(false); }
  }

  async function deleteField() {
    if (!pendingDelete) return;
    setBusy(true);
    setError("");
    try {
      await api.deleteField(pendingDelete.id);
      setPendingDelete(null);
      setNotice(`${pendingDelete.name} was deleted.`);
      await loadFields();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "This field could not be deleted.");
    } finally { setBusy(false); }
  }

  return <>
    <PageTitle eyebrow="YOUR LAND & CROPS" title="My fields" description="Keep each field’s crop, stage, and conditions together." action={<button className="button button-primary" onClick={() => setModalField(null)}><Plus className="h-4 w-4" /> Add a field</button>} />
    {notice && <div className="success-banner" role="status"><span>{notice}</span><button className="text-button" onClick={() => setNotice("")} aria-label="Dismiss message">×</button></div>}
    {error && <ErrorState message={error} onRetry={retryLoad} />}
    {loading ? <LoadingState label="Loading your fields" /> : error ? null : fields.length === 0 ? <EmptyState title="Your workspace is ready for its first field" message="Add a field to keep its crop details, sensor readings, and irrigation advice in one place." action={<button className="button button-primary" onClick={() => setModalField(null)}><Plus className="h-4 w-4" /> Add your first field</button>} /> : <div className="field-grid">
      {fields.map((field, index) => <article key={field.id} className="field-card" style={{ animationDelay: `${index * 70}ms` }}>
        <div className={`field-card-art field-art-${index % 3}`}><span className="field-art-chip"><span className="status-dot" /> Active field</span><div className="field-art-lines"><i /><i /><i /><i /><i /></div><div className="field-plant"><Sprout className="h-9 w-9" aria-hidden="true" /></div></div>
        <div className="field-card-body">
          <div className="field-card-heading"><div><p className="field-crop-label">{field.crop}</p><h2>{field.name}</h2></div><span className="stage-chip">{field.crop_stage}</span></div>
          <div className="field-card-location">{field.lat != null && field.lon != null ? <><MapPin className="h-3.5 w-3.5" aria-hidden="true" /> {field.lat.toFixed(3)}, {field.lon.toFixed(3)}</> : <><MapPin className="h-3.5 w-3.5" aria-hidden="true" /> Location not set</>}</div>
          <div className="field-card-footer"><Link to={`/fields/${field.id}`} className="field-open-link">View field <ArrowRight className="h-4 w-4" aria-hidden="true" /></Link><div className="field-card-actions"><button className="icon-button" aria-label={`Edit ${field.name}`} title="Edit field" onClick={() => setModalField(field)}><Pencil className="h-4 w-4" /></button><button className="icon-button icon-button-danger" aria-label={`Delete ${field.name}`} title="Delete field" onClick={() => setPendingDelete(field)}><Trash2 className="h-4 w-4" /></button></div></div>
        </div>
      </article>)}
    </div>}
    {modalField !== undefined && <Modal title={modalField ? "Edit field details" : "Add a field"} onClose={() => !busy && setModalField(undefined)}><FieldForm key={modalField?.id ?? "new"} field={modalField ?? undefined} busy={busy} onSave={saveField} /></Modal>}
    {pendingDelete && <Modal title="Delete this field?" onClose={() => !busy && setPendingDelete(null)}><div className="delete-confirm"><div className="delete-icon"><Trash2 className="h-5 w-5" /></div><p><strong>{pendingDelete.name}</strong> and its sensor history and irrigation decisions will be removed from your workspace.</p><div className="modal-actions"><button className="button button-secondary" onClick={() => setPendingDelete(null)} disabled={busy}>Keep field</button><button className="button button-danger" onClick={() => void deleteField()} disabled={busy}>{busy ? "Deleting…" : "Delete field"}</button></div></div></Modal>}
  </>;
}
