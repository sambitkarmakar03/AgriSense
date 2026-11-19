import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Activity, ArrowUpRight, CloudSun, FileText, LayoutDashboard, Leaf, LogOut, Menu, Moon, PanelsTopLeft, Plus, ShieldCheck, Sprout, Sun, X } from "lucide-react";
import { useAuth } from "../auth/useAuth";
import { MOCKS_ENABLED } from "../api/client";

const navigation = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/fields", label: "My fields", icon: PanelsTopLeft },
  { to: "/irrigation", label: "Irrigation advisor", icon: CloudSun },
];

const secondaryNavigation = [
  { to: "/about", label: "About the system", icon: Activity },
  { to: "/limitations", label: "Limitations & ethics", icon: ShieldCheck },
];

function initials(name: string): string {
  return name.split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase() ?? "").join("");
}

export function AppShell() {
  const { user, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [dark, setDark] = useState(() => {
    const saved = window.localStorage.getItem("agrisense.theme");
    return saved === "dark" || (saved !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  });
  const location = useLocation();
  const pageTitle = [...navigation, ...secondaryNavigation].find((item) => item.to === location.pathname)?.label ?? "Field detail";

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  function toggleTheme() {
    const nextDark = !dark;
    setDark(nextDark);
    document.documentElement.classList.toggle("dark", nextDark);
    window.localStorage.setItem("agrisense.theme", nextDark ? "dark" : "light");
  }

  function closeMobileMenu() { setMobileOpen(false); }

  return (
    <div className="app-frame">
      {mobileOpen && <button className="sidebar-scrim" aria-label="Close navigation" onClick={closeMobileMenu} />}
      <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`} aria-label="Main navigation">
        <div className="brand-lockup">
          <span className="brand-mark"><Sprout className="h-5 w-5" aria-hidden="true" /></span>
          <span><strong>AgriSense</strong><small>FIELD INTELLIGENCE</small></span>
          <button className="icon-button sidebar-close" aria-label="Close navigation" onClick={closeMobileMenu}><X className="h-5 w-5" /></button>
        </div>

        <div className="season-card">
          <div className="season-orbit"><Leaf className="h-5 w-5" aria-hidden="true" /></div>
          <p className="season-label">YOUR FARMSPACE</p>
          <p className="season-name">Field operations</p>
          <span className="season-status"><span className="status-dot" /> {MOCKS_ENABLED ? "Demo preview" : "Connected workspace"}</span>
        </div>

        <p className="nav-caption">WORKSPACE</p>
        <nav className="nav-group" aria-label="Workspace">
          {navigation.map(({ to, label, icon: Icon, end }) => <NavLink key={to} to={to} end={end} onClick={closeMobileMenu} className={({ isActive }) => `nav-link ${isActive ? "nav-link-active" : ""}`}><Icon className="h-[18px] w-[18px]" aria-hidden="true" /><span>{label}</span>{label === "My fields" && <ArrowUpRight className="nav-trailing h-3.5 w-3.5" aria-hidden="true" />}</NavLink>)}
        </nav>

        <div className="nav-divider" />
        <p className="nav-caption">GUIDANCE</p>
        <nav className="nav-group" aria-label="Guidance">
          {secondaryNavigation.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} onClick={closeMobileMenu} className={({ isActive }) => `nav-link ${isActive ? "nav-link-active" : ""}`}><Icon className="h-[18px] w-[18px]" aria-hidden="true" /><span>{label}</span></NavLink>)}
        </nav>

        <div className="sidebar-spacer" />
        <div className="sidebar-help">
          <div className="help-icon"><FileText className="h-4 w-4" aria-hidden="true" /></div>
          <p className="help-title">Made for better decisions</p>
          <p className="help-copy">Recommendations are advisory. Your field knowledge always matters.</p>
          <NavLink to="/limitations" className="help-link" onClick={closeMobileMenu}>Read our approach <ArrowUpRight className="h-3.5 w-3.5" /></NavLink>
        </div>
        <div className="sidebar-profile">
          <span className="avatar">{initials(user?.full_name || user?.email || "AF")}</span>
          <span className="profile-copy"><strong>{user?.full_name || "Farmer"}</strong><small>{user?.email}</small></span>
          <button className="icon-button profile-logout" aria-label="Sign out" title="Sign out" onClick={logout}><LogOut className="h-4 w-4" /></button>
        </div>
      </aside>

      <div className="main-frame">
        <header className="topbar">
          <div className="topbar-leading">
            <button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setMobileOpen(true)}><Menu className="h-5 w-5" /></button>
            <span className="breadcrumb-label">Workspace <span>/</span> <strong>{pageTitle}</strong></span>
          </div>
          <div className="topbar-actions">
            {MOCKS_ENABLED && <span className="demo-pill"><span className="status-dot" /> Demo data</span>}
            <span className="topbar-date">{new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric" }).format(new Date())}</span>
            <button className="theme-toggle" onClick={toggleTheme} aria-label={`Switch to ${dark ? "light" : "dark"} theme`} title={`Switch to ${dark ? "light" : "dark"} theme`}>{dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}</button>
          </div>
        </header>
        {MOCKS_ENABLED && <div className="demo-strip"><Plus className="h-3.5 w-3.5" aria-hidden="true" /> Preview data is isolated in demo mode and is not sent to the AgriSense backend.</div>}
        <main className="main-content"><Outlet /></main>
        <footer className="app-footer"><span>AgriSense <span className="footer-dot">·</span> Field intelligence</span><span>Recommendations are advisory and may need local review.</span></footer>
      </div>
    </div>
  );
}
