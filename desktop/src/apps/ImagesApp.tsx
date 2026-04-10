import { useState, useEffect, useCallback, useMemo } from "react";
import { Image, Wand2, Trash2, Download, Package } from "lucide-react";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Textarea,
} from "@/components/ui";
import { ModelBrowser } from "@/components/ModelBrowser";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface GeneratedImage {
  id: string;
  url: string;
  prompt: string;
  model: string;
  size: number | string;
  steps: number;
  seed: number;
  guidance: number;
  createdAt: string;
}

interface ModelVariant {
  id: string;
  name: string;
  format?: string;
  size_mb: number;
  min_ram_mb?: number;
  backend?: string[];
  downloaded?: boolean;
  compatibility: "green" | "yellow" | "red";
  download_url?: string;
}

interface ImageModel {
  id: string;
  name: string;
  description?: string;
  capabilities: string[];
  variants: ModelVariant[];
  has_downloaded_variant?: boolean;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

/* ------------------------------------------------------------------ */
/*  ImagesApp                                                          */
/* ------------------------------------------------------------------ */

export function ImagesApp({ windowId: _windowId }: { windowId: string }) {
  const [images, setImages] = useState<GeneratedImage[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Model catalog state
  const [models, setModels] = useState<ImageModel[]>([]);
  const [selectedModelId, setSelectedModelId] = useState<string>("");
  const [selectedVariantId, setSelectedVariantId] = useState<string>("");
  const [browserOpen, setBrowserOpen] = useState(false);

  // Form state (non-model)
  const [prompt, setPrompt] = useState("");
  const [size, setSize] = useState(512);
  const [steps, setSteps] = useState(4);
  const [seed, setSeed] = useState("");
  const [guidance, setGuidance] = useState("7.5");

  /* -------------------------- Images gallery --------------------- */

  const fetchImages = useCallback(async () => {
    try {
      const res = await fetch("/api/images", {
        headers: { Accept: "application/json" },
      });
      if (res.ok) {
        const ct = res.headers.get("content-type") ?? "";
        if (ct.includes("application/json")) {
          const data = await res.json();
          const list = Array.isArray(data)
            ? data
            : Array.isArray(data?.images)
              ? data.images
              : [];
          const mapped: GeneratedImage[] = list.map(
            (raw: Record<string, unknown>) => ({
              id: (raw.filename as string) ?? (raw.id as string) ?? "",
              url: (raw.path as string) ?? (raw.url as string) ?? "",
              prompt: (raw.prompt as string) ?? "",
              model: (raw.model as string) ?? "",
              size: (raw.size as string | number) ?? "",
              steps: (raw.steps as number) ?? 0,
              seed: (raw.seed as number) ?? 0,
              guidance: (raw.guidance_scale as number) ?? 0,
              createdAt:
                (raw.created_at as string) ?? new Date().toISOString(),
            }),
          );
          setImages(mapped);
          setLoading(false);
          return;
        }
      }
    } catch {
      /* fall through */
    }
    setImages([]);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchImages();
  }, [fetchImages]);

  /* -------------------------- Model catalog ---------------------- */

  const refreshModels = useCallback(async () => {
    try {
      const res = await fetch("/api/models", {
        headers: { Accept: "application/json" },
      });
      if (!res.ok) return [] as ImageModel[];
      const data = await res.json();
      if (!data || !Array.isArray(data.models)) return [] as ImageModel[];
      const imageModels: ImageModel[] = data.models.filter(
        (m: ImageModel) =>
          Array.isArray(m.capabilities) &&
          m.capabilities.includes("image-generation"),
      );
      setModels(imageModels);
      return imageModels;
    } catch {
      return [] as ImageModel[];
    }
  }, []);

  useEffect(() => {
    (async () => {
      const imageModels = await refreshModels();
      // Auto-select first downloaded variant
      for (const m of imageModels) {
        const dl = m.variants?.find((v) => v.downloaded);
        if (dl) {
          setSelectedModelId(m.id);
          setSelectedVariantId(dl.id);
          return;
        }
      }
    })();
  }, [refreshModels]);

  const selectedModel = useMemo(
    () => models.find((m) => m.id === selectedModelId),
    [models, selectedModelId],
  );
  const selectedVariant = useMemo(
    () => selectedModel?.variants.find((v) => v.id === selectedVariantId),
    [selectedModel, selectedVariantId],
  );

  // Flat list of usable (downloaded) variants for the dropdown
  const availableOptions = useMemo(() => {
    const options: Array<{
      modelId: string;
      variantId: string;
      label: string;
    }> = [];
    for (const m of models) {
      for (const v of m.variants ?? []) {
        if (v.downloaded) {
          options.push({
            modelId: m.id,
            variantId: v.id,
            label: `${m.name} — ${v.name}`,
          });
        }
      }
    }
    return options;
  }, [models]);

  const handleSelectChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value;
    if (value === "__browse__") {
      setBrowserOpen(true);
      return;
    }
    if (!value) return;
    const [modelId, variantId] = value.split("::");
    setSelectedModelId(modelId);
    setSelectedVariantId(variantId);
  };

  /* -------------------------- Generate --------------------------- */

  async function handleGenerate() {
    if (!prompt.trim()) return;
    if (!selectedVariant || !selectedVariant.downloaded) {
      setError("Select a downloaded model first.");
      return;
    }
    setGenerating(true);
    setError(null);

    const params = {
      prompt: prompt.trim(),
      model: selectedModelId,
      variant: selectedVariantId,
      size: `${size}x${size}`,
      steps,
      seed: seed ? parseInt(seed) : Math.floor(Math.random() * 999999),
      guidance_scale: parseFloat(guidance) || 7.5,
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
          if (data.filename || data.id) {
            await fetchImages();
          } else if (data.error) {
            setError(data.error);
          }
        }
      } else {
        const data = await res.json().catch(() => ({}));
        setError(
          (data as { error?: string }).error ??
            `Generation failed (${res.status})`,
        );
      }
    } catch (e) {
      setError(`Generation error: ${(e as Error).message}`);
    }

    setGenerating(false);
  }

  function handleDelete(id: string) {
    setImages((prev) => prev.filter((img) => img.id !== id));
    fetch(`/api/images/${encodeURIComponent(id)}`, { method: "DELETE" }).catch(
      () => {},
    );
  }

  function handleDownload(img: GeneratedImage) {
    if (!img.url) return;
    const a = document.createElement("a");
    a.href = img.url;
    a.download = `${img.prompt.slice(0, 30).replace(/\s+/g, "-")}-${img.seed}.png`;
    a.click();
  }

  /* -------------------------- Render ----------------------------- */

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
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Wand2 size={14} className="text-accent" />
              Generate Image
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {/* Prompt */}
            <div className="space-y-1.5">
              <Label htmlFor="img-prompt">Prompt</Label>
              <Textarea
                id="img-prompt"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="A serene mountain landscape at sunset..."
                rows={3}
                className="resize-none"
              />
            </div>

            {/* Model dropdown */}
            <div className="space-y-1.5">
              <Label htmlFor="img-model">Model</Label>
              <div className="flex items-center gap-2">
                <select
                  id="img-model"
                  value={
                    selectedModelId && selectedVariantId
                      ? `${selectedModelId}::${selectedVariantId}`
                      : ""
                  }
                  onChange={handleSelectChange}
                  className="flex-1 h-9 rounded-lg border border-white/10 bg-shell-bg-deep px-3 py-1 text-sm text-shell-text focus-visible:outline-none focus-visible:border-accent/40 focus-visible:ring-2 focus-visible:ring-accent/20"
                >
                  {availableOptions.length === 0 && (
                    <option value="">
                      No models available — click Browse…
                    </option>
                  )}
                  {availableOptions.map((opt) => (
                    <option
                      key={`${opt.modelId}::${opt.variantId}`}
                      value={`${opt.modelId}::${opt.variantId}`}
                    >
                      {"\u2713 "}
                      {opt.label}
                    </option>
                  ))}
                  <option disabled>────────</option>
                  <option value="__browse__">Get more models…</option>
                </select>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setBrowserOpen(true)}
                  type="button"
                >
                  <Package size={12} />
                  Browse
                </Button>
              </div>
              {!selectedVariant && availableOptions.length === 0 && (
                <div className="text-xs text-shell-text-tertiary mt-1">
                  Open the browser to download an image generation model.
                </div>
              )}
            </div>

            {/* Row of controls */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {/* Size */}
              <div className="space-y-1.5">
                <Label htmlFor="img-size">Size</Label>
                <select
                  id="img-size"
                  value={size}
                  onChange={(e) => setSize(parseInt(e.target.value))}
                  className="flex h-9 w-full rounded-lg border border-white/10 bg-shell-bg-deep px-3 py-1 text-sm text-shell-text focus-visible:outline-none focus-visible:border-accent/40 focus-visible:ring-2 focus-visible:ring-accent/20"
                >
                  <option value={256}>256x256</option>
                  <option value={384}>384x384</option>
                  <option value={512}>512x512</option>
                </select>
              </div>

              {/* Seed */}
              <div className="space-y-1.5">
                <Label htmlFor="img-seed">Seed</Label>
                <Input
                  id="img-seed"
                  type="number"
                  value={seed}
                  onChange={(e) => setSeed(e.target.value)}
                  placeholder="Random"
                />
              </div>

              {/* Guidance */}
              <div className="space-y-1.5">
                <Label htmlFor="img-guidance">Guidance</Label>
                <Input
                  id="img-guidance"
                  type="number"
                  step="0.5"
                  min="1"
                  max="20"
                  value={guidance}
                  onChange={(e) => setGuidance(e.target.value)}
                />
              </div>
            </div>

            {/* Steps slider */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <Label htmlFor="img-steps">Steps</Label>
                <span className="text-xs text-shell-text-tertiary tabular-nums">
                  {steps}
                </span>
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

            {/* Error */}
            {error && (
              <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
                {error}
              </div>
            )}

            {/* Generate button */}
            <Button
              size="lg"
              onClick={handleGenerate}
              disabled={
                !prompt.trim() ||
                generating ||
                !selectedVariant ||
                !selectedVariant.downloaded
              }
            >
              <Wand2 size={14} />
              {generating ? "Generating..." : "Generate"}
            </Button>

            {/* Loading spinner */}
            {generating && (
              <div className="flex items-center gap-2 text-xs text-shell-text-tertiary">
                <div className="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin" />
                Generating image...
              </div>
            )}
          </CardContent>
        </Card>

        {/* Gallery */}
        {loading ? (
          <div className="text-center text-shell-text-tertiary text-sm py-8">
            Loading gallery...
          </div>
        ) : images.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 gap-3 text-shell-text-tertiary">
            <Image size={40} className="opacity-30" />
            <p className="text-sm">No images generated yet</p>
            <p className="text-xs">
              Use the form above to create your first image
            </p>
          </div>
        ) : (
          <div>
            <h2 className="text-sm font-medium text-shell-text-secondary mb-3">
              Gallery
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
              {images.map((img) => (
                <Card key={img.id} className="overflow-hidden group">
                  <div className="aspect-square bg-shell-bg-deep flex items-center justify-center">
                    {img.url ? (
                      <img
                        src={img.url}
                        alt={img.prompt}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="text-center px-3">
                        <Image
                          size={24}
                          className="mx-auto text-shell-text-tertiary mb-1"
                        />
                        <p className="text-[10px] text-shell-text-tertiary line-clamp-2">
                          {img.prompt}
                        </p>
                      </div>
                    )}
                  </div>

                  <CardContent className="p-2.5 space-y-1">
                    <p className="text-xs line-clamp-2 leading-relaxed">
                      {img.prompt}
                    </p>
                    <div className="flex items-center gap-2 text-[10px] text-shell-text-tertiary">
                      <span>{img.model}</span>
                      <span>
                        {typeof img.size === "number"
                          ? `${img.size}px`
                          : img.size}
                      </span>
                      <span>{img.steps}st</span>
                    </div>
                    <div className="flex items-center gap-1 pt-1">
                      {img.url && (
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleDownload(img)}
                          className="h-7 w-7"
                          aria-label={`Download image: ${img.prompt.slice(0, 30)}`}
                          title="Download"
                        >
                          <Download size={13} />
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleDelete(img.id)}
                        className="h-7 w-7 hover:text-red-400 hover:bg-red-500/15"
                        aria-label={`Delete image: ${img.prompt.slice(0, 30)}`}
                        title="Delete"
                      >
                        <Trash2 size={13} />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}
      </div>

      <ModelBrowser
        open={browserOpen}
        onClose={() => setBrowserOpen(false)}
        capability="image-generation"
        onModelDownloaded={async (modelId, variantId) => {
          await refreshModels();
          setSelectedModelId(modelId);
          setSelectedVariantId(variantId);
        }}
      />
    </div>
  );
}
