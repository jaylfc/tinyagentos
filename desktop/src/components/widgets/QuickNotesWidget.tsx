import { useState, useCallback } from "react";

const STORAGE_KEY = "tinyagentos-quick-notes";

export function QuickNotesWidget() {
  const [text, setText] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) ?? "";
    } catch {
      return "";
    }
  });

  const handleChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setText(val);
    try {
      localStorage.setItem(STORAGE_KEY, val);
    } catch {
      // storage full or unavailable
    }
  }, []);

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", padding: 4 }}>
      <div style={{ fontSize: "0.7rem", fontWeight: 600, color: "rgba(255,255,255,0.5)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 }}>
        Quick Notes
      </div>
      <textarea
        value={text}
        onChange={handleChange}
        placeholder="Type your notes here..."
        aria-label="Quick notes"
        style={{
          flex: 1,
          resize: "none",
          background: "rgba(255,255,255,0.05)",
          border: "1px solid rgba(255,255,255,0.1)",
          borderRadius: 6,
          color: "#fff",
          fontSize: "0.8rem",
          padding: 8,
          outline: "none",
          fontFamily: "inherit",
          lineHeight: 1.5,
        }}
      />
    </div>
  );
}
