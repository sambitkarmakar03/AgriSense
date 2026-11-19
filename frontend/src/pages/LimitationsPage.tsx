import { ArrowLeft, ExternalLink, Eye, FileWarning, HandHelping, MapPinned, ShieldCheck, Sprout } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

const privacyLinks = [
  { label: "Digital Personal Data Protection Act, 2023", href: "https://www.indiacode.nic.in/bitstream/123456789/22037/1/a2023-22.pdf" },
  { label: "Digital Personal Data Protection Rules, 2025", href: "https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf" },
];

const limits = [
  { icon: ShieldCheck, title: "Advice only", text: "An ON/OFF suggestion is decision support. AgriSense does not actuate irrigation equipment or guarantee crop outcomes. Check the field and use your judgment before acting." },
  { icon: MapPinned, title: "Regional thresholds", text: "Irrigation thresholds are rule-based and may not match local soil, crop variety, season, sensor calibration, or water-management practices. Review advice with a local agronomist when conditions are uncertain." },
  { icon: FileWarning, title: "Disease detection is not available yet", text: "The current release does not accept leaf images or provide disease classifications. A future model is planned around four labels and lab-image training; performance in real field conditions will need careful validation." },
  { icon: HandHelping, title: "Human agronomist involvement", text: "A rule match is not a substitute for professional crop advice. Ask an agronomist when a recommendation conflicts with field observations or when the crop is at risk." },
  { icon: Eye, title: "Sensor and model limits", text: "Recommendations depend on the values supplied. Missing, stale, inaccurate, or unrepresentative readings can change the result. The system reports rule matches; it does not independently verify sensors." },
];

export function LimitationsPage() {
  const navigate = useNavigate();
  const hasHistory = window.history.length > 1;
  return <main className="ethics-page">
    <header className="ethics-topbar"><Link to="/login" className="auth-brand"><span className="brand-mark"><Sprout className="h-5 w-5" aria-hidden="true" /></span><strong>AgriSense</strong></Link><button className="ethics-back" onClick={() => hasHistory ? navigate(-1) : navigate("/login")}><ArrowLeft className="h-4 w-4" /> Back</button></header>
    <div className="ethics-main">
      <p className="eyebrow">LIMITATIONS · PRIVACY · RESPONSIBLE USE</p>
      <h1>Useful guidance starts with honest limits.</h1>
      <p className="ethics-lede">AgriSense helps organize field information and explain irrigation rules. It cannot see everything happening in a field, and it does not replace the judgment of the people who work it.</p>
      <section className="ethics-notice">
        <div className="ethics-notice-icon"><ShieldCheck className="h-5 w-5" /></div>
        <div><span className="eyebrow">PRIVACY NOTICE</span><h2>What information is used?</h2><p>To provide this service, AgriSense may process your account email and name, field name and crop details, optional field coordinates, sensor readings, irrigation decisions, override notes, and the consent record associated with registration. Field coordinates are sent to the weather provider when a forecast is requested.</p><p>Use coordinates only when you want location-based weather. Avoid entering information that is not needed for field guidance. Data is used to operate the account and provide the requested advisory features; no model training workflow is active in this release.</p><p>Registration records your consent text version. The current interface does not include a self-service privacy dashboard. Account deletion is available through the authenticated account endpoint; contact your service operator for help using it.</p><p className="ethics-law-note">This product notice describes current AgriSense behavior; it is not a claim of legal compliance. The Digital Personal Data Protection Act, 2023 and its rules have provision-specific commencement. Deployment operators should review the applicable requirements and provide the required notices and rights flows.</p><div className="privacy-links">{privacyLinks.map((item) => <a key={item.label} href={item.href} target="_blank" rel="noreferrer">{item.label} <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" /></a>)}</div></div>
      </section>
      <h2 className="ethics-section-title">What to keep in mind</h2>
      <div className="limit-list">{limits.map(({ icon: Icon, title, text }) => <article className="limit-card" key={title}><span className="limit-icon"><Icon className="h-5 w-5" aria-hidden="true" /></span><div><h3>{title}</h3><p>{text}</p></div></article>)}</div>
      <div className="ethics-footer-note"><span className="ethics-footer-mark"><Sprout className="h-4 w-4" /></span><p>Use local observations alongside every recommendation. When something does not look right, pause and ask a human expert.</p></div>
    </div>
    <footer className="ethics-page-footer">AgriSense <span>·</span> Field intelligence for informed decisions</footer>
  </main>;
}
