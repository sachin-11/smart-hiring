interface FastApiValidationErrorItem {
  type: string
  loc: (string | number)[]
  msg: string
}

interface ApiErrorLike {
  response?: {
    data?: {
      detail?: string | FastApiValidationErrorItem[]
    }
  }
}

/**
 * FastAPI's `detail` field is a plain string for handler-raised HTTPExceptions,
 * but an *array* of {type, loc, msg, input, ctx} objects for automatic Pydantic
 * validation errors (422s) — rendering that array directly as a React child
 * throws "Objects are not valid as a React child". This normalizes either shape
 * into a single display string.
 */
export function extractErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as ApiErrorLike)?.response?.data?.detail

  if (typeof detail === "string" && detail.trim()) return detail

  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item) => {
        const field = item.loc?.filter((segment) => segment !== "body").join(".")
        return field ? `${field}: ${item.msg}` : item.msg
      })
      .join("; ")
  }

  return fallback
}
