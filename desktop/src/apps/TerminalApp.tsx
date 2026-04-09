import { useEffect, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";

const WELCOME = [
  "\x1b[1;36mTinyAgentOS Terminal v0.1\x1b[0m",
  "Type \x1b[33mhelp\x1b[0m for available commands.\r\n",
];

const PROMPT = "\x1b[1;35mtinyos\x1b[0m \x1b[34m~\x1b[0m $ ";

const HELP_TEXT = [
  "Available commands:",
  "  help     - Show this message",
  "  clear    - Clear the terminal",
  "  whoami   - Print current user",
  "  date     - Print current date/time",
  "  echo     - Echo arguments back",
  "  uname    - System information",
];

function handleCommand(cmd: string, term: Terminal) {
  const parts = cmd.trim().split(/\s+/);
  const command = parts[0]?.toLowerCase() ?? "";
  const args = parts.slice(1).join(" ");

  switch (command) {
    case "":
      break;
    case "help":
      HELP_TEXT.forEach((l) => term.writeln(l));
      break;
    case "clear":
      term.clear();
      break;
    case "whoami":
      term.writeln("agent");
      break;
    case "date":
      term.writeln(new Date().toString());
      break;
    case "echo":
      term.writeln(args);
      break;
    case "uname":
      term.writeln("TinyAgentOS 0.1.0 aarch64");
      break;
    default:
      term.writeln(`\x1b[31mcommand not found:\x1b[0m ${command}`);
  }
}

export function TerminalApp({ windowId: _windowId }: { windowId: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const term = new Terminal({
      theme: {
        background: "#151625",
        foreground: "rgba(255, 255, 255, 0.85)",
        cursor: "#667eea",
        selectionBackground: "rgba(102, 126, 234, 0.3)",
        black: "#1a1b2e",
        red: "#f87171",
        green: "#4ade80",
        yellow: "#fbbf24",
        blue: "#667eea",
        magenta: "#a78bfa",
        cyan: "#22d3ee",
        white: "rgba(255, 255, 255, 0.85)",
      },
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
      fontSize: 14,
      lineHeight: 1.4,
      cursorBlink: true,
      cursorStyle: "bar",
      allowProposedApi: true,
    });

    termRef.current = term;
    term.open(containerRef.current);

    // Welcome message
    WELCOME.forEach((l) => term.writeln(l));
    term.write(PROMPT);

    let currentLine = "";

    term.onKey(({ key, domEvent }) => {
      const code = domEvent.keyCode;

      if (code === 13) {
        // Enter
        term.writeln("");
        handleCommand(currentLine, term);
        currentLine = "";
        term.write(PROMPT);
      } else if (code === 8) {
        // Backspace
        if (currentLine.length > 0) {
          currentLine = currentLine.slice(0, -1);
          term.write("\b \b");
        }
      } else if (code === 12) {
        // Ctrl+L
        term.clear();
        term.write(PROMPT + currentLine);
      } else if (domEvent.ctrlKey && code === 67) {
        // Ctrl+C
        term.writeln("^C");
        currentLine = "";
        term.write(PROMPT);
      } else if (key.length === 1 && !domEvent.ctrlKey && !domEvent.altKey) {
        currentLine += key;
        term.write(key);
      }
    });

    // Fit terminal to container
    const observer = new ResizeObserver(() => {
      try {
        const dims = containerRef.current?.getBoundingClientRect();
        if (dims) {
          const cols = Math.floor((dims.width - 20) / 8.4);
          const rows = Math.floor((dims.height - 10) / (14 * 1.4));
          if (cols > 0 && rows > 0) {
            term.resize(cols, rows);
          }
        }
      } catch {
        // ignore resize errors
      }
    });

    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      term.dispose();
      termRef.current = null;
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className="h-full w-full"
      style={{ background: "#151625", padding: "4px" }}
    />
  );
}
