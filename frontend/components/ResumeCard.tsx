import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import type { ResumeDetailResponse } from "@/types/resume"

function formatRange(start: string | null, end: string | null, isCurrent: boolean): string {
  const startLabel = start ?? "?"
  const endLabel = isCurrent ? "Present" : (end ?? "?")
  return `${startLabel} — ${endLabel}`
}

export default function ResumeCard({ resume }: { resume: ResumeDetailResponse }) {
  return (
    <Card className="w-full max-w-xl">
      <CardHeader>
        <CardTitle>{resume.full_name ?? "Unknown candidate"}</CardTitle>
        <CardDescription>
          {[resume.email, resume.phone].filter(Boolean).join(" · ") || "No contact info extracted"}
          {resume.total_years_exp != null && (
            <span className="ml-2">· {resume.total_years_exp} yrs experience</span>
          )}
        </CardDescription>
      </CardHeader>

      <CardContent className="flex flex-col gap-5">
        {resume.skills && resume.skills.length > 0 && (
          <div>
            <h3 className="mb-2 text-sm font-medium text-muted-foreground">Skills</h3>
            <div className="flex flex-wrap gap-1.5">
              {resume.skills.map((skill) => (
                <Badge key={skill} variant="secondary">
                  {skill}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {resume.experience && resume.experience.length > 0 && (
          <div>
            <h3 className="mb-2 text-sm font-medium text-muted-foreground">Experience</h3>
            <ol className="flex flex-col gap-3 border-l pl-4">
              {resume.experience.map((exp, i) => (
                <li key={i}>
                  <p className="text-sm font-medium">
                    {exp.title} · {exp.company}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatRange(exp.start_date, exp.end_date, exp.is_current)}
                  </p>
                  {exp.description && <p className="mt-1 text-sm">{exp.description}</p>}
                </li>
              ))}
            </ol>
          </div>
        )}

        {resume.education && resume.education.length > 0 && (
          <div>
            <h3 className="mb-2 text-sm font-medium text-muted-foreground">Education</h3>
            <ul className="flex flex-col gap-1.5">
              {resume.education.map((edu, i) => (
                <li key={i} className="text-sm">
                  <span className="font-medium">{edu.institution}</span>
                  {edu.degree && <> · {edu.degree}</>}
                  {edu.field_of_study && <> in {edu.field_of_study}</>}
                  {(edu.start_year || edu.end_year) && (
                    <span className="text-muted-foreground">
                      {" "}
                      ({edu.start_year ?? "?"}–{edu.end_year ?? "?"})
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>

      <CardFooter>
        <Button disabled title="Coming in a future module">
          View Match Score
        </Button>
      </CardFooter>
    </Card>
  )
}
