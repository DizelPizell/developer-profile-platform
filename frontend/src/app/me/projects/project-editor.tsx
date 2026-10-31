"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { FormField } from "@/components/form-field";
import { RequestErrorAlert } from "@/components/request-error";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  archiveProject,
  createProject,
  getProject,
  missingProjectFields,
  PROJECT_FIELD_MAX_LENGTH,
  PROJECT_TEXT_FIELDS,
  projectFieldErrors,
  publishProject,
  TECHNOLOGIES_MAX,
  TECHNOLOGY_MAX_LENGTH,
  updateProject,
  type ProjectField,
  type ProjectFieldError,
  type ProjectResponse,
  type ProjectTextField,
  type ProjectWrite,
} from "@/lib/api";

import {
  PROJECT_FIELD_TEXT,
  projectActionError,
  ProjectStateBadge,
  UNTITLED,
} from "./project-texts";
import { RepositoryBlock } from "./repository-block";
import { TechnologiesInput } from "./technologies-input";

type Values = Record<ProjectTextField, string> & { technologies: string[] };
type Action = "save" | "publish" | "archive";

function toValues(project: ProjectResponse | null): Values {
  const values = Object.fromEntries(
    PROJECT_TEXT_FIELDS.map((field) => [field, project?.[field] ?? ""]),
  ) as Record<ProjectTextField, string>;
  return { ...values, technologies: project?.technologies ?? [] };
}

/**
 * Only the fields that differ from the stored project; an emptied text field
 * is cleared with null, technologies go as the whole list in the entered order.
 */
function changedFields(values: Values, saved: ProjectResponse | null): ProjectWrite {
  const stored = toValues(saved);
  const update: ProjectWrite = {};
  for (const field of PROJECT_TEXT_FIELDS) {
    if (values[field] !== stored[field]) {
      update[field] = values[field] === "" ? null : values[field];
    }
  }
  const sameTechnologies =
    values.technologies.length === stored.technologies.length &&
    values.technologies.every((name, i) => name === stored.technologies[i]);
  if (!sameTechnologies) {
    update.technologies = values.technologies;
  }
  return update;
}

function fieldErrorMessage(field: ProjectField, { type, item }: ProjectFieldError): string {
  if (field === "technologies") {
    if (item) {
      return type === "string_too_long"
        ? `Не больше ${TECHNOLOGY_MAX_LENGTH} символов в названии технологии.`
        : "Некорректное название технологии.";
    }
    if (type === "duplicate_technology") {
      return "Технологии не должны повторяться, даже с другим регистром букв.";
    }
    return type === "too_long" ? `Не больше ${TECHNOLOGIES_MAX} технологий.` : "Некорректное значение.";
  }
  if (type === "string_too_long") {
    return `Не больше ${PROJECT_FIELD_MAX_LENGTH[field]} символов.`;
  }
  if (type === "control_characters") {
    return "Недопустимые символы.";
  }
  return "Некорректное значение.";
}

/** «Роль», «Ваш вклад», «Технологии» (project-form.png). */
function fieldList(fields: ProjectField[]): string {
  return fields.map((field) => `«${PROJECT_FIELD_TEXT[field].label}»`).join(", ");
}

export function ProjectEditor({
  initialProject,
  imported = false,
  onNotFound,
}: {
  /** null on /me/projects/new. */
  initialProject: ProjectResponse | null;
  /** Shows «Проект создан» until the next save (DESIGN.md, import). */
  imported?: boolean;
  onNotFound: () => void;
}) {
  const router = useRouter();
  const [saved, setSaved] = useState(initialProject);
  const [values, setValues] = useState(() => toValues(initialProject));
  const [pending, setPending] = useState<Action | null>(null);
  // A link or unlink in the repository block; it disables the form's buttons too.
  const [githubPending, setGithubPending] = useState(false);
  // Blocks a second request before the disabled state reaches the DOM.
  const inFlight = useRef(false);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<ProjectField, string>>>({});
  const [incomplete, setIncomplete] = useState<{ action: Action; fields: ProjectField[] } | null>(
    null,
  );
  const [message, setMessage] = useState<string | null>(null);
  const [requestError, setRequestError] = useState<unknown>(null);
  const [savedNotice, setSavedNotice] = useState(false);
  // Fixed at the first render: the values come from the project as imported.
  const [importNotice, setImportNotice] = useState(() =>
    imported && initialProject?.github ? importNoticeText(initialProject) : null,
  );
  // The buttons are at the bottom of a long form and the error block at the top.
  const alerts = useRef<HTMLDivElement>(null);
  const hasAlert = incomplete !== null || message !== null || requestError !== null;

  useEffect(() => {
    if (hasAlert) {
      alerts.current?.scrollIntoView?.({ block: "nearest" });
    }
  }, [hasAlert, incomplete, message, requestError]);

  const update = changedFields(values, saved);
  const dirty = Object.keys(update).length > 0;
  const busy = pending !== null || githubPending;
  const status = saved?.status ?? null;
  const canPublish = saved !== null && status !== "PUBLISHED" && !dirty;
  const canArchive = status === "PUBLISHED";

  async function run(action: Action, call: () => Promise<"stay" | "leave">) {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setPending(action);
    setFieldErrors({});
    setIncomplete(null);
    setMessage(null);
    setRequestError(null);
    setSavedNotice(false);
    let leaving = false;
    try {
      leaving = (await call()) === "leave";
    } catch (error) {
      leaving = await handleError(action, error);
    } finally {
      if (!leaving) {
        inFlight.current = false;
        setPending(null);
      }
    }
  }

  /** Shows the error; true when the screen is being left. */
  async function handleError(action: Action, error: unknown): Promise<boolean> {
    if (error instanceof ApiError && error.status === 401) {
      router.replace("/login");
      return true;
    }
    if (error instanceof ApiError && error.code === "NOT_FOUND") {
      onNotFound();
      return true;
    }
    const missing = missingProjectFields(error);
    const perField = Object.entries(projectFieldErrors(error)) as [
      ProjectField,
      ProjectFieldError,
    ][];
    const known = projectActionError(error);
    if (missing.length > 0) {
      setIncomplete({ action, fields: missing });
    } else if (perField.length > 0) {
      setFieldErrors(
        Object.fromEntries(perField.map(([field, entry]) => [field, fieldErrorMessage(field, entry)])),
      );
    } else if (known) {
      setMessage(known.text);
      if (known.reload && saved) {
        // The stored state changed elsewhere; edits in the form stay.
        try {
          setSaved(await getProject(saved.id));
        } catch (reloadError) {
          return handleError(action, reloadError);
        }
      }
    } else {
      setRequestError(error);
    }
    return false;
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!dirty) {
      return;
    }
    void run("save", async () => {
      if (saved === null) {
        const created = await createProject(update);
        // The edit screen of the created project takes over; the button stays disabled.
        router.replace(`/me/projects/${encodeURIComponent(created.id)}`);
        return "leave";
      }
      const project = await updateProject(saved.id, update);
      setSaved(project);
      // The server normalizes values (trim, blank → null, stored spelling); show them.
      setValues(toValues(project));
      setSavedNotice(true);
      setImportNotice(null);
      return "stay";
    });
  }

  function publish() {
    if (saved === null) {
      return;
    }
    void run("publish", async () => {
      const project = await publishProject(saved.id);
      setSaved(project);
      setValues(toValues(project));
      return "stay";
    });
  }

  function archive() {
    if (saved === null) {
      return;
    }
    // Archive does not use the form, so unsaved edits stay in it.
    void run("archive", async () => {
      setSaved(await archiveProject(saved.id));
      return "stay";
    });
  }

  function change(next: Partial<Values>) {
    setValues((current) => ({ ...current, ...next }));
    setSavedNotice(false);
  }

  function missingError(field: ProjectField): string | undefined {
    if (!incomplete?.fields.includes(field)) {
      return undefined;
    }
    return field === "technologies" ? "Нужна хотя бы одна" : "Заполните это поле";
  }

  function field(name: ProjectTextField, multiline = false) {
    const text = PROJECT_FIELD_TEXT[name];
    return (
      <FormField
        id={`project-${name}`}
        label={text.label}
        required={text.required}
        hint={text.hint}
        placeholder={text.placeholder}
        value={values[name]}
        maxLength={PROJECT_FIELD_MAX_LENGTH[name]}
        error={fieldErrors[name] ?? missingError(name)}
        readOnly={busy}
        multiline={multiline}
        onChange={(value) => change({ [name]: value })}
      />
    );
  }

  const technologyText = PROJECT_FIELD_TEXT.technologies;

  return (
    <>
      <section className="flex flex-col gap-4 bg-panel px-6 py-6 shadow-panel sm:flex-row sm:items-center sm:justify-between sm:px-8">
        <h1 className="font-heading text-lg leading-relaxed uppercase">
          {saved ? "Проект" : "Новый проект"}
        </h1>
        <div className="flex flex-wrap items-center gap-4">
          {saved && <ProjectStateBadge status={saved.status} visibility={saved.visibility} />}
          <p className="text-sm text-text-muted">Публичная страница проекта появится позже</p>
        </div>
      </section>

      {importNotice !== null && (
        <div role="status" className="flex flex-col gap-3 border-4 border-success bg-bg px-4 py-4">
          <p className="font-heading text-xs leading-normal text-success uppercase">
            Проект создан
          </p>
          <p className="break-words">{importNotice}</p>
        </div>
      )}

      {hasAlert && (
        <div ref={alerts} className="flex flex-col gap-4">
          {incomplete && <IncompleteAlert action={incomplete.action} fields={incomplete.fields} />}
          {message !== null && <Alert>{message}</Alert>}
          {requestError !== null && <RequestErrorAlert error={requestError} />}
        </div>
      )}

      <form
        noValidate
        aria-label="Проект"
        onSubmit={handleSubmit}
        className="flex flex-col gap-6 bg-panel px-6 py-8 shadow-panel sm:px-8"
      >
        {field("title")}
        {field("summary")}
        <div className="grid gap-6 sm:grid-cols-2">
          {field("role")}
          <TechnologiesInput
            id="project-technologies"
            label={technologyText.label}
            hint={technologyText.hint}
            placeholder={technologyText.placeholder}
            values={values.technologies}
            error={fieldErrors.technologies ?? missingError("technologies")}
            readOnly={busy}
            onChange={(technologies) => change({ technologies })}
          />
        </div>
        {field("contribution", true)}
        {field("description", true)}
        <div className="grid gap-6 sm:grid-cols-2">
          {field("problem", true)}
          {field("results", true)}
        </div>

        <RepositoryBlock
          project={saved}
          busy={pending !== null}
          onPendingChange={setGithubPending}
          // Only github is taken from the answer: unsaved edits and «Сохранить» stay as they are.
          onGitHub={(github) => setSaved((current) => current && { ...current, github })}
          onNotFound={onNotFound}
        />

        <div className="flex flex-col gap-4 border-t-4 border-outline pt-6">
          <p className="text-text-muted">Демо и скриншоты добавим в следующих версиях.</p>
          <div className="flex flex-wrap items-center gap-4">
            <Button type="submit" size="lg" disabled={!dirty || busy}>
              Сохранить
            </Button>
            <Button
              type="button"
              variant="label"
              size="lg"
              disabled={!canPublish || busy}
              onClick={publish}
            >
              Опубликовать
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="lg"
              disabled={!canArchive || busy}
              onClick={archive}
            >
              В архив
            </Button>
            <p role="status" className="text-lg text-success">
              {savedNotice ? "Сохранено" : ""}
            </p>
          </div>
          {status !== "PUBLISHED" && dirty && (
            <p className="text-sm text-text-muted">
              Сохраните изменения, чтобы опубликовать проект.
            </p>
          )}
          {canArchive ? (
            saved?.featured_position != null && (
              <p className="text-sm text-text-muted">«В архив» уберёт проект из главных.</p>
            )
          ) : (
            <p className="text-sm text-text-muted">«В архив» доступно у опубликованного проекта</p>
          )}
        </div>
      </form>
    </>
  );
}

/** The «Проект создан» text; the values come from the project response. */
function importNoticeText(project: ProjectResponse): string {
  return (
    `Из репозитория ${project.github?.full_name} создан черновик «${project.title ?? UNTITLED}». ` +
    "Заполните «Коротко о проекте», «Роль», «Ваш вклад» и «Технологии», чтобы опубликовать его."
  );
}

function IncompleteAlert({ action, fields }: { action: Action; fields: ProjectField[] }) {
  return (
    <Alert className="flex gap-4">
      <span
        aria-hidden="true"
        className="flex size-8 shrink-0 items-center justify-center bg-error font-heading text-sm text-outline"
      >
        !
      </span>
      <div className="flex flex-col gap-2">
        <p className="font-heading text-xs leading-normal uppercase">
          {action === "save" ? "Нельзя сохранить" : "Нельзя опубликовать"}
        </p>
        <p className="text-text">
          {fields.length > 1 ? "Заполните обязательные поля: " : "Заполните обязательное поле: "}
          {fieldList(fields)}.
          {action === "save" && " Опубликованный проект должен оставаться заполненным."}
        </p>
      </div>
    </Alert>
  );
}
