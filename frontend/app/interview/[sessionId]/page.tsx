"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useParams } from "next/navigation"
import { Clock, Keyboard, Mic } from "lucide-react"

import AIAvatar from "@/components/AIAvatar"
import DashboardShell from "@/components/layout/DashboardShell"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { LoadingState } from "@/components/ui/spinner"
import { Textarea } from "@/components/ui/textarea"
import VoiceRecorder from "@/components/VoiceRecorder"
import { api } from "@/lib/api"
import { extractErrorMessage } from "@/lib/errors"
import type {
  InterviewAnswerResponse,
  InterviewTranscriptResponse,
  InterviewWsServerMessage,
  QAExchange,
  QuestionCategory,
} from "@/types/interview"

type AnswerMode = "text" | "voice"

interface CurrentQuestion {
  question: string
  category: QuestionCategory
  isFollowUp: boolean
}

function scoreColor(score: number | null): string {
  if (score === null) return "text-muted-foreground"
  if (score >= 4) return "text-emerald-600 dark:text-emerald-400"
  if (score === 3) return "text-amber-600 dark:text-amber-400"
  return "text-red-600 dark:text-red-400"
}

function categoryLabel(category: QuestionCategory): string {
  if (category === "intro") return "Introduction"
  return category.charAt(0).toUpperCase() + category.slice(1)
}

export default function InterviewRoomPage() {
  const params = useParams<{ sessionId: string }>()
  const sessionId = params.sessionId

  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [history, setHistory] = useState<QAExchange[]>([])
  const [currentQuestion, setCurrentQuestion] = useState<CurrentQuestion | null>(null)
  const [questionIndex, setQuestionIndex] = useState(0)
  const [totalQuestions, setTotalQuestions] = useState(0)
  const [completed, setCompleted] = useState(false)
  const [averageScore, setAverageScore] = useState<number | null>(null)

  const [mode, setMode] = useState<AnswerMode>("text")
  const [answerText, setAnswerText] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [pendingTranscript, setPendingTranscript] = useState<string | null>(null)

  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [questionStartedAt, setQuestionStartedAt] = useState(0)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)

  const [nudgeVisible, setNudgeVisible] = useState(false)
  const [aiSpeaking, setAiSpeaking] = useState(false)
  const [playbackAnalyser, setPlaybackAnalyser] = useState<AnalyserNode | null>(null)

  const audioRef = useRef<HTMLAudioElement>(null)
  const playbackCtxRef = useRef<AudioContext | null>(null)
  const objectUrlRef = useRef<string | null>(null)
  const currentQuestionRef = useRef<CurrentQuestion | null>(null)
  const lastAnswerTextRef = useRef<string>("")

  // Queue for sentence-chunked TTS audio streamed over the voice WS: chunks
  // arrive one at a time as they're synthesized, and are played back-to-back
  // instead of waiting for the whole response before any audio starts.
  const audioQueueRef = useRef<string[]>([])
  const isPlayingQueueRef = useRef(false)
  const currentChunkUrlRef = useRef<string | null>(null)

  useEffect(() => {
    currentQuestionRef.current = currentQuestion
  }, [currentQuestion])

  // Initial load: the session's live (Redis) or finalized (DB) transcript is the
  // single source of truth, so a page refresh mid-interview resumes correctly.
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const { data } = await api.get<InterviewTranscriptResponse>(`/interview/${sessionId}/transcript`)
        if (cancelled) return

        if (data.status === "completed") {
          setHistory(data.exchanges)
          setCompleted(true)
          setAverageScore(data.average_score)
          setTotalQuestions(data.total_questions)
        } else {
          const pending = data.exchanges[data.exchanges.length - 1]
          const answered = data.exchanges.slice(0, -1)
          setHistory(answered)
          if (pending) {
            setCurrentQuestion({
              question: pending.question,
              category: pending.category,
              isFollowUp: pending.is_follow_up,
            })
          }
          setQuestionIndex(data.question_index)
          setTotalQuestions(data.total_questions)
          setQuestionStartedAt(Date.now())

          // Pick up the first question's audio handed off from the start
          // page (see app/interview/page.tsx) — only relevant the moment
          // after starting; a plain refresh mid-interview has no history yet
          // either at the very first turn, so also gate on the key existing.
          if (answered.length === 0) {
            const key = `interview-first-audio:${sessionId}`
            const pendingAudio = sessionStorage.getItem(key)
            if (pendingAudio) {
              sessionStorage.removeItem(key)
              setAudioUrl(pendingAudio)
            }
          }
        }
      } catch {
        if (!cancelled) setLoadError("Could not load this interview session. It may have expired.")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [sessionId])

  // Per-question timer.
  useEffect(() => {
    setElapsedSeconds(0)
    if (completed || !questionStartedAt) return
    const id = setInterval(() => setElapsedSeconds(Math.floor((Date.now() - questionStartedAt) / 1000)), 1000)
    return () => clearInterval(id)
  }, [questionStartedAt, completed])

  // Autoplay whatever audio (TTS presigned URL or WS-streamed blob) just arrived.
  useEffect(() => {
    if (audioUrl && audioRef.current) {
      audioRef.current.src = audioUrl
      audioRef.current.play().catch(() => {})
    }
  }, [audioUrl])

  // Routes the AI's own audio output through an AnalyserNode so AIAvatar can
  // react to its actual amplitude in real time — the playback counterpart to
  // the mic AnalyserNode VoiceRecorder sets up for the candidate's waveform.
  // createMediaElementSource can only be called once per <audio> element, so
  // this must run exactly once for its lifetime.
  useEffect(() => {
    const audioEl = audioRef.current
    if (!audioEl || playbackCtxRef.current) return

    const ctx = new AudioContext()
    playbackCtxRef.current = ctx
    const source = ctx.createMediaElementSource(audioEl)
    const analyser = ctx.createAnalyser()
    analyser.fftSize = 1024
    source.connect(analyser)
    analyser.connect(ctx.destination)
    setPlaybackAnalyser(analyser)

    return () => {
      ctx.close().catch(() => {})
      playbackCtxRef.current = null
    }
  }, [])

  // Stops whatever's currently playing/queued — used for barge-in (candidate
  // clicks "Start speaking" while the AI is still talking) and cleanup.
  const stopAllAudio = useCallback(() => {
    audioRef.current?.pause()
    audioQueueRef.current.forEach((url) => URL.revokeObjectURL(url))
    audioQueueRef.current = []
    isPlayingQueueRef.current = false
    if (currentChunkUrlRef.current) {
      URL.revokeObjectURL(currentChunkUrlRef.current)
      currentChunkUrlRef.current = null
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current)
      objectUrlRef.current = null
    }
    setAudioUrl(null)
  }, [])

  const playNextQueuedChunk = useCallback(() => {
    if (currentChunkUrlRef.current) {
      URL.revokeObjectURL(currentChunkUrlRef.current)
      currentChunkUrlRef.current = null
    }
    const next = audioQueueRef.current.shift()
    if (!next) {
      isPlayingQueueRef.current = false
      return
    }
    isPlayingQueueRef.current = true
    currentChunkUrlRef.current = next
    if (audioRef.current) {
      audioRef.current.src = next
      audioRef.current.play().catch(() => {})
    }
  }, [])

  const handleAudioChunk = useCallback(
    (buffer: ArrayBuffer) => {
      const url = URL.createObjectURL(new Blob([buffer], { type: "audio/mpeg" }))
      audioQueueRef.current.push(url)
      if (!isPlayingQueueRef.current) playNextQueuedChunk()
    },
    [playNextQueuedChunk]
  )

  const handleNudge = useCallback(() => {
    setNudgeVisible(true)
    setTimeout(() => setNudgeVisible(false), 5000)
  }, [])

  useEffect(() => {
    return () => {
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
      if (currentChunkUrlRef.current) URL.revokeObjectURL(currentChunkUrlRef.current)
      audioQueueRef.current.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [])

  const commitAnswer = useCallback(
    async (
      answer: string,
      result: {
        score: number | null
        feedback: string | null
        is_follow_up: boolean
        complete: boolean
        question: string | null
        category: QuestionCategory | null
        question_index: number
        total_questions: number
      }
    ) => {
      const answeredQuestion = currentQuestionRef.current
      if (answeredQuestion) {
        const exchange: QAExchange = {
          question: answeredQuestion.question,
          category: answeredQuestion.category,
          is_follow_up: answeredQuestion.isFollowUp,
          answer,
          score: result.score,
          feedback: result.feedback,
        }
        setHistory((prev) => [...prev, exchange])
      }
      setTotalQuestions(result.total_questions)
      setPendingTranscript(null)

      if (result.complete) {
        setCurrentQuestion(null)
        try {
          const { data } = await api.get<InterviewTranscriptResponse>(`/interview/${sessionId}/transcript`)
          setAverageScore(data.average_score)
        } finally {
          setCompleted(true)
        }
        return
      }

      setCurrentQuestion({
        question: result.question!,
        category: result.category!,
        isFollowUp: result.is_follow_up,
      })
      setQuestionIndex(result.question_index)
      setQuestionStartedAt(Date.now())
    },
    [sessionId]
  )

  const submitTextAnswer = useCallback(async () => {
    if (!answerText.trim() || submitting) return
    setSubmitting(true)
    setSubmitError(null)
    const answer = answerText.trim()

    const formData = new FormData()
    formData.append("session_id", sessionId)
    formData.append("answer_text", answer)

    try {
      const { data } = await api.post<InterviewAnswerResponse>("/interview/answer", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      setAnswerText("")
      setAudioUrl(data.audio_url)
      await commitAnswer(answer, data)
    } catch (err) {
      setSubmitError(extractErrorMessage(err, "Failed to submit answer."))
    } finally {
      setSubmitting(false)
    }
  }, [answerText, submitting, sessionId, commitAnswer])

  const handleVoiceTranscript = useCallback((text: string) => {
    lastAnswerTextRef.current = text
    setPendingTranscript(text)
  }, [])

  const handleVoiceResult = useCallback(
    (result: Extract<InterviewWsServerMessage, { type: "result" }>) => {
      commitAnswer(lastAnswerTextRef.current, result)
    },
    [commitAnswer]
  )

  const handleVoiceError = useCallback((message: string) => {
    setSubmitError(message)
  }, [])

  if (loading) {
    return (
      <DashboardShell>
        <main className="mx-auto flex max-w-4xl items-center justify-center">
          <LoadingState label="Loading interview session…" />
        </main>
      </DashboardShell>
    )
  }

  if (loadError) {
    return (
      <DashboardShell>
        <main className="mx-auto flex max-w-4xl items-center justify-center">
          <p className="text-destructive">{loadError}</p>
        </main>
      </DashboardShell>
    )
  }

  return (
    <DashboardShell>
    <main className="mx-auto grid max-w-5xl grid-cols-1 gap-6 lg:grid-cols-[1fr_360px]">
      <audio
        ref={audioRef}
        className="hidden"
        onEnded={playNextQueuedChunk}
        onPlay={() => setAiSpeaking(true)}
        onPause={() => setAiSpeaking(false)}
      />

      <div className="flex flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">AI Interview</h1>
          {!completed && totalQuestions > 0 && currentQuestion?.category !== "intro" && (
            <span className="text-sm text-muted-foreground">
              Question {Math.min(questionIndex + 1, totalQuestions)} of {totalQuestions}
            </span>
          )}
          {!completed && currentQuestion?.category === "intro" && (
            <span className="text-sm text-muted-foreground">Getting started…</span>
          )}
        </div>

        {!completed && (
          <div className="flex justify-center py-2">
            <AIAvatar analyser={playbackAnalyser} speaking={aiSpeaking} />
          </div>
        )}

        {completed ? (
          <Card>
            <CardHeader>
              <CardTitle>Interview complete</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <p className="text-sm text-muted-foreground">
                All {totalQuestions} questions answered.
              </p>
              {averageScore !== null && (
                <p>
                  Average score:{" "}
                  <span className={`text-lg font-bold ${scoreColor(Math.round(averageScore))}`}>
                    {averageScore.toFixed(1)} / 5
                  </span>
                </p>
              )}
            </CardContent>
          </Card>
        ) : (
          currentQuestion && (
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between gap-4">
                  <Badge variant="outline">{categoryLabel(currentQuestion.category)}</Badge>
                  <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
                    <Clock className="size-4" />
                    {elapsedSeconds}s
                  </span>
                </div>
                <CardTitle className="text-xl font-normal leading-relaxed">
                  {currentQuestion.question}
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <div className="flex gap-2">
                  <Button
                    variant={mode === "text" ? "default" : "outline"}
                    size="sm"
                    onClick={() => setMode("text")}
                    className="gap-1.5"
                  >
                    <Keyboard className="size-4" /> Text
                  </Button>
                  <Button
                    variant={mode === "voice" ? "default" : "outline"}
                    size="sm"
                    onClick={() => setMode("voice")}
                    className="gap-1.5"
                  >
                    <Mic className="size-4" /> Voice
                  </Button>
                </div>

                {nudgeVisible && (
                  <p className="text-sm text-muted-foreground">Still there? Take your time.</p>
                )}

                {mode === "text" ? (
                  <div className="flex flex-col gap-3">
                    <Textarea
                      value={answerText}
                      onChange={(e) => setAnswerText(e.target.value)}
                      placeholder="Type your answer…"
                      rows={5}
                      disabled={submitting}
                    />
                    <Button
                      onClick={submitTextAnswer}
                      disabled={!answerText.trim() || submitting}
                      className="self-start"
                    >
                      {submitting ? "Submitting…" : "Submit Answer"}
                    </Button>
                  </div>
                ) : (
                  <div className="flex flex-col gap-3">
                    {pendingTranscript && (
                      <p className="rounded-md bg-muted p-3 text-sm italic text-muted-foreground">
                        &ldquo;{pendingTranscript}&rdquo;
                      </p>
                    )}
                    <VoiceRecorder
                      key={questionIndex + (currentQuestion?.question ?? "")}
                      sessionId={sessionId}
                      onTranscript={handleVoiceTranscript}
                      onResult={handleVoiceResult}
                      onAudioChunk={handleAudioChunk}
                      onBeforeRecording={stopAllAudio}
                      onNudge={handleNudge}
                      onError={handleVoiceError}
                    />
                  </div>
                )}

                {submitError && <p className="text-sm text-destructive">{submitError}</p>}
              </CardContent>
            </Card>
          )
        )}
      </div>

      <div className="flex flex-col gap-3">
        <h2 className="font-semibold">Transcript</h2>
        <div className="flex flex-col gap-3 overflow-y-auto">
          {history.length === 0 && (
            <p className="text-sm text-muted-foreground">Your answers will appear here as you go.</p>
          )}
          {history.map((ex, i) => (
            <Card key={i} className="text-sm">
              <CardContent className="flex flex-col gap-1.5 p-4">
                <div className="flex items-center justify-between gap-2">
                  <Badge variant="outline" className="text-xs">
                    {categoryLabel(ex.category)}
                    {ex.is_follow_up ? " · follow-up" : ""}
                  </Badge>
                  {ex.score !== null && (
                    <span className={`font-semibold ${scoreColor(ex.score)}`}>{ex.score}/5</span>
                  )}
                </div>
                <p className="font-medium">{ex.question}</p>
                {ex.answer && <p className="text-muted-foreground">{ex.answer}</p>}
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </main>
    </DashboardShell>
  )
}
