// Per-framework default emoji used when an agent doesn't have an explicit
// emoji of its own. Kept lightweight — a single lookup + a fallback, no
// library, so the whole rendering path is one function call.

const FRAMEWORK_EMOJI: Record<string, string> = {
  openclaw: "\u{1F916}",          // 🤖
  smolagents: "\u{1F9EA}",        // 🧪
  generic: "\u{1F916}",           // 🤖
  pocketflow: "\u{1F517}",        // 🔗
  langroid: "\u{1F333}",          // 🌳
  "openai-agents-sdk": "\u{1F4AC}", // 💬
  agent_zero: "\u{1F9E0}",        // 🧠
  hermes: "\u{1F4EE}",            // 📮
  ironclaw: "\u{1F9F2}",          // 🧲
  microclaw: "\u{1F9A0}",         // 🦠
  moltis: "\u{1F9EC}",            // 🧬
  nanoclaw: "\u{2728}",           // ✨
  nullclaw: "\u{26AB}",           // ⚫
  picoclaw: "\u{1F539}",          // 🔹
  shibaclaw: "\u{1F436}",         // 🐶
  zeroclaw: "\u{1F300}",          // 🌀
};

const DEFAULT_EMOJI = "\u{1F916}"; // 🤖

/**
 * Return the default unicode emoji for a given framework id.
 * Always returns a non-empty string — falls back to the generic robot.
 */
export function defaultEmojiForFramework(framework: string | undefined | null): string {
  if (!framework) return DEFAULT_EMOJI;
  return FRAMEWORK_EMOJI[framework] ?? DEFAULT_EMOJI;
}

/**
 * Resolve the emoji to show for an agent.  Prefers the per-agent emoji,
 * falls back to the framework default, falls back to the generic robot.
 */
export function resolveAgentEmoji(
  agentEmoji: string | undefined | null,
  framework: string | undefined | null,
): string {
  const trimmed = (agentEmoji ?? "").trim();
  if (trimmed) return trimmed;
  return defaultEmojiForFramework(framework);
}

/**
 * A small quick-pick palette covering common categories (faces, animals,
 * objects, symbols).  Users can still paste any unicode into the input.
 */
export const EMOJI_QUICK_PICKS: readonly string[] = [
  "\u{1F916}", // 🤖
  "\u{1F98A}", // 🦊
  "\u{1F436}", // 🐶
  "\u{1F431}", // 🐱
  "\u{1F525}", // 🔥
  "\u{2B50}", // ⭐
  "\u{1F9EA}", // 🧪
  "\u{1F9E0}", // 🧠
  "\u{1F4A1}", // 💡
  "\u{1F680}", // 🚀
  "\u{1F308}", // 🌈
  "\u{1F47B}", // 👻
];
