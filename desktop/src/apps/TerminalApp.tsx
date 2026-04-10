import { useEffect, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import "@xterm/xterm/css/xterm.css";

export function TerminalApp({ windowId: _windowId }: { windowId: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const fitRef = useRef<FitAddon | null>(null);

  useEffect(() => {
    if (!containerRef.current || termRef.current) return;

    const term = new Terminal({
      theme: {
        background: "#151625",
        foreground: "rgba(255, 255, 255, 0.85)",
        cursor: "#667eea",
        cursorAccent: "#151625",
        selectionBackground: "rgba(102, 126, 234, 0.3)",
        black: "#1a1b2e",
        red: "#ff5f57",
        green: "#28c840",
        yellow: "#febc2e",
        blue: "#667eea",
        magenta: "#f093fb",
        cyan: "#4facfe",
        white: "rgba(255,255,255,0.85)",
        brightBlack: "#555",
        brightRed: "#ff6b6b",
        brightGreen: "#51cf66",
        brightYellow: "#ffd43b",
        brightBlue: "#748ffc",
        brightMagenta: "#e599f7",
        brightCyan: "#66d9e8",
        brightWhite: "#ffffff",
      },
      fontFamily:
        "'JetBrains Mono', 'Fira Code', 'MesloLGS NF', 'Hack Nerd Font', 'Cascadia Code', 'SF Mono', monospace",
      fontSize: 14,
      lineHeight: 1.2,
      cursorBlink: true,
      cursorStyle: "bar",
      allowProposedApi: true,
    });

    const fit = new FitAddon();
    const webLinks = new WebLinksAddon();
    term.loadAddon(fit);
    term.loadAddon(webLinks);

    term.open(containerRef.current);
    fit.fit();
    fitRef.current = fit;
    termRef.current = term;

    // Connect WebSocket to /ws/terminal
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(
      `${proto}//${window.location.host}/ws/terminal`,
    );
    wsRef.current = ws;

    ws.onopen = () => {
      // Send initial size
      ws.send(
        JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }),
      );
    };

    ws.onmessage = (event) => {
      term.write(event.data);
    };

    ws.onerror = () => {
      term.writeln("\r\n\x1b[31mWebSocket connection error\x1b[0m");
    };

    ws.onclose = () => {
      term.writeln("\r\n\x1b[33mConnection closed\x1b[0m");
    };

    // Forward terminal input to WebSocket
    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(data);
      }
    });

    // Handle resize
    const resizeObserver = new ResizeObserver(() => {
      fit.fit();
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(
          JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }),
        );
      }
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      ws.close();
      term.dispose();
      termRef.current = null;
      wsRef.current = null;
      fitRef.current = null;
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className="h-full w-full"
      style={{ backgroundColor: "#151625" }}
    />
  );
}
