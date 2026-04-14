import { create } from "zustand";

// Wallpapers are split into (image, fallback) pairs rather than a single
// background-shorthand so CSS media queries can control background-size
// per viewport (cover on desktop, contain on mobile so the full image is
// visible instead of cropped at the edges).

interface Wallpaper {
  id: string;
  label: string;
  image: string; // assigned to CSS background-image
  fallback: string; // assigned to CSS background-color
}

const WALLPAPERS: Wallpaper[] = [
  {
    id: "default",
    label: "Default",
    image: "url('/static/wallpaper.png')",
    fallback: "#1a1b2e",
  },
  {
    id: "deep-indigo",
    label: "Deep Indigo",
    image: "linear-gradient(160deg, #1a1b2e 0%, #1e2140 40%, #252848 100%)",
    fallback: "#1a1b2e",
  },
  {
    id: "midnight",
    label: "Midnight Blue",
    image: "linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%)",
    fallback: "#0f0c29",
  },
  {
    id: "aurora",
    label: "Aurora",
    image: "linear-gradient(135deg, #0f2027 0%, #203a43 40%, #2c5364 100%)",
    fallback: "#0f2027",
  },
  {
    id: "sunset",
    label: "Sunset",
    image: "linear-gradient(135deg, #1a1a2e 0%, #16213e 30%, #0f3460 60%, #533483 100%)",
    fallback: "#1a1a2e",
  },
  {
    id: "forest",
    label: "Forest",
    image: "linear-gradient(160deg, #0d1b0e 0%, #1a2f1a 40%, #1e3a1e 100%)",
    fallback: "#0d1b0e",
  },
  {
    id: "ocean",
    label: "Ocean",
    image: "linear-gradient(160deg, #0a192f 0%, #0d2847 40%, #112d4e 100%)",
    fallback: "#0a192f",
  },
  {
    id: "charcoal",
    label: "Charcoal",
    image: "linear-gradient(180deg, #1c1c1c 0%, #2d2d2d 100%)",
    fallback: "#1c1c1c",
  },
  {
    id: "nebula",
    label: "Nebula",
    image: "linear-gradient(135deg, #1a0a2e 0%, #2d1b4e 40%, #1a2a4e 100%)",
    fallback: "#1a0a2e",
  },
];

interface ThemeStore {
  wallpaperId: string;
  wallpaperImage: string;
  wallpaperFallback: string;
  showDesktopIcons: boolean;

  setWallpaper: (id: string) => void;
  toggleDesktopIcons: () => void;
  getWallpapers: () => Wallpaper[];
}

export const useThemeStore = create<ThemeStore>((set) => ({
  wallpaperId: "default",
  wallpaperImage: WALLPAPERS[0]!.image,
  wallpaperFallback: WALLPAPERS[0]!.fallback,
  showDesktopIcons: true,

  setWallpaper(id) {
    const wp = WALLPAPERS.find((w) => w.id === id);
    if (wp) {
      set({
        wallpaperId: id,
        wallpaperImage: wp.image,
        wallpaperFallback: wp.fallback,
      });
    }
  },

  toggleDesktopIcons() {
    set((s) => ({ showDesktopIcons: !s.showDesktopIcons }));
  },

  getWallpapers: () => WALLPAPERS,
}));
