"use client"

import { useState, type KeyboardEvent } from "react"

import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"

interface SkillTagInputProps {
  value: string[]
  onChange: (skills: string[]) => void
  placeholder?: string
}

export default function SkillTagInput({ value, onChange, placeholder }: SkillTagInputProps) {
  const [draft, setDraft] = useState("")

  const addSkill = () => {
    const skill = draft.trim()
    if (skill && !value.some((s) => s.toLowerCase() === skill.toLowerCase())) {
      onChange([...value, skill])
    }
    setDraft("")
  }

  const removeSkill = (skill: string) => {
    onChange(value.filter((s) => s !== skill))
  }

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault()
      addSkill()
    } else if (e.key === "Backspace" && draft === "" && value.length > 0) {
      removeSkill(value[value.length - 1])
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={addSkill}
        placeholder={placeholder ?? "Type a skill and press Enter"}
      />
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {value.map((skill) => (
            <Badge key={skill} variant="secondary" className="gap-1">
              {skill}
              <button
                type="button"
                onClick={() => removeSkill(skill)}
                aria-label={`Remove ${skill}`}
                className="ml-0.5 text-muted-foreground hover:text-foreground"
              >
                ×
              </button>
            </Badge>
          ))}
        </div>
      )}
    </div>
  )
}
