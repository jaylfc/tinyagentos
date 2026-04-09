import { useState, useEffect, useCallback } from "react";
import { Image, Wand2, Trash2, Download } from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface GeneratedImage {
  id: string;
  url: string;
  prompt: string;
  model: string;
  size: number;
  steps: number;
  seed: number;
  guidance: number;
  createdAt: string;
}

/* ------------------------------------------------------------------ */
/*  ImagesApp                                                          */
/* ------------------------------------------------------------------ */

export function ImagesApp({ windowId: _windowId }: { windowId: string }) {
  const [images, setImages] = useState<GeneratedImage[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);

  // Form state
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState("stable-diffusion");
  const [size, setSize] = useState(512);
  const [steps, setSteps] = useState(4);
  const [seed, setSeed] = useState("");
  const [guidance, setGuidance] = useState("7.5");

  const fetchImages = useCallback(async () => {
    try {
      const res = await fetch("/api/images", {
        headers: { Accept: "application/json" },
      });
      if (res.ok) {
        const ct = res.headers.get("content-type") ?? "";
        if (ct.includes("application/json")) {
          const data = await res.json();
          if (Array.isArray(data)) {
            setImages(data);
            setLoading(false);
            return;
          }
        }
      }
    } catch { /* fall through */ }
    setImages([]);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchImages();
  }, [fetchImages]);

  async function handleGenerate() {
    if (!prompt.trim()) return;
    setGenerating(true);

    const params = {
      prompt: prompt.trim(),
      model,
      size,
      steps,
      seed: seed ? parseInt(seed) : Math.floor(Math.random() * 999999),
      guidance: parseFloat(guidance) || 7.5,
    };

    try {
      const res = await fetch("/api/images/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      if (res.ok) {
        const ct = res.headers.get("content-type") ?? "";
        if (ct.includes("application/json")) {
          const data = await res.json();
          if (data.id) {
            setImages((prev) => [data, ...prev]);
          }
        }
      }
    } catch { /* ignore */ }

    // If no real API, add a placeholder
    if (images.length === 0 || true) {
      const placeholder: GeneratedImage = {
        id: `img-${Date.now()}`,
        url: "",
        prompt: params.prompt,
        model: params.model,
        size: params.size,
        steps: params.steps,
        seed: params.seed,
        guidance: params.guidance,
        createdAt: new Date().toISOString(),
      };
      setImages((prev) => {
        // Avoid duplicate if API already added it
        if (prev.find((i) => i.id === placeholder.id)) return prev;
        return [placeholder, ...prev];
      });
    }

    setGenerating(false);
  }

  function handleDelete(id: string) {
    setImages((prev) => prev.filter((img) => img.id !== id));
    fetch(`/api/images/${id}`, { method: "DELETE" }).catch(() => {});
  }

  function handleDownload(img: GeneratedImage) {
    if (!img.url) return;
    const a = document.createElement("a");
    a.href = img.url;
    a.download = `${img.prompt.slice(0, 30).replace(/\s+/g, "-")}-${img.seed}.png`;
    a.click();
  }

  return (
    <div className="flex flex-col h-full bg-shell-bg text-shell-text select-none">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5">
        <Image size={18} className="text-accent" />
        <h1 className="text-sm font-semibold">Images</h1>
        <span className="text-xs text-shell-text-tertiary">
          {images.length} generated
        </span>
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-5">
        {/* Generate form */}
        <div className="rounded-xl bg-shell-surface/60 border border-white/5 p-4 space-y-3">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <Wand2 size={14} className="text-accent" />
            Generate Image
          </h2>

          {/* Prompt */}
          <div>
            <label htmlFor="img-prompt" className="block text-xs text-shell-text-secondary mb-1.5">
              Prompt
            </label>
            <textarea
              id="img-prompt"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="A serene mountain landscape at sunset..."
              rows={3}
              className="w-full rounded-lg bg-shell-bg-deep px-3 py-2 text-sm text-shell-text placeholder:text-shell-text-tertiary border border-white/5 focus:outline-none focus:ring-1 focus:ring-accent resize-none"
            />
          </div>

          {/* Row of controls */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {/* Model */}
            <div>
              <label htmlFor="img-model" className="block text-xs text-shell-text-secondary mb-1.5">
                Model
              </label>
              <input
                id="img-model"
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="w-full rounded-lg bg-shell-bg-deep px-3 py-2 text-sm text-shell-text border border-white/5 focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>

            {/* Size */}
            <div>
              <label htmlFor="img-size" className="block text-xs text-shell-text-secondary mb-1.5">
                Size
              </label>
              <select
                id="img-size"
                value={size}
                onChange={(e) => setSize(parseInt(e.target.value))}
                className="w-full rounded-lg bg-shell-bg-deep px-3 py-2 text-sm text-shell-text border border-white/5 focus:outline-none focus:ring-1 focus:ring-accent"
              >
                <option value={256}>256x256</option>
                <option value={384}>384x384</option>
                <option value={512}>512x512</option>
              </select>
            </div>

            {/* Seed */}
            <div>
              <label htmlFor="img-seed" className="block text-xs text-shell-text-secondary mb-1.5">
                Seed
              </label>
              <input
                id="img-seed"
                type="number"
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
                placeholder="Random"
                className="w-full rounded-lg bg-shell-bg-deep px-3 py-2 text-sm text-shell-text placeholder:text-shell-text-tertiary border border-white/5 focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>

            {/* Guidance */}
            <div>
              <label htmlFor="img-guidance" className="block text-xs text-shell-text-secondary mb-1.5">
                Guidance
              </label>
              <input
                id="img-guidance"
                type="number"
                step="0.5"
                min="1"
                max="20"
                value={guidance}
                onChange={(e) => setGuidance(e.target.value)}
                className="w-full rounded-lg bg-shell-bg-deep px-3 py-2 text-sm text-shell-text border border-white/5 focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
          </div>

          {/* Steps slider */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label htmlFor="img-steps" className="text-xs text-shell-text-secondary">
                Steps
              </label>
              <span className="text-xs text-shell-text-tertiary tabular-nums">{steps}</span>
            </div>
            <input
              id="img-steps"
              type="range"
              min={1}
              max={8}
              value={steps}
              onChange={(e) => setSteps(parseInt(e.target.value))}
              className="w-full accent-accent"
            />
          </div>

          {/* Generate button */}
          <button
            onClick={handleGenerate}
            disabled={!prompt.trim() || generating}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium bg-accent text-white hover:bg-accent/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Wand2 size={14} />
            {generating ? "Generating..." : "Generate"}
          </button>

          {/* Loading spinner */}
          {generating && (
            <div className="flex items-center gap-2 text-xs text-shell-text-tertiary">
              <div className="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin" />
              Generating image...
            </div>
          )}
        </div>

        {/* Gallery */}
        {loading ? (
          <div className="text-center text-shell-text-tertiary text-sm py-8">
            Loading gallery...
          </div>
        ) : images.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 gap-3 text-shell-text-tertiary">
            <Image size={40} className="opacity-30" />
            <p className="text-sm">No images generated yet</p>
            <p className="text-xs">Use the form above to create your first image</p>
          </div>
        ) : (
          <div>
            <h2 className="text-sm font-medium text-shell-text-secondary mb-3">Gallery</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
              {images.map((img) => (
                <div
                  key={img.id}
                  className="rounded-xl bg-shell-surface/60 border border-white/5 overflow-hidden group"
                >
                  {/* Image area */}
                  <div
                    className="aspect-square bg-shell-bg-deep flex items-center justify-center"
                  >
                    {img.url ? (
                      <img
                        src={img.url}
                        alt={img.prompt}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="text-center px-3">
                        <Image size={24} className="mx-auto text-shell-text-tertiary mb-1" />
                        <p className="text-[10px] text-shell-text-tertiary line-clamp-2">{img.prompt}</p>
                      </div>
                    )}
                  </div>

                  {/* Caption */}
                  <div className="p-2.5 space-y-1">
                    <p className="text-xs line-clamp-2 leading-relaxed">{img.prompt}</p>
                    <div className="flex items-center gap-2 text-[10px] text-shell-text-tertiary">
                      <span>{img.model}</span>
                      <span>{img.size}px</span>
                      <span>{img.steps}st</span>
                    </div>
                    <div className="flex items-center gap-1 pt-1">
                      {img.url && (
                        <button
                          onClick={() => handleDownload(img)}
                          className="p-1 rounded-md hover:bg-white/5 transition-colors text-shell-text-secondary hover:text-shell-text"
                          aria-label={`Download image: ${img.prompt.slice(0, 30)}`}
                          title="Download"
                        >
                          <Download size={13} />
                        </button>
                      )}
                      <button
                        onClick={() => handleDelete(img.id)}
                        className="p-1 rounded-md hover:bg-red-500/15 transition-colors text-shell-text-secondary hover:text-red-400"
                        aria-label={`Delete image: ${img.prompt.slice(0, 30)}`}
                        title="Delete"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
