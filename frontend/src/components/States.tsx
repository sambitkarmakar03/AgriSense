import { useEffect, useRef, type ReactNode } from "react";
import { AlertCircle, LoaderCircle, Sprout } from "lucide-react";

export function LoadingState({ label = "Loading your farm data" }: { label?: string }) {
  return (
    <div className="state-card" role="status" aria-live="polite">
      <LoaderCircle className="h-5 w-5 animate-spin text-leaf-700" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state-card state-card-error" role="alert">
      <AlertCircle className="h-5 w-5 shrink-0" aria-hidden="true" />
      <span className="flex-1">{message}</span>
      {onRetry && <button className="button button-secondary button-small" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function EmptyState({ title, message, action }: { title: string; message: string; action?: ReactNode }) {
  return (
    <div className="empty-state">
      <span className="empty-state-icon"><Sprout className="h-6 w-6" aria-hidden="true" /></span>
      <h3>{title}</h3>
      <p>{message}</p>
      {action}
    </div>
  );
}

export function PageTitle({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="page-title-row">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {action && <div className="page-title-action">{action}</div>}
    </div>
  );
}

export function Panel({ title, subtitle, action, children, className = "" }: { title?: string; subtitle?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`panel ${className}`}>
      {(title || subtitle || action) && <div className="panel-header">
        <div>{title && <h2 className="panel-title">{title}</h2>}{subtitle && <p className="panel-subtitle">{subtitle}</p>}</div>
        {action}
      </div>}
      {children}
    </section>
  );
}

export function Modal({ title, children, onClose, wide = false }: { title: string; children: ReactNode; onClose: () => void; wide?: boolean }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (!dialog.open) dialog.showModal();
    return () => { if (dialog.open) dialog.close(); };
  }, []);
  return (
    <dialog ref={dialogRef} className={`modal ${wide ? "modal-wide" : ""}`} aria-labelledby="modal-title" onCancel={(event) => { event.preventDefault(); onClose(); }}>
      <div className="modal-header"><h2 id="modal-title">{title}</h2><button className="icon-button" aria-label="Close dialog" onClick={onClose}>×</button></div>
      {children}
    </dialog>
  );
}
