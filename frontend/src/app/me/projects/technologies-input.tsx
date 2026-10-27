"use client";

import { useState, type KeyboardEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TECHNOLOGIES_MAX, TECHNOLOGY_MAX_LENGTH } from "@/lib/api";

/** The API's normalization: trim, inner whitespace runs become one space (ADR-015). */
function normalize(name: string): string {
  return name.trim().replace(/\s+/g, " ");
}

// Technologies as chips (project-form.png): added with Enter or «Добавить»,
// removed with ×, kept in the entered order. Blank names and names equal
// ignoring case are rejected here; the API stays the source of truth.
export function TechnologiesInput({
  id,
  label,
  hint,
  placeholder,
  values,
  error,
  readOnly,
  onChange,
}: {
  id: string;
  label: string;
  hint: string;
  placeholder: string;
  values: string[];
  /** Shown under the field; also marks it invalid. */
  error?: string;
  readOnly: boolean;
  onChange: (values: string[]) => void;
}) {
  const [draft, setDraft] = useState("");
  const [rejected, setRejected] = useState<string | null>(null);
  const full = values.length >= TECHNOLOGIES_MAX;
  const hintId = `${id}-hint`;
  const countId = `${id}-count`;
  const errorId = `${id}-error`;
  const message = error ?? rejected ?? (full ? `Не больше ${TECHNOLOGIES_MAX} технологий.` : null);

  function add() {
    if (readOnly || full) {
      return;
    }
    const name = normalize(draft);
    if (!name) {
      setDraft("");
      return;
    }
    if (values.some((value) => value.toLowerCase() === name.toLowerCase())) {
      setRejected(`«${name}» уже есть в списке.`);
      return;
    }
    onChange([...values, name]);
    setDraft("");
    setRejected(null);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter" && !event.nativeEvent.isComposing) {
      // Adds a chip instead of submitting the form.
      event.preventDefault();
      add();
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id} className="uppercase">
        {label}
        <span aria-hidden="true">*</span>
      </Label>
      <div className="flex gap-3">
        <Input
          id={id}
          type="text"
          value={draft}
          maxLength={TECHNOLOGY_MAX_LENGTH}
          placeholder={placeholder}
          readOnly={readOnly || full}
          aria-invalid={error !== undefined ? true : undefined}
          aria-describedby={[hintId, countId, message !== null ? errorId : null]
            .filter(Boolean)
            .join(" ")}
          onChange={(event) => {
            setDraft(event.target.value);
            setRejected(null);
          }}
          onKeyDown={handleKeyDown}
        />
        <Button type="button" disabled={readOnly || full} onClick={add}>
          Добавить
        </Button>
      </div>
      {values.length > 0 && (
        <ul aria-label="Добавленные технологии" className="flex flex-wrap gap-2">
          {values.map((name, index) => (
            <li
              key={name}
              className="flex items-center gap-2 border-2 border-outline bg-bg py-1 pr-1 pl-2"
            >
              <span className="break-all">{name}</span>
              <button
                type="button"
                aria-label={`Удалить «${name}»`}
                disabled={readOnly}
                onClick={() => onChange(values.filter((_, i) => i !== index))}
                className="flex size-6 items-center justify-center bg-frame text-sm text-text disabled:opacity-50"
              >
                <span aria-hidden="true">×</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex justify-between gap-4 text-sm text-text-muted">
        <p id={hintId}>{hint}</p>
        <p id={countId} className="shrink-0 tabular-nums">
          {values.length} / {TECHNOLOGIES_MAX}
        </p>
      </div>
      {message !== null && (
        <p id={errorId} className={error !== undefined || rejected ? "text-sm text-error" : "text-sm text-text-muted"}>
          {message}
        </p>
      )}
    </div>
  );
}
