"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Alert, type AlertTone } from "./Alert";

const ALERT_DURATION_MS = 3_000;

interface AlertItem {
  id: number;
  message: string;
  tone: AlertTone;
}

interface AlertContextValue {
  showAlert: (message: string, tone?: AlertTone) => void;
  showSuccess: (message: string) => void;
  showError: (message: string) => void;
  showWarning: (message: string) => void;
  showInfo: (message: string) => void;
}

const AlertContext = createContext<AlertContextValue | null>(null);

function TimedAlert({
  item,
  onDismiss,
}: {
  item: AlertItem;
  onDismiss: (id: number) => void;
}) {
  const dismissItem = useCallback(() => onDismiss(item.id), [item.id, onDismiss]);

  useEffect(() => {
    const timer = window.setTimeout(dismissItem, ALERT_DURATION_MS);
    return () => window.clearTimeout(timer);
  }, [dismissItem]);

  return <Alert message={item.message} tone={item.tone} onDismiss={dismissItem} />;
}

export function AlertProvider({ children }: { children: ReactNode }) {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setAlerts((current) => current.filter((alert) => alert.id !== id));
  }, []);

  const showAlert = useCallback((message: string, tone: AlertTone = "info") => {
    const normalizedMessage = message.trim();
    if (!normalizedMessage) return;
    const id = nextId.current++;
    setAlerts((current) => [...current.slice(-3), { id, message: normalizedMessage, tone }]);
  }, []);

  const value = useMemo<AlertContextValue>(() => ({
    showAlert,
    showSuccess: (message) => showAlert(message, "success"),
    showError: (message) => showAlert(message, "error"),
    showWarning: (message) => showAlert(message, "warning"),
    showInfo: (message) => showAlert(message, "info"),
  }), [showAlert]);

  return (
    <AlertContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed inset-x-3 top-3 z-[100] flex flex-col items-end gap-2 sm:left-auto sm:right-4 sm:top-4 sm:w-full sm:max-w-sm"
        aria-live="polite"
        aria-atomic="false"
      >
        {alerts.map((item) => (
          <TimedAlert
            key={item.id}
            item={item}
            onDismiss={dismiss}
          />
        ))}
      </div>
    </AlertContext.Provider>
  );
}

export function useAlert() {
  const context = useContext(AlertContext);
  if (!context) {
    throw new Error("useAlert must be used inside AlertProvider");
  }
  return context;
}
