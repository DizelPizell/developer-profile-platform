"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ChangeEvent, type KeyboardEvent } from "react";

import { RequestErrorAlert } from "@/components/request-error";
import { Alert } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  ApiError,
  deleteScreenshot,
  getProject,
  mediaUrl,
  reorderScreenshots,
  SCREENSHOT_CAPTION_MAX_LENGTH,
  SCREENSHOT_MAX_BYTES,
  SCREENSHOT_TYPES,
  SCREENSHOTS_MAX,
  updateScreenshotCaption,
  uploadScreenshot,
  type ProjectResponse,
  type Screenshot,
} from "@/lib/api";

import { BADGE } from "./project-texts";

// Texts: DESIGN.md, "«Демо и скриншоты» in the project form"; mockup project-media.png.
const TOO_LARGE = "Файл больше 5 МБ.";
const WRONG_TYPE = "Подходят JPEG, PNG и WebP.";
const LIMIT_TEXT = `Можно добавить не больше ${SCREENSHOTS_MAX} скриншотов.`;
const NOT_FOUND_TEXT = "Скриншот не найден. Список загружен заново.";

const FILE_ERRORS: Record<string, string> = {
  invalid_image: "Не получилось прочитать картинку. Подходят JPEG, PNG и WebP.",
  image_too_large: TOO_LARGE,
  too_many_pixels: "Слишком большое изображение: не больше 40 мегапикселей.",
};
const CAPTION_ERRORS: Record<string, string> = {
  string_too_long: `Не больше ${SCREENSHOT_CAPTION_MAX_LENGTH} символов.`,
  control_characters: "Недопустимые символы.",
};

/**
 * The text of a screenshot error; reload: the stored list changed and is read
 * again. null for errors shown as the generic cabinet error.
 */
export function screenshotErrorText(error: unknown): { text: string; reload: boolean } | null {
  if (!(error instanceof ApiError)) {
    return null;
  }
  // Nginx answers 413 with HTML before the API sees the request (ADR-0022).
  if (error.status === 413) {
    return { text: TOO_LARGE, reload: false };
  }
  if (error.code === "SCREENSHOT_LIMIT_REACHED") {
    return { text: `${LIMIT_TEXT} Список загружен заново.`, reload: true };
  }
  if (error.code === "SCREENSHOT_ORDER_MISMATCH") {
    return { text: "Список скриншотов изменился, порядок загружен заново.", reload: true };
  }
  if (error.code !== "VALIDATION_ERROR" || !Array.isArray(error.details.fields)) {
    return null;
  }
  for (const entry of error.details.fields as { loc?: unknown; type?: unknown }[]) {
    const field = Array.isArray(entry?.loc) && entry.loc[0] === "body" ? entry.loc[1] : null;
    if (typeof entry?.type !== "string") {
      continue;
    }
    if (field === "file" && entry.type in FILE_ERRORS) {
      return { text: FILE_ERRORS[entry.type], reload: false };
    }
    if (field === "caption") {
      return { text: CAPTION_ERRORS[entry.type] ?? "Некорректное значение.", reload: false };
    }
  }
  return null;
}

function without(drafts: Record<string, string>, id: string): Record<string, string> {
  const rest = { ...drafts };
  delete rest[id];
  return rest;
}

/** "upload" is the block itself; anything else is the id of a row. */
type Failure = { place: string; text?: string; error?: unknown; fileName?: string };
type Control = "caption" | "up" | "down" | "delete" | "upload";
type Focus = { control: Control; id?: string };

export function ScreenshotsBlock({
  project,
  demoSaved,
  busy,
  onPendingChange,
  onScreenshots,
  onNotFound,
}: {
  /** null on /me/projects/new. */
  project: ProjectResponse | null;
  /** The first screenshot is the demo preview while a demo link is stored. */
  demoSaved: boolean;
  /** Another request of the form runs. */
  busy: boolean;
  onPendingChange: (pending: boolean) => void;
  /** Every call answers with the whole list; the form takes only it. */
  onScreenshots: (screenshots: Screenshot[]) => void;
  onNotFound: () => void;
}) {
  const router = useRouter();
  const [pending, setPending] = useState<"upload" | "other" | null>(null);
  const inFlight = useRef(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [notice, setNotice] = useState("");
  // Unsaved captions by screenshot id, so they survive a reorder.
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [deleting, setDeleting] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const block = useRef<HTMLDivElement>(null);
  const focusNext = useRef<Focus | null>(null);

  useEffect(() => {
    const target = focusNext.current;
    if (target === null || pending !== null) {
      return;
    }
    focusNext.current = null;
    const key = target.id ? `${target.control}-${target.id}` : target.control;
    block.current?.querySelector<HTMLElement>(`[data-focus="${key}"]`)?.focus();
  });

  if (project === null) {
    return <p className="text-text-muted">Скриншоты можно добавить после первого сохранения.</p>;
  }

  const { id: projectId, screenshots } = project;
  const disabled = busy || pending !== null;
  const full = screenshots.length >= SCREENSHOTS_MAX;

  async function reload(place: string) {
    try {
      onScreenshots((await getProject(projectId)).screenshots);
      return true;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        router.replace("/login");
      } else if (error instanceof ApiError && error.code === "NOT_FOUND") {
        onNotFound();
      } else {
        setFailure({ place, error });
      }
      return false;
    }
  }

  async function fail(place: string, error: unknown, fileName?: string) {
    if (error instanceof ApiError && error.status === 401) {
      router.replace("/login");
      return;
    }
    // One 404 for a missing screenshot and a missing project: the project decides.
    if (error instanceof ApiError && error.code === "NOT_FOUND") {
      if (await reload("upload")) {
        setFailure({ place: "upload", text: NOT_FOUND_TEXT });
      }
      return;
    }
    const known = screenshotErrorText(error);
    if (known === null) {
      setFailure({ place, error, fileName });
      return;
    }
    const where = known.reload ? "upload" : place;
    if (!known.reload || (await reload(where))) {
      setFailure({ place: where, text: known.text, fileName });
    }
  }

  async function run(
    kind: "upload" | "other",
    place: string,
    call: () => Promise<Screenshot[]>,
    after: (list: Screenshot[]) => { notice: string; focus: Focus },
    fileName?: string,
  ) {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setPending(kind);
    onPendingChange(true);
    setFailure(null);
    setNotice(kind === "upload" ? "Загружаем скриншот…" : "");
    try {
      const list = await call();
      onScreenshots(list);
      const next = after(list);
      setNotice(next.notice);
      focusNext.current = next.focus;
    } catch (error) {
      setNotice("");
      await fail(place, error, fileName);
    } finally {
      inFlight.current = false;
      setPending(null);
      onPendingChange(false);
    }
  }

  function pickFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // The same file can be picked again after an error.
    event.target.value = "";
    if (!file || disabled) {
      return;
    }
    setNotice("");
    if (file.size > SCREENSHOT_MAX_BYTES) {
      setFailure({ place: "upload", text: TOO_LARGE, fileName: file.name });
      return;
    }
    // An empty type (unknown to the browser) goes to the server, which reads the content.
    if (file.type !== "" && !SCREENSHOT_TYPES.includes(file.type)) {
      setFailure({ place: "upload", text: WRONG_TYPE, fileName: file.name });
      return;
    }
    void run(
      "upload",
      "upload",
      () => uploadScreenshot(projectId, file),
      (list) => ({ notice: "Скриншот добавлен.", focus: { control: "caption", id: list.at(-1)?.id } }),
      file.name,
    );
  }

  function captionOf(shot: Screenshot) {
    return drafts[shot.id] ?? shot.caption ?? "";
  }

  function saveCaption(shot: Screenshot) {
    const value = captionOf(shot);
    if (disabled || value === (shot.caption ?? "")) {
      return;
    }
    void run(
      "other",
      shot.id,
      () => updateScreenshotCaption(projectId, shot.id, value === "" ? null : value),
      () => {
        setDrafts((current) => without(current, shot.id));
        return { notice: "Подпись сохранена.", focus: { control: "caption", id: shot.id } };
      },
    );
  }

  function move(index: number, step: -1 | 1) {
    const ids = screenshots.map((shot) => shot.id);
    const target = index + step;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    const id = ids[target];
    // The pressed arrow keeps the focus unless it became disabled at an edge.
    const atEdge = step < 0 ? target === 0 : target === ids.length - 1;
    const arrow: Control = (step < 0) !== atEdge ? "up" : "down";
    void run(
      "other",
      id,
      () => reorderScreenshots(projectId, ids),
      () => ({ notice: "Порядок изменён.", focus: { control: arrow, id } }),
    );
  }

  function remove(id: string) {
    const index = screenshots.findIndex((shot) => shot.id === id);
    void run(
      "other",
      id,
      () => deleteScreenshot(projectId, id),
      (list) => {
        setDrafts((current) => without(current, id));
        const next = list[index];
        return {
          notice: "Скриншот удалён.",
          focus: next ? { control: "delete", id: next.id } : { control: "upload" },
        };
      },
    );
  }

  function failureFor(place: string) {
    if (failure?.place !== place) {
      return null;
    }
    if (failure.text === undefined) {
      return <RequestErrorAlert error={failure.error} />;
    }
    return (
      <Alert>
        <p>{failure.text}</p>
        {failure.fileName && (
          <p className="mt-1 text-sm break-all text-text-muted">{failure.fileName}</p>
        )}
      </Alert>
    );
  }

  return (
    <div ref={block} className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="caps-label">Скриншоты</h3>
        <p className="text-sm text-text-muted">
          Скриншотов: {screenshots.length} из {SCREENSHOTS_MAX}
        </p>
      </div>
      <p className="text-sm text-text-muted">
        Скриншоты сохраняются сразу и не зависят от кнопки «Сохранить». Файл открывается по прямой
        ссылке у любого, кто её знает, даже пока проект — черновик.
      </p>

      {screenshots.length === 0 ? (
        <p className="border-2 border-dashed border-frame px-4 py-6 text-center text-text-muted">
          [Пока нет скриншотов]
        </p>
      ) : (
        <ol aria-label="Скриншоты проекта" className="flex flex-col gap-3">
          {screenshots.map((shot, index) => {
            const n = index + 1;
            const src = mediaUrl(shot.url);
            const caption = captionOf(shot);
            const inputId = `screenshot-${shot.id}-caption`;
            return (
              <li
                key={shot.id}
                className="grid gap-4 border-2 border-outline bg-bg p-3 sm:grid-cols-[2.5rem_10rem_1fr_auto] sm:items-start"
              >
                <span
                  aria-hidden="true"
                  className="flex size-10 items-center justify-center border-2 border-outline bg-label font-bold text-outline"
                >
                  {n}
                </span>
                <div className="flex flex-col gap-2">
                  {src === null ? (
                    <div className="aspect-video w-40 border-2 border-outline bg-panel" />
                  ) : (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={src}
                      alt={shot.caption ?? `Скриншот ${n}`}
                      width={shot.width}
                      height={shot.height}
                      className="h-auto w-40 border-2 border-outline object-contain"
                    />
                  )}
                  {index === 0 && demoSaved && (
                    <span className={`${BADGE} self-start bg-label text-sm text-outline`}>
                      Превью демо
                    </span>
                  )}
                </div>
                <div className="flex min-w-0 flex-col gap-2">
                  <Label htmlFor={inputId} className="uppercase">
                    Подпись <span className="sr-only">к скриншоту {n}</span>
                  </Label>
                  <Input
                    id={inputId}
                    data-focus={`caption-${shot.id}`}
                    value={caption}
                    maxLength={SCREENSHOT_CAPTION_MAX_LENGTH}
                    placeholder="Что на скриншоте"
                    readOnly={disabled}
                    aria-describedby={`${inputId}-hint`}
                    onChange={(event) => {
                      const value = event.target.value;
                      setDrafts((current) => ({ ...current, [shot.id]: value }));
                    }}
                    onKeyDown={(event: KeyboardEvent<HTMLInputElement>) => {
                      if (event.key === "Enter") {
                        // Enter saves the caption, not the project form.
                        event.preventDefault();
                        saveCaption(shot);
                      }
                    }}
                  />
                  <div
                    id={`${inputId}-hint`}
                    className="flex justify-between gap-4 text-sm text-text-muted"
                  >
                    <span>Для тех, кто не видит картинку. До 200 символов</span>
                    <span>
                      {caption.length} / {SCREENSHOT_CAPTION_MAX_LENGTH}
                    </span>
                  </div>
                  <Button
                    type="button"
                    variant="secondary"
                    className="self-start"
                    disabled={disabled || caption === (shot.caption ?? "")}
                    onClick={() => saveCaption(shot)}
                  >
                    Сохранить подпись
                  </Button>
                  {failureFor(shot.id)}
                </div>
                <div className="flex gap-2 sm:flex-col sm:items-stretch">
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="secondary"
                      size="icon"
                      data-focus={`up-${shot.id}`}
                      aria-label={`Выше: скриншот ${n}`}
                      disabled={disabled || index === 0}
                      onClick={() => move(index, -1)}
                    >
                      <span aria-hidden="true">▲</span>
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      size="icon"
                      data-focus={`down-${shot.id}`}
                      aria-label={`Ниже: скриншот ${n}`}
                      disabled={disabled || index === screenshots.length - 1}
                      onClick={() => move(index, 1)}
                    >
                      <span aria-hidden="true">▼</span>
                    </Button>
                  </div>
                  <Button
                    type="button"
                    variant="danger"
                    data-focus={`delete-${shot.id}`}
                    aria-label={`Удалить скриншот ${n}`}
                    disabled={disabled}
                    onClick={() => setDeleting(shot.id)}
                  >
                    Удалить
                  </Button>
                </div>
              </li>
            );
          })}
        </ol>
      )}

      <div className="flex flex-wrap items-center gap-4">
        <Button
          type="button"
          variant="label"
          data-focus="upload"
          disabled={disabled || full}
          onClick={() => fileInput.current?.click()}
        >
          {pending === "upload" ? "Загружаем…" : "Добавить скриншот"}
        </Button>
        {full && <p className="text-sm text-label">{LIMIT_TEXT}</p>}
        <input
          ref={fileInput}
          type="file"
          accept={SCREENSHOT_TYPES.join(",")}
          hidden
          aria-label="Файл скриншота"
          onChange={pickFile}
        />
      </div>
      <p className="text-sm text-text-muted">
        JPEG, PNG или WebP, до 5 МБ. Метаданные (EXIF, в том числе место съёмки) удаляются.
      </p>
      {failureFor("upload")}
      <p role="status" className="text-sm text-success">
        {notice}
      </p>

      <AlertDialog open={deleting !== null} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogTitle>Удалить скриншот?</AlertDialogTitle>
          <AlertDialogDescription>Файл удалится навсегда. Отменить нельзя.</AlertDialogDescription>
          <div className="flex flex-wrap gap-4">
            <AlertDialogAction asChild>
              <Button
                type="button"
                variant="destructive"
                onClick={(event) => {
                  event.preventDefault();
                  const id = deleting;
                  setDeleting(null);
                  if (id !== null) {
                    remove(id);
                  }
                }}
              >
                Удалить
              </Button>
            </AlertDialogAction>
            <AlertDialogCancel asChild>
              <Button type="button" variant="secondary">
                Отмена
              </Button>
            </AlertDialogCancel>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
