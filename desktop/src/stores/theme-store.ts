import { create } from "zustand";

const WALLPAPERS = [
  { id: "default", label: "Deep Indigo", style: "linear-gradient(160deg, #1a1b2e 0%, #1e2140 40%, #252848 100%)" },
  { id: "midnight", label: "Midnight Blue", style: "linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%)" },
  { id: "aurora", label: "Aurora", style: "linear-gradient(135deg, #0f2027 0%, #203a43 40%, #2c5364 100%)" },
  { id: "sunset", label: "Sunset", style: "linear-gradient(135deg, #1a1a2e 0%, #16213e 30%, #0f3460 60%, #533483 100%)" },
  { id: "forest", label: "Forest", style: "linear-gradient(160deg, #0d1b0e 0%, #1a2f1a 40%, #1e3a1e 100%)" },
  { id: "ocean", label: "Ocean", style: "linear-gradient(160deg, #0a192f 0%, #0d2847 40%, #112d4e 100%)" },
  { id: "charcoal", label: "Charcoal", style: "linear-gradient(180deg, #1c1c1c 0%, #2d2d2d 100%)" },
  { id: "nebula", label: "Nebula", style: "linear-gradient(135deg, #1a0a2e 0%, #2d1b4e 40%, #1a2a4e 100%)" },
];

interface ThemeStore {
  wallpaperId: string;
  wallpaperStyle: string;
  showDesktopIcons: boolean;

  setWallpaper: (id: string) => void;
  toggleDesktopIcons: () => void;
  getWallpapers: () => typeof WALLPAPERS;
}

export const useThemeStore = create<ThemeStore>((set) => ({
  wallpaperId: "default",
  wallpaperStyle: WALLPAPERS[0]!.style,
  showDesktopIcons: true,

  setWallpaper(id) {
    const wp = WALLPAPERS.find((w) => w.id === id);
    if (wp) {
      set({ wallpaperId: id, wallpaperStyle: wp.style });
    }
  },

  toggleDesktopIcons() {
    set((s) => ({ showDesktopIcons: !s.showDesktopIcons }));
  },

  getWallpapers: () => WALLPAPERS,
}));
