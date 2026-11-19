import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Cloud, RotateCw } from "lucide-react";
import { api, API_READY_EVENT, MOCKS_ENABLED } from "../api/client";

type WakeState = "checking" | "ready" | "offline";
let sharedWakeAttempt: Promise<boolean> | null = null;

async function wait(ms: number): Promise<void> {
  await new Promise((resolve) => window.setTimeout(resolve, ms));
}

function checkBackend(force = false): Promise<boolean> {
  if (!force && sharedWakeAttempt) return sharedWakeAttempt;
  sharedWakeAttempt = (async () => {
    const pauses = [0, 1800, 4200, 8000];
    for (const pause of pauses) {
      if (pause) await wait(pause);
      try {
        await api.health();
        return true;
      } catch {
        // A sleeping host gets a short, bounded retry sequence.
      }
    }
    return false;
  })();
  return sharedWakeAttempt;
}

export function WakeServerBanner() {
  const [state, setState] = useState<WakeState>(MOCKS_ENABLED ? "ready" : "checking");
  const [retrying, setRetrying] = useState(false);

  const runCheck = useCallback(async (force = false) => {
    if (MOCKS_ENABLED) {
      setState("ready");
      return;
    }
    setRetrying(true);
    setState("checking");
    const ready = await checkBackend(force);
    if (ready) window.dispatchEvent(new CustomEvent(API_READY_EVENT));
    setState(ready ? "ready" : "offline");
    setRetrying(false);
  }, []);

  useEffect(() => {
    let active = true;
    if (MOCKS_ENABLED) return undefined;
    void checkBackend().then((ready) => {
      if (!active) return;
      if (ready) window.dispatchEvent(new CustomEvent(API_READY_EVENT));
      setState(ready ? "ready" : "offline");
      setRetrying(false);
    });
    return () => { active = false; };
  }, []);

  if (state === "ready") return null;
  if (state === "checking") {
    return <div className="wake-banner wake-banner-waking" role="status" aria-live="polite"><Cloud className="h-4 w-4" aria-hidden="true" /><span>Waking the AgriSense field service. This can take a few moments.</span></div>;
  }
  return <div className="wake-banner wake-banner-error" role="alert"><AlertTriangle className="h-4 w-4" aria-hidden="true" /><span>The API is still unavailable. Your session and saved field data are unchanged.</span><button className="wake-retry" onClick={() => void runCheck(true)} disabled={retrying}><RotateCw className="h-3.5 w-3.5" aria-hidden="true" /> Retry</button></div>;
}
