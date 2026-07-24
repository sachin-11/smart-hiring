"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"

import SkillTagInput from "@/components/SkillTagInput"
import DashboardShell from "@/components/layout/DashboardShell"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api"
import { extractErrorMessage } from "@/lib/errors"
import type { JobCreateRequest, JobDetailResponse } from "@/types/job"

export default function NewJobPage() {
  const router = useRouter()

  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [requiredSkills, setRequiredSkills] = useState<string[]>([])
  const [minExperience, setMinExperience] = useState("")
  const [maxExperience, setMaxExperience] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!title.trim() || !description.trim()) {
      setError("Title and description are required.")
      return
    }

    setSubmitting(true)
    try {
      const payload: JobCreateRequest = {
        title: title.trim(),
        description: description.trim(),
        required_skills: requiredSkills,
        min_experience: minExperience ? Number(minExperience) : null,
        max_experience: maxExperience ? Number(maxExperience) : null,
      }
      const { data: job } = await api.post<JobDetailResponse>("/jobs", payload)
      // Matching is auto-triggered by the matches page itself on load.
      router.push(`/jobs/${job.id}/matches`)
    } catch (err) {
      setError(extractErrorMessage(err, "Failed to create job. Please try again."))
      setSubmitting(false)
    }
  }

  return (
    <DashboardShell>
    <main className="mx-auto flex max-w-2xl flex-col gap-6">
      <h1 className="text-2xl font-bold">Create Job</h1>

      <form onSubmit={onSubmit} className="flex flex-col gap-5">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="title">Job title</Label>
          <Input
            id="title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Senior Backend Engineer"
            required
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="description">Job description</Label>
          <Textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe the role, responsibilities, and requirements..."
            rows={10}
            required
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label>Required skills</Label>
          <SkillTagInput value={requiredSkills} onChange={setRequiredSkills} />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="min-exp">Min experience (years)</Label>
            <Input
              id="min-exp"
              type="number"
              min={0}
              step={0.5}
              value={minExperience}
              onChange={(e) => setMinExperience(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="max-exp">Max experience (years)</Label>
            <Input
              id="max-exp"
              type="number"
              min={0}
              step={0.5}
              value={maxExperience}
              onChange={(e) => setMaxExperience(e.target.value)}
            />
          </div>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Button type="submit" disabled={submitting}>
          {submitting ? "Creating & analyzing..." : "Create Job & Find Matches"}
        </Button>
      </form>
    </main>
    </DashboardShell>
  )
}
