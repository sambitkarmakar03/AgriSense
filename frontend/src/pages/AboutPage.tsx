import { useCallback, useEffect, useState } from "react";
import { Activity, ArrowRight, BrainCircuit, CircleHelp, Database, GitBranch, MessageSquareText, Network, ShieldCheck, Sprout } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { AboutSystem } from "../api/client";
import { ErrorState, LoadingState, PageTitle, Panel } from "../components/States";

const concepts = [
  { title: "Working memory", text: "The current field context: the latest sensor values, crop stage, and available forecast. Each decision records the inputs used.", icon: Database },
  { title: "Inference engine", text: "A small forward-chaining engine evaluates the current facts against the selected irrigation knowledge base and records which rules fired.", icon: BrainCircuit },
  { title: "Explanation facility", text: "The rule trace and a plain-language explanation show how the recommendation followed from the available field conditions.", icon: CircleHelp },
  { title: "Knowledge acquisition", text: "Irrigation rules are stored in versioned YAML knowledge bases. Agronomist editing and review are planned for a later phase.", icon: GitBranch },
  { title: "Feedback mechanism", text: "Farmer overrides and their notes are saved with a decision. They provide context for later review; they do not automatically retrain or change rules.", icon: MessageSquareText },
  { title: "System boundary", text: "AgriSense provides advisory irrigation decisions. It does not control pumps, validate sensor hardware, or replace agronomic judgment.", icon: ShieldCheck },
];

export function AboutPage() {
  const [system, setSystem] = useState<AboutSystem | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await api.getAboutSystem();
      setError("");
      setSystem(data);
    }
    catch (caught) { setError(caught instanceof Error ? caught.message : "System information could not be loaded."); }
    finally { setLoading(false); }
  }, []);

  function retry() { setLoading(true); setError(""); void load(); }

  useEffect(() => { void load(); }, [load]);

  return <>
    <PageTitle eyebrow="HOW AGRISENSE WORKS" title="Field signals, made understandable." description="A compact decision-support system built around field data and explainable irrigation rules." />
    {error && <ErrorState message={error} onRetry={retry} />}
    <section className="about-hero">
      <div className="about-hero-copy"><span className="about-hero-mark"><Network className="h-5 w-5" /></span><p className="eyebrow">A SMALL, EXPLAINABLE SYSTEM</p><h2>From field readings<br />to a reasoned next step.</h2><p>AgriSense brings together sensor readings, a forecast when one is available, and a versioned set of agronomic rules. The system shows its work so a farmer can decide what to do next.</p></div>
      <div className="system-flow" aria-label="System input and output flow"><div className="flow-node"><span className="flow-icon flow-input"><Sprout className="h-5 w-5" /></span><strong>Field facts</strong><small>Crop · readings<br />Forecast · stage</small></div><span className="flow-arrow"><ArrowRight className="h-5 w-5" /></span><div className="flow-node flow-engine"><span className="flow-icon flow-process"><Activity className="h-5 w-5" /></span><strong>Rule engine</strong><small>YAML knowledge<br />Forward chaining</small></div><span className="flow-arrow"><ArrowRight className="h-5 w-5" /></span><div className="flow-node"><span className="flow-icon flow-output"><ShieldCheck className="h-5 w-5" /></span><strong>Advice</strong><small>Action · duration<br />Why it matched</small></div></div>
      <div className="about-hero-caption"><span><span className="status-dot" /> EXPLAINABLE BY DESIGN</span><span>Advisory decision support</span></div>
    </section>

    <div className="concept-grid">{concepts.map(({ title, text, icon: Icon }, index) => <article className="concept-card" key={title}><span className="concept-number">0{index + 1}</span><span className="concept-icon"><Icon className="h-5 w-5" aria-hidden="true" /></span><h2>{title}</h2><p>{text}</p></article>)}</div>

    <div className="about-data-grid">
      <Panel title="Inputs & outputs" subtitle="Data provided to and returned by the system">
        {loading ? <LoadingState label="Loading system details" /> : system ? <div className="two-column-lists">
          <div><h3>Inputs</h3><ul className="detail-list">{system.inputs.map((value) => <li key={value}><span className="list-bullet list-bullet-green" />{value}</li>)}</ul></div>
          <div><h3>Outputs</h3><ul className="detail-list">{system.outputs.map((value) => <li key={value}><span className="list-bullet list-bullet-blue" />{value}</li>)}</ul></div>
        </div> : null}
      </Panel>
      <Panel title="Runtime environment" subtitle="The system’s interfaces and boundaries">
        {loading ? <LoadingState label="Loading environment details" /> : system ? <>
          <p className="system-boundary">{system.boundary}</p>
          <div className="environment-columns">
            <div><h3>Interfaces</h3><ul className="detail-list">{system.interfaces.map((value) => <li key={value}><span className="list-bullet list-bullet-green" />{value}</li>)}</ul></div>
            <div><h3>Environment</h3><ul className="detail-list">{system.environment.map((value) => <li key={value}><span className="list-bullet list-bullet-blue" />{value}</li>)}</ul></div>
          </div>
        </> : null}
      </Panel>
    </div>

    {system && <Panel title="System processor" subtitle="The active services that produce irrigation guidance"><ul className="processor-list">{system.processor.map((value, index) => <li key={value}><span className="processor-step">0{index + 1}</span><span>{value}</span></li>)}</ul></Panel>}
    <div className="about-next-step"><div><strong>Want to see a recommendation for a field?</strong><p>Open the advisor to review conditions, rules, and previous decisions.</p></div><Link to="/irrigation" className="button button-primary">Open irrigation advisor <ArrowRight className="h-4 w-4" /></Link></div>
  </>;
}
