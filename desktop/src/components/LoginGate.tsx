import { useState, useEffect, useCallback } from "react";
import { Lock } from "lucide-react";
import { OnboardingScreen } from "./OnboardingScreen";

interface Props {
  children: React.ReactNode;
}

type AuthStatus =
  | { phase: "loading" }
  | { phase: "onboarding" }
  | { phase: "login"; legacy: boolean }
  | { phase: "ready" };

export function LoginGate({ children }: Props) {
  const [status, setStatus] = useState<AuthStatus>({ phase: "loading" });
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const refreshStatus = useCallback(async () => {
    try {
      const res = await fetch("/auth/status", { credentials: "include" });
      if (!res.ok) {
        // Auth subsystem disabled or unreachable — fall through to children.
        setStatus({ phase: "ready" });
        return;
      }
      const data = await res.json();
      if (!data.configured) {
        setStatus({ phase: "onboarding" });
      } else if (data.authenticated) {
        setStatus({ phase: "ready" });
      } else {
        setStatus({ phase: "login", legacy: !data.user });
      }
    } catch {
      // Network error — assume auth not enforced and let the desktop load.
      setStatus({ phase: "ready" });
    }
  }, []);

  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username: username.trim() || undefined, password }),
      });
      if (res.ok) {
        await refreshStatus();
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data?.error ?? "Incorrect username or password");
      }
    } catch {
      setError("Login failed");
    }
    setLoading(false);
  };

  if (status.phase === "loading") {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-shell-bg text-shell-text-tertiary text-sm">
        Loading...
      </div>
    );
  }

  if (status.phase === "onboarding") {
    return <OnboardingScreen onDone={refreshStatus} />;
  }

  if (status.phase === "login") {
    const showUsername = !status.legacy;
    return (
      <div
        className="h-screen w-screen flex items-center justify-center p-4"
        style={{ background: "linear-gradient(160deg, #1a1b2e 0%, #1e2140 40%, #252848 100%)" }}
      >
        <form
          onSubmit={handleSubmit}
          className="w-full max-w-sm p-6 rounded-2xl border border-white/10"
          style={{
            backgroundColor: "rgba(255,255,255,0.04)",
            backdropFilter: "blur(20px)",
          }}
        >
          <div className="flex flex-col items-center gap-3 mb-6">
            <div
              className="w-14 h-14 rounded-2xl flex items-center justify-center"
              style={{ background: "linear-gradient(135deg, #8b92a3, #5b6170)" }}
            >
              <Lock size={24} className="text-white" />
            </div>
            <h1 className="text-lg font-semibold text-shell-text">taOS</h1>
            <p className="text-xs text-shell-text-secondary">Sign in to continue</p>
          </div>

          {showUsername && (
            <>
              <label htmlFor="login-username" className="sr-only">Username</label>
              <input
                id="login-username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                placeholder="Username"
                className="w-full px-4 py-2.5 mb-2 rounded-lg bg-shell-bg-deep border border-white/10 text-sm text-shell-text outline-none focus:border-accent/40 transition-colors"
              />
            </>
          )}

          <label htmlFor="login-password" className="sr-only">Password</label>
          <input
            id="login-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            autoFocus={!showUsername}
            placeholder="Password"
            className="w-full px-4 py-2.5 rounded-lg bg-shell-bg-deep border border-white/10 text-sm text-shell-text outline-none focus:border-accent/40 transition-colors"
          />

          {error && <p className="text-xs text-red-400 mt-2" role="alert">{error}</p>}

          <button
            type="submit"
            disabled={loading || !password || (showUsername && !username)}
            className="w-full mt-4 px-4 py-2.5 rounded-lg bg-accent text-white text-sm font-medium hover:brightness-110 disabled:opacity-50 transition-all"
          >
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </form>
      </div>
    );
  }

  return <>{children}</>;
}
