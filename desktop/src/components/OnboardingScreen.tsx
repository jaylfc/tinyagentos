import { useState } from "react";
import { Sparkles } from "lucide-react";

interface Props {
  onDone: () => void;
}

/**
 * First-run onboarding. Collects username, full name, email, and a
 * password to seed the single-user record. Once submitted, the server
 * sets a session cookie and we hand control back to LoginGate which
 * re-checks `/auth/status` and renders the desktop.
 *
 * Email is gathered now (even though it's unused today) so cloud
 * services can reach the user without a second prompt later.
 */
export function OnboardingScreen({ onDone }: Props) {
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const passwordOk = password.length >= 4;
  const matches = password.length > 0 && password === confirm;
  const valid =
    username.trim().length > 0 &&
    fullName.trim().length > 0 &&
    passwordOk &&
    matches;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!valid) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/auth/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          username: username.trim(),
          full_name: fullName.trim(),
          email: email.trim(),
          password,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data?.error ?? `Setup failed (${res.status})`);
        setLoading(false);
        return;
      }
      onDone();
    } catch {
      setError("Network error — please try again");
      setLoading(false);
    }
  }

  return (
    <div
      className="h-screen w-screen flex items-center justify-center overflow-y-auto"
      style={{
        background: "linear-gradient(160deg, #1a1b2e 0%, #1e2140 40%, #252848 100%)",
        paddingTop: "calc(env(safe-area-inset-top, 0px) + 16px)",
        paddingBottom: "calc(env(safe-area-inset-bottom, 0px) + 16px)",
        paddingLeft: "calc(env(safe-area-inset-left, 0px) + 16px)",
        paddingRight: "calc(env(safe-area-inset-right, 0px) + 16px)",
      }}
    >
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md p-6 rounded-2xl border border-white/10"
        style={{
          backgroundColor: "rgba(255,255,255,0.04)",
          backdropFilter: "blur(20px)",
        }}
        aria-label="Welcome to taOS"
      >
        <div className="flex flex-col items-center gap-3 mb-6">
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center"
            style={{ background: "linear-gradient(135deg, #8b92a3, #5b6170)" }}
          >
            <Sparkles size={24} className="text-white" />
          </div>
          <h1 className="text-lg font-semibold text-shell-text">Welcome to taOS</h1>
          <p className="text-xs text-shell-text-secondary text-center">
            Set up your account. You can change any of these later in Settings.
          </p>
        </div>

        <div className="space-y-3">
          <Field label="Username" id="onb-username" required>
            <input
              id="onb-username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value.replace(/\s+/g, "").toLowerCase())}
              autoComplete="username"
              autoFocus
              placeholder="jay"
              className="onb-input"
            />
          </Field>

          <Field label="Full name" id="onb-fullname" required>
            <input
              id="onb-fullname"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              autoComplete="name"
              placeholder="Jay Doe"
              className="onb-input"
            />
          </Field>

          <Field label="Email" id="onb-email" hint="Used for cloud services later. Optional today.">
            <input
              id="onb-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              placeholder="you@example.com"
              className="onb-input"
            />
          </Field>

          <Field label="Password" id="onb-password" required hint="At least 4 characters.">
            <input
              id="onb-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              className="onb-input"
            />
          </Field>

          <Field label="Confirm password" id="onb-confirm" required>
            <input
              id="onb-confirm"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              className="onb-input"
              aria-invalid={confirm.length > 0 && !matches}
            />
            {confirm.length > 0 && !matches && (
              <p className="text-[11px] text-red-400 mt-1">Passwords don't match.</p>
            )}
          </Field>
        </div>

        {error && (
          <p className="text-xs text-red-400 mt-3 text-center" role="alert">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={!valid || loading}
          className="w-full mt-5 px-4 py-2.5 rounded-lg bg-accent text-white text-sm font-medium hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
        >
          {loading ? "Setting up..." : "Get started"}
        </button>

        <style>{`
          .onb-input {
            width: 100%;
            padding: 10px 14px;
            border-radius: 8px;
            background: var(--color-shell-bg-deep);
            border: 1px solid rgba(255, 255, 255, 0.10);
            color: var(--color-shell-text);
            font-size: 13px;
            outline: none;
            transition: border-color 0.15s;
          }
          .onb-input:focus {
            border-color: rgba(139, 146, 163, 0.45);
          }
        `}</style>
      </form>
    </div>
  );
}

function Field({
  label,
  id,
  required,
  hint,
  children,
}: {
  label: string;
  id: string;
  required?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label
        htmlFor={id}
        className="block text-[11px] uppercase tracking-wide text-shell-text-tertiary mb-1"
      >
        {label}
        {required && <span className="text-red-400 ml-1" aria-hidden="true">*</span>}
      </label>
      {children}
      {hint && <p className="text-[10px] text-shell-text-tertiary mt-1">{hint}</p>}
    </div>
  );
}
