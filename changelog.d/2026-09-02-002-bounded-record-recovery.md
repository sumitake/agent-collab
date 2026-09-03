- Preserve valid bounded runtime records across malformed UTF-8, missing final
  newline, and unrelated stderr overflow, while excluding stdout records whose
  delimiter falls beyond the response byte cap.
