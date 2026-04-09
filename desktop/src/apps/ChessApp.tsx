import { useState, useCallback, useEffect, useRef } from "react";
import { Chess, type Square } from "chess.js";

type GameMode = "two-player" | "vs-agent";

const PIECE_SYMBOLS: Record<string, Record<string, string>> = {
  w: { k: "♔", q: "♕", r: "♖", b: "♗", n: "♘", p: "♙" },
  b: { k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟" },
};

const LIGHT = "#f0d9b5";
const DARK = "#b58863";
const SELECTED_BG = "#829769";
const VALID_MOVE_DOT = "rgba(0,0,0,0.25)";
const VALID_CAPTURE = "rgba(0,0,0,0.25)";

function squareName(row: number, col: number): Square {
  const file = String.fromCharCode(97 + col);
  const rank = String(8 - row);
  return (file + rank) as Square;
}

export function ChessApp({ windowId: _windowId }: { windowId: string }) {
  const [game, setGame] = useState(() => new Chess());
  const [selected, setSelected] = useState<Square | null>(null);
  const [validMoves, setValidMoves] = useState<Square[]>([]);
  const [mode, setMode] = useState<GameMode>("two-player");
  const [agentThinking, setAgentThinking] = useState(false);
  const agentTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const board = game.board();
  const turn = game.turn();
  const history = game.history();
  const isCheck = game.isCheck();
  const isCheckmate = game.isCheckmate();
  const isStalemate = game.isStalemate();
  const isDraw = game.isDraw();
  const isGameOver = game.isGameOver();

  const makeAgentMove = useCallback(
    (g: Chess) => {
      if (g.isGameOver()) return;
      setAgentThinking(true);
      const delay = 500 + Math.random() * 500;
      agentTimerRef.current = setTimeout(() => {
        const moves = g.moves();
        if (moves.length === 0) return;
        const pick = moves[Math.floor(Math.random() * moves.length)]!;
        g.move(pick);
        setGame(new Chess(g.fen()));
        setAgentThinking(false);
      }, delay);
    },
    [],
  );

  useEffect(() => {
    return () => {
      if (agentTimerRef.current) clearTimeout(agentTimerRef.current);
    };
  }, []);

  // Trigger agent move when it's black's turn in agent mode
  useEffect(() => {
    if (mode === "vs-agent" && turn === "b" && !isGameOver && !agentThinking) {
      makeAgentMove(game);
    }
  }, [mode, turn, isGameOver, agentThinking, game, makeAgentMove]);

  function handleSquareClick(row: number, col: number) {
    if (isGameOver || agentThinking) return;
    if (mode === "vs-agent" && turn === "b") return;

    const sq = squareName(row, col);

    if (selected) {
      // Try to move
      const moveObj = game.moves({ verbose: true }).find(
        (m) => m.from === selected && m.to === sq,
      );
      if (moveObj) {
        // For simplicity, auto-queen promotion
        const promo = moveObj.flags.includes("p") ? "q" : undefined;
        game.move({ from: selected, to: sq, promotion: promo });
        setGame(new Chess(game.fen()));
        setSelected(null);
        setValidMoves([]);
        return;
      }

      // Clicked own piece — reselect
      const piece = board[row]![col];
      if (piece && piece.color === turn) {
        setSelected(sq);
        setValidMoves(
          game
            .moves({ square: sq, verbose: true })
            .map((m) => m.to as Square),
        );
        return;
      }

      // Deselect
      setSelected(null);
      setValidMoves([]);
      return;
    }

    // Nothing selected — select own piece
    const piece = board[row]![col];
    if (piece && piece.color === turn) {
      setSelected(sq);
      setValidMoves(
        game.moves({ square: sq, verbose: true }).map((m) => m.to as Square),
      );
    }
  }

  function handleNewGame() {
    if (agentTimerRef.current) clearTimeout(agentTimerRef.current);
    const fresh = new Chess();
    setGame(fresh);
    setSelected(null);
    setValidMoves([]);
    setAgentThinking(false);
  }

  function handleUndo() {
    if (agentThinking) return;
    if (mode === "vs-agent") {
      // Undo both agent and player move
      game.undo();
      game.undo();
    } else {
      game.undo();
    }
    setGame(new Chess(game.fen()));
    setSelected(null);
    setValidMoves([]);
  }

  function handleModeChange(newMode: GameMode) {
    if (agentTimerRef.current) clearTimeout(agentTimerRef.current);
    setMode(newMode);
    const fresh = new Chess();
    setGame(fresh);
    setSelected(null);
    setValidMoves([]);
    setAgentThinking(false);
  }

  function getStatus(): string {
    if (isCheckmate) return `Checkmate! ${turn === "w" ? "Black" : "White"} wins`;
    if (isStalemate) return "Stalemate — Draw";
    if (isDraw) return "Draw";
    if (agentThinking) return "Agent thinking...";
    const side = turn === "w" ? "White" : "Black";
    return `${side} to move${isCheck ? " (Check!)" : ""}`;
  }

  return (
    <div
      style={{
        display: "flex",
        height: "100%",
        background: "#1a1a2e",
        color: "#e0e0e0",
        fontFamily: "'Segoe UI', system-ui, sans-serif",
        overflow: "hidden",
      }}
    >
      {/* Board area */}
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: 16,
          minWidth: 0,
        }}
      >
        {/* Status */}
        <div
          style={{
            fontSize: 16,
            fontWeight: 600,
            marginBottom: 10,
            color: isCheckmate ? "#ff6b6b" : isCheck ? "#ffa726" : "#e0e0e0",
          }}
          role="status"
          aria-live="polite"
        >
          {getStatus()}
        </div>

        {/* Board */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(8, 1fr)",
            gridTemplateRows: "repeat(8, 1fr)",
            width: "min(100%, 480px)",
            aspectRatio: "1",
            borderRadius: 4,
            overflow: "hidden",
            boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
          }}
          role="grid"
          aria-label="Chess board"
        >
          {board.map((row, r) =>
            row.map((piece, c) => {
              const sq = squareName(r, c);
              const isLight = (r + c) % 2 === 0;
              const isSelected = selected === sq;
              const isValidTarget = validMoves.includes(sq);
              const hasPiece = piece !== null;

              let bg = isLight ? LIGHT : DARK;
              if (isSelected) bg = SELECTED_BG;

              return (
                <button
                  key={sq}
                  onClick={() => handleSquareClick(r, c)}
                  aria-label={`${sq}${piece ? ` ${piece.color === "w" ? "white" : "black"} ${piece.type}` : ""}`}
                  style={{
                    background: bg,
                    border: "none",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    position: "relative",
                    fontSize: "clamp(24px, 5vw, 48px)",
                    lineHeight: 1,
                    padding: 0,
                    color: piece?.color === "b" ? "#1a1a1a" : "#fff",
                    textShadow:
                      piece?.color === "w"
                        ? "0 1px 3px rgba(0,0,0,0.4)"
                        : "0 1px 2px rgba(255,255,255,0.15)",
                  }}
                >
                  {/* Valid move indicator */}
                  {isValidTarget && !hasPiece && (
                    <div
                      style={{
                        position: "absolute",
                        width: "30%",
                        height: "30%",
                        borderRadius: "50%",
                        background: VALID_MOVE_DOT,
                      }}
                    />
                  )}
                  {isValidTarget && hasPiece && (
                    <div
                      style={{
                        position: "absolute",
                        inset: 2,
                        borderRadius: "50%",
                        border: `3px solid ${VALID_CAPTURE}`,
                      }}
                    />
                  )}
                  {piece && PIECE_SYMBOLS[piece.color]![piece.type]}
                </button>
              );
            }),
          )}
        </div>

        {/* Controls */}
        <div
          style={{
            display: "flex",
            gap: 8,
            marginTop: 12,
            flexWrap: "wrap",
            justifyContent: "center",
          }}
        >
          <select
            value={mode}
            onChange={(e) => handleModeChange(e.target.value as GameMode)}
            aria-label="Game mode"
            style={{
              padding: "6px 10px",
              borderRadius: 4,
              border: "1px solid #444",
              background: "#2a2a3e",
              color: "#e0e0e0",
              fontSize: 13,
              cursor: "pointer",
            }}
          >
            <option value="two-player">Two Player</option>
            <option value="vs-agent">Play vs Agent</option>
          </select>
          <button
            onClick={handleNewGame}
            aria-label="New game"
            style={{
              padding: "6px 14px",
              borderRadius: 4,
              border: "1px solid #444",
              background: "#2a2a3e",
              color: "#e0e0e0",
              fontSize: 13,
              cursor: "pointer",
            }}
          >
            New Game
          </button>
          <button
            onClick={handleUndo}
            disabled={history.length === 0 || agentThinking}
            aria-label="Undo move"
            style={{
              padding: "6px 14px",
              borderRadius: 4,
              border: "1px solid #444",
              background: "#2a2a3e",
              color: history.length === 0 || agentThinking ? "#666" : "#e0e0e0",
              fontSize: 13,
              cursor: history.length === 0 || agentThinking ? "default" : "pointer",
            }}
          >
            Undo
          </button>
        </div>
      </div>

      {/* Move history sidebar */}
      <div
        style={{
          width: 180,
          borderLeft: "1px solid #333",
          display: "flex",
          flexDirection: "column",
          background: "#16162a",
        }}
      >
        <div
          style={{
            padding: "10px 12px",
            fontSize: 13,
            fontWeight: 600,
            borderBottom: "1px solid #333",
            color: "#aaa",
          }}
        >
          Moves
        </div>
        <div
          style={{
            flex: 1,
            overflowY: "auto",
            padding: "8px 12px",
            fontSize: 13,
            lineHeight: 1.8,
          }}
          role="log"
          aria-label="Move history"
        >
          {history.length === 0 && (
            <span style={{ color: "#555", fontStyle: "italic" }}>No moves yet</span>
          )}
          {Array.from({ length: Math.ceil(history.length / 2) }).map((_, i) => (
            <div key={i} style={{ display: "flex", gap: 6 }}>
              <span style={{ color: "#666", minWidth: 24 }}>{i + 1}.</span>
              <span style={{ color: "#ddd", minWidth: 40 }}>{history[i * 2]}</span>
              <span style={{ color: "#aaa" }}>{history[i * 2 + 1] ?? ""}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
