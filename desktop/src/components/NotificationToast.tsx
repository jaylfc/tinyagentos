import { useEffect } from "react";
import { X, Info, CheckCircle, AlertTriangle, AlertCircle } from "lucide-react";
import { useNotificationStore, type Notification } from "@/stores/notification-store";

const LEVEL_ICONS = {
  info: Info,
  success: CheckCircle,
  warning: AlertTriangle,
  error: AlertCircle,
};

const LEVEL_COLORS = {
  info: "text-blue-400 bg-blue-500/10 border-blue-500/20",
  success: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
  warning: "text-amber-400 bg-amber-500/10 border-amber-500/20",
  error: "text-red-400 bg-red-500/10 border-red-500/20",
};

function ToastItem({ notif }: { notif: Notification }) {
  const dismiss = useNotificationStore((s) => s.dismiss);
  const Icon = LEVEL_ICONS[notif.level];

  useEffect(() => {
    const timer = setTimeout(() => dismiss(notif.id), 5000);
    return () => clearTimeout(timer);
  }, [notif.id, dismiss]);

  return (
    <div
      className={`flex items-start gap-3 p-3 rounded-xl border backdrop-blur-lg shadow-xl w-80 ${LEVEL_COLORS[notif.level]}`}
      style={{ backgroundColor: "rgba(26, 27, 46, 0.9)" }}
    >
      <Icon size={18} className="shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-shell-text">{notif.title}</div>
        {notif.body && <div className="text-xs text-shell-text-secondary mt-0.5">{notif.body}</div>}
      </div>
      <button onClick={() => dismiss(notif.id)} className="shrink-0 text-shell-text-tertiary hover:text-shell-text">
        <X size={14} />
      </button>
    </div>
  );
}

export function NotificationToasts() {
  const notifications = useNotificationStore((s) => s.notifications);
  // Only show unread, non-persisted notifications as toasts (latest 3)
  const active = notifications.filter((n) => !n.read).slice(0, 3);

  return (
    <div className="fixed bottom-20 right-4 z-[10001] flex flex-col gap-2 pointer-events-auto">
      {active.map((n) => (
        <ToastItem key={n.id} notif={n} />
      ))}
    </div>
  );
}
