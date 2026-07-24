import { create } from "zustand"

interface UiState {
  sidebarOpen: boolean
  toggleSidebar: () => void
  closeSidebar: () => void
}

/** Mobile sidebar drawer open/closed state — shared between Header (toggle button)
 * and Sidebar (the drawer itself), which are siblings under DashboardShell. */
export const useUiStore = create<UiState>((set) => ({
  sidebarOpen: false,
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  closeSidebar: () => set({ sidebarOpen: false }),
}))
