import { useState, useEffect } from "react";
import { Lock } from "lucide-react";

interface Props {
  children: React.ReactNode;
}

export function LoginGate({ children }: Props) {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Check auth status — try fetching desktop settings (a protected endpoint)
    fetch("/api/desktop/settings", { credentials: "include" })
      .then((r) => {
        if (r.status === 401) {
          setAuthed(false);
        } else {
          setAuthed(true);
        }
      })
      .catch(() => setAuthed(true)); // if the check fails, assume auth is disabled
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      // TinyAgentOS auth uses form-urlencoded POST to /auth/login.
      // A 303 redirect on success sets the session cookie; a failed
      // login redirects back to /auth/login?error=1.
      const body = new URLSearchParams();
      body.set("password", password);
      const res = await fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        credentials: "include",
        redirect: "manual",
        body: body.toString(),
      });
      // Re-check against a protected endpoint to confirm auth state
      const check = await fetch("/api/desktop/settings", { credentials: "include" });
      if (check.status !== 401) {
        setAuthed(true);
      } else {
        setError("Incorrect password");
      }
      void res;
    } catch {
      setError("Login failed");
    }
    setLoading(false);
  };

  if (authed === null) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-shell-bg text-shell-text-tertiary text-sm">
        Loading...
      </div>
    );
  }

  if (!authed) {
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
              style={{ background: "linear-gradient(135deg, #667eea, #764ba2)" }}
            >
              <Lock size={24} className="text-white" />
            </div>
            <h1 className="text-lg font-semibold text-shell-text">taOS</h1>
            <p className="text-xs text-shell-text-secondary">Enter your password to continue</p>
          </div>

          <label htmlFor="login-password" className="sr-only">Password</label>
          <input
            id="login-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus
            placeholder="Password"
            className="w-full px-4 py-2.5 rounded-lg bg-shell-bg-deep border border-white/10 text-sm text-shell-text outline-none focus:border-accent/40 transition-colors"
          />

          {error && <p className="text-xs text-red-400 mt-2" role="alert">{error}</p>}

          <button
            type="submit"
            disabled={loading || !password}
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
