import { create } from "zustand"
import { persist } from "zustand/middleware"

interface JobState {
  currentJobId: string | null
  currentJobTitle: string | null
  setCurrentJob: (id: string | null, title: string | null) => void
}

/** The recruiter's currently-focused job, shared across the jobs/candidates pages
 * (e.g. "bulk email selected candidates" defaults to this job). Persisted so it
 * survives a page refresh. */
export const useJobStore = create<JobState>()(
  persist(
    (set) => ({
      currentJobId: null,
      currentJobTitle: null,
      setCurrentJob: (id, title) => set({ currentJobId: id, currentJobTitle: title }),
    }),
    { name: "smart-hiring-current-job" }
  )
)
