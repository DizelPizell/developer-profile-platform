"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";

import { FormField } from "@/components/form-field";
import { RequestErrorAlert } from "@/components/request-error";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  missingProfileFields,
  PROFILE_FIELD_MAX_LENGTH,
  PROFILE_FIELDS,
  profileContactErrors,
  profileFieldErrors,
  publishProfile,
  unpublishProfile,
  updateProfile,
  type OwnProfileResponse,
  type ProfileField,
  type ProfileStatus,
  type ProfileUpdate,
} from "@/lib/api";

import {
  buildContacts,
  ContactsBlock,
  contactErrorTexts,
  contactsForm,
  type ContactErrors,
} from "./profile-contacts";

// Texts from the cabinet mockup (DESIGN.md).
const FIELDS: Record<
  ProfileField,
  { label: string; hint: string; placeholder: string; required?: boolean }
> = {
  display_name: {
    label: "Имя",
    hint: "Обязательно для публикации",
    placeholder: "Как вас называть",
    required: true,
  },
  headline: {
    label: "Заголовок",
    hint: "Одна строка под именем. Обязательно для публикации",
    placeholder: "Например: Fullstack-разработчик, Python и TypeScript",
    required: true,
  },
  location: { label: "Локация", hint: "Необязательно", placeholder: "Город, страна" },
  bio: {
    label: "О себе",
    hint: "Простой текст, без разметки",
    placeholder: "Чем занимаетесь, что умеете, какие задачи решаете лучше всего",
  },
};

type Values = Record<ProfileField, string>;
type Action = "save" | "publish" | "unpublish";

function toValues(profile: OwnProfileResponse): Values {
  return {
    display_name: profile.display_name ?? "",
    headline: profile.headline ?? "",
    bio: profile.bio ?? "",
    location: profile.location ?? "",
  };
}

/** Only the fields that differ from the stored profile; an emptied field is cleared. */
function changedFields(values: Values, saved: OwnProfileResponse): ProfileUpdate {
  const update: ProfileUpdate = {};
  for (const field of PROFILE_FIELDS) {
    if (values[field] !== (saved[field] ?? "")) {
      update[field] = values[field] === "" ? null : values[field];
    }
  }
  return update;
}

function fieldErrorMessage(field: ProfileField, type: string): string {
  if (type === "string_too_long") {
    return `Не больше ${PROFILE_FIELD_MAX_LENGTH[field]} символов.`;
  }
  if (type === "control_characters") {
    return "Недопустимые символы.";
  }
  return "Некорректное значение.";
}

/** «Имя» и «Заголовок» */
function fieldList(fields: ProfileField[]): string {
  const names = fields.map((field) => `«${FIELDS[field].label}»`);
  return names.length > 1 ? `${names.slice(0, -1).join(", ")} и ${names.at(-1)}` : names[0];
}

export function ProfileEditor({ initialProfile }: { initialProfile: OwnProfileResponse }) {
  const router = useRouter();
  const [saved, setSaved] = useState(initialProfile);
  const [values, setValues] = useState(() => toValues(initialProfile));
  const [pending, setPending] = useState<Action | null>(null);
  // Blocks a second request before the disabled state reaches the DOM.
  const inFlight = useRef(false);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<ProfileField, string>>>({});
  const [incomplete, setIncomplete] = useState<{ action: Action; fields: ProfileField[] } | null>(
    null,
  );
  const [requestError, setRequestError] = useState<unknown>(null);
  const [savedNotice, setSavedNotice] = useState(false);
  const [contacts, setContacts] = useState(() => contactsForm(initialProfile.contacts));
  const [contactErrors, setContactErrors] = useState<ContactErrors>({});

  const update = changedFields(values, saved);
  // Both lists come from buildContacts, so an untouched form never reads as changed.
  const built = buildContacts(contacts);
  const storedList = buildContacts(contactsForm(saved.contacts)).list;
  if (JSON.stringify(built.list) !== JSON.stringify(storedList)) {
    update.contacts = built.list;
  }
  const dirty = Object.keys(update).length > 0;
  const busy = pending !== null;
  const published = saved.status === "PUBLISHED";

  async function run(
    action: Action,
    call: () => Promise<OwnProfileResponse>,
    { keepEdits }: { keepEdits: boolean },
  ) {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setPending(action);
    setFieldErrors({});
    setContactErrors({});
    setIncomplete(null);
    setRequestError(null);
    setSavedNotice(false);
    try {
      const profile = await call();
      setSaved(profile);
      if (!keepEdits) {
        // The server normalizes values (trim, blank → null); show what it stored.
        setValues(toValues(profile));
        setContacts(contactsForm(profile.contacts));
      }
      setSavedNotice(action === "save");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        router.replace("/login");
        return;
      }
      const missing = missingProfileFields(error);
      const perField = Object.entries(profileFieldErrors(error)) as [ProfileField, string][];
      // The keys of the list this request sent: the form cannot change during it.
      const perContact = contactErrorTexts(profileContactErrors(error).items, built.keys);
      if (missing.length > 0) {
        setIncomplete({ action, fields: missing });
      } else if (perField.length > 0 || Object.keys(perContact).length > 0) {
        setFieldErrors(
          Object.fromEntries(perField.map(([field, type]) => [field, fieldErrorMessage(field, type)])),
        );
        setContactErrors(perContact);
      } else {
        setRequestError(error);
      }
    } finally {
      inFlight.current = false;
      setPending(null);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (dirty) {
      void run("save", () => updateProfile(update), { keepEdits: false });
    }
  }

  function handleChange(field: ProfileField, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    setSavedNotice(false);
  }

  function field(name: ProfileField, multiline = false) {
    const text = FIELDS[name];
    return (
      <FormField
        id={`profile-${name}`}
        label={text.label}
        required={text.required}
        hint={text.hint}
        placeholder={text.placeholder}
        value={values[name]}
        maxLength={PROFILE_FIELD_MAX_LENGTH[name]}
        error={fieldErrors[name]}
        invalid={incomplete?.fields.includes(name)}
        readOnly={busy}
        multiline={multiline}
        onChange={(value) => handleChange(name, value)}
      />
    );
  }

  const publicPath = `/u/${saved.slug}`;

  return (
    <>
      <section className="flex flex-col gap-6 bg-panel px-8 py-8 shadow-panel sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-3">
          <h1 className="font-heading text-2xl leading-relaxed text-balance uppercase">Мой профиль</h1>
          <p className="text-lg break-all">
            Публичный адрес:{" "}
            {published ? (
              <a href={publicPath} className="text-label underline underline-offset-4">
                {publicPath}
              </a>
            ) : (
              <span>{publicPath}</span>
            )}{" "}
            <span className="text-text-muted">(не меняется)</span>
          </p>
          <p className="text-base text-text-muted">
            Опубликованный профиль видят все по этой ссылке.
          </p>
        </div>
        <div className="flex flex-col items-start gap-3 sm:items-end">
          <p className="caps-label text-label">Статус</p>
          <StatusBadge status={saved.status} />
        </div>
      </section>

      {incomplete && <IncompleteAlert action={incomplete.action} fields={incomplete.fields} />}
      {requestError !== null && <RequestErrorAlert error={requestError} />}

      <form
        noValidate
        aria-label="Профиль"
        onSubmit={handleSubmit}
        className="flex flex-col gap-6 bg-panel px-8 py-8 shadow-panel"
      >
        <div className="grid gap-6 sm:grid-cols-2">
          {field("display_name")}
          {field("location")}
        </div>
        {field("headline")}
        {field("bio", true)}

        <ContactsBlock
          form={contacts}
          saved={saved.contacts}
          published={published}
          errors={contactErrors}
          readOnly={busy}
          onChange={(form, rowsChanged) => {
            setContacts(form);
            setSavedNotice(false);
            if (rowsChanged) {
              // Row errors are keyed by place, which a removed row shifts.
              setContactErrors({});
            }
          }}
        />

        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-4">
            <Button type="submit" disabled={!dirty || busy}>
              Сохранить
            </Button>
            <Button
              type="button"
              variant="label"
              disabled={published || dirty || busy}
              onClick={() => void run("publish", publishProfile, { keepEdits: false })}
            >
              Опубликовать
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={!published || busy}
              // Unpublish does not use the form, so unsaved edits stay in it.
              onClick={() => void run("unpublish", unpublishProfile, { keepEdits: true })}
            >
              Скрыть
            </Button>
            <p role="status" className="text-lg text-success">
              {savedNotice ? "Сохранено" : ""}
            </p>
          </div>
          {!published && dirty && (
            <p className="text-sm text-text-muted">
              Сохраните изменения, чтобы опубликовать профиль.
            </p>
          )}
          {!published && (
            <p className="text-sm text-text-muted">
              «Скрыть» доступно, когда профиль опубликован.
            </p>
          )}
        </div>
      </form>
    </>
  );
}

function StatusBadge({ status }: { status: ProfileStatus }) {
  const published = status === "PUBLISHED";
  return (
    <span
      className={
        published
          ? "border-4 border-success px-3 py-2 caps-label text-success"
          : "border-4 border-label px-3 py-2 caps-label text-label"
      }
    >
      {published ? "В сети · PUBLISHED" : "Черновик · PRIVATE"}
    </span>
  );
}

function IncompleteAlert({ action, fields }: { action: Action; fields: ProfileField[] }) {
  const list = fieldList(fields);
  return (
    <Alert className="flex gap-4">
      <span
        aria-hidden="true"
        className="flex size-8 shrink-0 items-center justify-center bg-error font-heading text-base text-outline"
      >
        !
      </span>
      <div className="flex flex-col gap-2">
        <p className="caps-label">
          {action === "save" ? "Нельзя сохранить" : "Нельзя опубликовать"}
        </p>
        <p className="text-text">
          {fields.length > 1 ? "Заполните обязательные поля: " : "Заполните обязательное поле: "}
          {list}.
          {action === "save" && " Очистить их можно только у скрытого профиля."}
        </p>
      </div>
    </Alert>
  );
}
