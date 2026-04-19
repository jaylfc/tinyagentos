/**
 * Two-line strip rendered between the last message and the composer.
 * Line 1: humans-typing. Line 2: agent-thinking.
 * Caller feeds in live arrays — they're empty when nothing is active
 * and the component renders nothing.
 */
export function TypingFooter({
  humans,
  agents,
  selfId = "user",
}: {
  humans: string[];
  agents: string[];
  selfId?: string;
}) {
  const others = humans.filter((h) => h !== selfId);
  const hasHumans = others.length > 0;
  const hasAgents = agents.length > 0;
  if (!hasHumans && !hasAgents) return null;

  const humanLine = formatHumansTyping(others);
  const agentLine = formatAgentsThinking(agents);

  return (
    <div
      aria-live="polite"
      className="px-4 pt-1 text-xs text-shell-text-tertiary flex flex-col gap-0.5"
    >
      {humanLine && <span>{humanLine}</span>}
      {agentLine && <span className="italic">{agentLine}</span>}
    </div>
  );
}

function formatHumansTyping(names: string[]): string | null {
  if (names.length === 0) return null;
  if (names.length === 1) return `${names[0]} is typing…`;
  if (names.length === 2) return `${names[0]} and ${names[1]} are typing…`;
  return `${names[0]} and ${names.length - 1} others are typing…`;
}

function formatAgentsThinking(slugs: string[]): string | null {
  if (slugs.length === 0) return null;
  return slugs.map((s) => `${s} is thinking…`).join(" · ");
}
