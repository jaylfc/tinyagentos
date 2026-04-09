import { useEffect, useRef, useState } from "react";
import { init } from "pell";
import "pell/dist/pell.min.css";

export function TextEditorApp({ windowId: _windowId }: { windowId: string }) {
  const editorRef = useRef<HTMLDivElement>(null);
  const [wordCount, setWordCount] = useState(0);

  useEffect(() => {
    if (!editorRef.current) return;
    if (editorRef.current.querySelector(".pell-actionbar")) return;

    const editor = init({
      element: editorRef.current,
      onChange: (html) => {
        const text = new DOMParser()
          .parseFromString(html, "text/html")
          .body.textContent?.trim() ?? "";
        setWordCount(text ? text.split(/\s+/).length : 0);
      },
      actions: [
        "bold",
        "italic",
        "underline",
        "strikethrough",
        "heading1",
        "heading2",
        "olist",
        "ulist",
        "link",
        "image",
        "line",
      ],
    });

    editor.content.setAttribute("aria-label", "Text editor content");
  }, []);

  return (
    <div className="flex flex-col h-full bg-shell-surface text-shell-text">
      <div
        ref={editorRef}
        className={[
          "flex flex-col flex-1 min-h-0",
          "[&_.pell-actionbar]:flex [&_.pell-actionbar]:flex-wrap [&_.pell-actionbar]:gap-0.5 [&_.pell-actionbar]:p-2",
          "[&_.pell-actionbar]:bg-shell-surface-raised [&_.pell-actionbar]:border-b [&_.pell-actionbar]:border-shell-border",
          "[&_.pell-actionbar_button]:px-2 [&_.pell-actionbar_button]:py-1 [&_.pell-actionbar_button]:rounded",
          "[&_.pell-actionbar_button]:text-shell-text-secondary [&_.pell-actionbar_button]:bg-transparent",
          "[&_.pell-actionbar_button]:hover:bg-shell-hover [&_.pell-actionbar_button]:hover:text-shell-text",
          "[&_.pell-actionbar_button]:transition-colors [&_.pell-actionbar_button]:text-sm [&_.pell-actionbar_button]:font-medium",
          "[&_.pell-content]:flex-1 [&_.pell-content]:p-4 [&_.pell-content]:overflow-y-auto",
          "[&_.pell-content]:outline-none [&_.pell-content]:text-shell-text [&_.pell-content]:leading-relaxed",
          "[&_.pell-content_h1]:text-2xl [&_.pell-content_h1]:font-bold [&_.pell-content_h1]:mb-2",
          "[&_.pell-content_h2]:text-xl [&_.pell-content_h2]:font-semibold [&_.pell-content_h2]:mb-2",
          "[&_.pell-content_ul]:list-disc [&_.pell-content_ul]:ml-6",
          "[&_.pell-content_ol]:list-decimal [&_.pell-content_ol]:ml-6",
          "[&_.pell-content_a]:text-shell-accent [&_.pell-content_a]:underline",
        ].join(" ")}
      />
      <div className="flex items-center justify-between px-4 py-1.5 text-xs text-shell-text-secondary bg-shell-surface-raised border-t border-shell-border">
        <span>{wordCount} {wordCount === 1 ? "word" : "words"}</span>
      </div>
    </div>
  );
}
