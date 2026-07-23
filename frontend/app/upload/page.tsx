"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useDropzone } from "react-dropzone"

import ResumeCard from "@/components/ResumeCard"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"
import type { ResumeDetailResponse, ResumeStatusResponse, ResumeUploadResponse } from "@/types/resume"

type Stage = "idle" | "uploading" | "processing" | "completed" | "failed"

const POLL_INTERVAL_MS = 2000
const MAX_POLL_ATTEMPTS = 60 // ~2 minutes

export default function UploadPage() {
  const [stage, setStage] = useState<Stage>("idle")
  const [uploadProgress, setUploadProgress] = useState(0)
  const [candidateId, setCandidateId] = useState<string | null>(null)
  const [resume, setResume] = useState<ResumeDetailResponse | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const pollAttemptsRef = useRef(0)
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const reset = useCallback(() => {
    if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current)
    pollAttemptsRef.current = 0
    setStage("idle")
    setUploadProgress(0)
    setCandidateId(null)
    setResume(null)
    setErrorMessage(null)
  }, [])

  const pollStatus = useCallback((id: string) => {
    const tick = async () => {
      pollAttemptsRef.current += 1
      try {
        const { data } = await api.get<ResumeStatusResponse>(`/resume/${id}/status`)

        if (data.status === "completed") {
          const { data: detail } = await api.get<ResumeDetailResponse>(`/resume/${id}`)
          setResume(detail)
          setStage("completed")
          return
        }

        if (data.status === "failed") {
          setErrorMessage(data.error ?? "Resume parsing failed")
          setStage("failed")
          return
        }

        if (pollAttemptsRef.current >= MAX_POLL_ATTEMPTS) {
          setErrorMessage("Parsing is taking longer than expected. Please try again later.")
          setStage("failed")
          return
        }

        pollTimeoutRef.current = setTimeout(tick, POLL_INTERVAL_MS)
      } catch {
        setErrorMessage("Lost connection while checking parsing status.")
        setStage("failed")
      }
    }

    pollTimeoutRef.current = setTimeout(tick, POLL_INTERVAL_MS)
  }, [])

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      const file = acceptedFiles[0]
      if (!file) return

      setStage("uploading")
      setUploadProgress(0)
      setErrorMessage(null)

      const formData = new FormData()
      formData.append("file", file)

      try {
        const { data } = await api.post<ResumeUploadResponse>("/resume/upload", formData, {
          headers: { "Content-Type": "multipart/form-data" },
          onUploadProgress: (event) => {
            if (event.total) {
              setUploadProgress(Math.round((event.loaded / event.total) * 100))
            }
          },
        })

        setCandidateId(data.candidate_id)
        setStage("processing")
        pollAttemptsRef.current = 0
        pollStatus(data.candidate_id)
      } catch (err) {
        const message =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          "Upload failed. Please try again."
        setErrorMessage(message)
        setStage("failed")
      }
    },
    [pollStatus]
  )

  useEffect(() => {
    return () => {
      if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current)
    }
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    },
    maxFiles: 1,
    disabled: stage === "uploading" || stage === "processing",
  })

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center gap-6 p-8">
      <h1 className="text-2xl font-bold">Upload Resume</h1>

      {(stage === "idle" || stage === "uploading" || stage === "processing") && (
        <div
          {...getRootProps()}
          className={`flex w-full max-w-xl cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-12 text-center transition-colors ${
            isDragActive ? "border-primary bg-muted" : "border-border"
          }`}
        >
          <input {...getInputProps()} />
          {stage === "idle" && (
            <>
              <p className="font-medium">Drag & drop a resume here, or click to select</p>
              <p className="text-sm text-muted-foreground">PDF or DOCX, up to 10MB</p>
            </>
          )}
          {stage === "uploading" && (
            <p className="font-medium">Uploading… {uploadProgress}%</p>
          )}
          {stage === "processing" && (
            <p className="font-medium">Parsing resume with AI… this can take a few seconds</p>
          )}
        </div>
      )}

      {stage === "failed" && (
        <div className="flex w-full max-w-xl flex-col items-center gap-3 rounded-xl border border-destructive/50 p-8 text-center">
          <p className="font-medium text-destructive">{errorMessage}</p>
          <Button onClick={reset}>Try again</Button>
        </div>
      )}

      {stage === "completed" && resume && (
        <div className="flex w-full flex-col items-center gap-4">
          <ResumeCard resume={resume} />
          <Button onClick={reset}>Upload another resume</Button>
        </div>
      )}

      {candidateId && stage !== "idle" && (
        <p className="text-xs text-muted-foreground">Candidate ID: {candidateId}</p>
      )}
    </main>
  )
}
