import { useState, type FormEvent, type ReactNode } from "react";
import { Eye, EyeOff, Leaf, LockKeyhole, Sprout } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ApiError, MOCKS_ENABLED } from "../api/client";
import { useAuth } from "../auth/useAuth";

function AuthFrame({ eyebrow, title, description, children, mode }: { eyebrow: string; title: string; description: string; children: ReactNode; mode: "login" | "register" }) {
  return (
    <main className="auth-page">
      <section className="auth-story" aria-label="AgriSense introduction">
        <Link to="/login" className="auth-brand"><span className="brand-mark"><Sprout className="h-5 w-5" aria-hidden="true" /></span><strong>AgriSense</strong></Link>
        <div className="auth-story-content">
          <p className="auth-kicker"><span className="auth-kicker-line" /> BETTER FIELD DECISIONS, ROOTED IN YOUR DATA</p>
          <h1>Know your fields.<br /><em>Grow with confidence.</em></h1>
          <p className="auth-story-copy">Clear field conditions and explainable irrigation guidance, in one calm place to plan your next move.</p>
          <div className="auth-art" aria-hidden="true">
            <div className="auth-sun" />
            <div className="auth-hill auth-hill-back" />
            <div className="auth-hill auth-hill-front" />
            <div className="auth-field-lines"><span /><span /><span /><span /></div>
            <div className="auth-art-label"><Leaf className="h-4 w-4" /><span>Made for the rhythm of your farm</span></div>
          </div>
        </div>
        <div className="auth-story-footer"><span>LOCAL KNOWLEDGE, MADE VISIBLE</span><span>01 / 03</span></div>
      </section>
      <section className="auth-panel">
        <div className="auth-mobile-brand"><span className="brand-mark"><Sprout className="h-5 w-5" aria-hidden="true" /></span><strong>AgriSense</strong></div>
        <div className="auth-form-wrap">
          <div className="auth-form-heading"><p className="eyebrow">{eyebrow}</p><h2>{title}</h2><p>{description}</p></div>
          {MOCKS_ENABLED && <div className="demo-auth-note" role="status">Demo preview is enabled. Sign in with any valid email and password to explore sample data.</div>}
          {children}
          <div className="auth-switch">{mode === "login" ? <>New to AgriSense? <Link to="/register">Create an account <span aria-hidden="true">→</span></Link></> : <>Already have an account? <Link to="/login">Sign in <span aria-hidden="true">→</span></Link></>}</div>
        </div>
        <div className="auth-panel-footer"><Link to="/limitations">Privacy & ethics</Link><span>·</span><span>AgriSense field intelligence</span></div>
      </section>
    </main>
  );
}

function PasswordInput({ value, onChange, autoComplete, minLength = 8 }: { value: string; onChange: (value: string) => void; autoComplete: string; minLength?: number }) {
  const [visible, setVisible] = useState(false);
  return <div className="password-wrap"><input className="form-input" id="password" name="password" type={visible ? "text" : "password"} value={value} onChange={(event) => onChange(event.target.value)} autoComplete={autoComplete} minLength={minLength} maxLength={256} required /><button className="password-toggle" type="button" aria-label={visible ? "Hide password" : "Show password"} onClick={() => setVisible(!visible)}>{visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}</button></div>;
}

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const returnTo = (location.state as { from?: string } | null)?.from ?? "/";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login({ email, password });
      navigate(returnTo, { replace: true });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "We could not sign you in. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return <AuthFrame mode="login" eyebrow="WELCOME BACK" title="Good to see you." description="Sign in to continue to your field workspace.">
    <form className="auth-form" onSubmit={submit}>
      {error && <div className="form-alert" role="alert">{error}</div>}
      <label className="field-label" htmlFor="email">Email address</label>
      <input className="form-input" id="email" name="email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} maxLength={320} placeholder="you@yourfarm.in" required />
      <div className="label-with-link"><label className="field-label" htmlFor="password">Password</label><span className="field-hint"><LockKeyhole className="h-3.5 w-3.5" /> Secured with a private session</span></div>
      <PasswordInput value={password} onChange={setPassword} autoComplete="current-password" minLength={1} />
      <button className="button button-primary button-full auth-submit" type="submit" disabled={busy}>{busy ? <span className="button-spinner" /> : null}{busy ? "Signing in…" : "Sign in to AgriSense"}<span aria-hidden="true">→</span></button>
      <p className="auth-privacy-note">Your field data belongs to you. <Link to="/limitations">Read our privacy notice</Link>.</p>
    </form>
  </AuthFrame>;
}

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (!consent) {
      setError("Please review and accept the privacy notice to create an account.");
      return;
    }
    setBusy(true);
    try {
      await register({ email, password, full_name: fullName.trim() || null, consent_accepted: true, consent_text_version: "v1" });
      navigate("/", { replace: true });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : caught instanceof Error ? caught.message : "We could not create your account.");
    } finally {
      setBusy(false);
    }
  }

  return <AuthFrame mode="register" eyebrow="START WITH YOUR FIELDS" title="A clearer view starts here." description="Create your account to set up your field workspace.">
    <form className="auth-form" onSubmit={submit}>
      {error && <div className="form-alert" role="alert">{error}</div>}
      <label className="field-label" htmlFor="full-name">Your name <span className="optional-label">OPTIONAL</span></label>
      <input className="form-input" id="full-name" name="name" type="text" autoComplete="name" value={fullName} onChange={(event) => setFullName(event.target.value)} maxLength={160} placeholder="How should we address you?" />
      <label className="field-label" htmlFor="email">Email address</label>
      <input className="form-input" id="email" name="email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} maxLength={320} placeholder="you@yourfarm.in" required />
      <label className="field-label" htmlFor="password">Create a password</label>
      <PasswordInput value={password} onChange={setPassword} autoComplete="new-password" />
      <p className="password-help">Use at least 8 characters. Your password is stored as a secure hash.</p>
      <div className="consent-row"><input id="consent" type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} required /><label htmlFor="consent">I agree to the privacy notice and consent to AgriSense using my account and field information to provide irrigation guidance.</label></div>
      <p className="consent-detail"><Link to="/limitations">Review what we collect and how it is used.</Link> Your consent record is stored with your account.</p>
      <button className="button button-primary button-full auth-submit" type="submit" disabled={busy}>{busy ? <span className="button-spinner" /> : <Sprout className="h-4 w-4" />}{busy ? "Creating your account…" : "Create my workspace"}<span aria-hidden="true">→</span></button>
    </form>
  </AuthFrame>;
}
