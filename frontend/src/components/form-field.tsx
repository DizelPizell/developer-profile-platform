import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

// A labelled text field with a hint, a character counter and an error line
// (DESIGN.md, cabinet). maxLength mirrors the API limit; the API stays the
// source of truth.
export function FormField({
  id,
  label,
  required = false,
  hint,
  placeholder,
  value,
  maxLength,
  error,
  invalid = false,
  readOnly = false,
  multiline = false,
  onChange,
}: {
  id: string;
  label: string;
  /** Marks the label with "*"; the field itself is not required for saving. */
  required?: boolean;
  hint: string;
  placeholder?: string;
  value: string;
  maxLength: number;
  /** Shown under the field; also marks it invalid. */
  error?: string;
  /** Marks the field invalid without its own message. */
  invalid?: boolean;
  readOnly?: boolean;
  multiline?: boolean;
  onChange: (value: string) => void;
}) {
  const hintId = `${id}-hint`;
  const countId = `${id}-count`;
  const errorId = `${id}-error`;
  const control = {
    id,
    value,
    maxLength,
    placeholder,
    readOnly,
    "aria-invalid": invalid || error !== undefined ? true : undefined,
    "aria-describedby": [hintId, countId, error !== undefined ? errorId : null]
      .filter(Boolean)
      .join(" "),
  };

  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id} className="uppercase">
        {label}
        {required && <span aria-hidden="true">*</span>}
      </Label>
      {multiline ? (
        <Textarea {...control} rows={6} onChange={(event) => onChange(event.target.value)} />
      ) : (
        <Input {...control} type="text" onChange={(event) => onChange(event.target.value)} />
      )}
      <div className="flex justify-between gap-4 text-sm text-text-muted">
        <p id={hintId}>{hint}</p>
        <p id={countId} className="shrink-0 tabular-nums">
          {value.length} / {maxLength}
        </p>
      </div>
      {error !== undefined && (
        <p id={errorId} className="text-sm text-error">
          {error}
        </p>
      )}
    </div>
  );
}
