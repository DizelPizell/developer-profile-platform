import { FormField } from "@/components/form-field";
import { Button } from "@/components/ui/button";
import type { Contact, ContactItemError, ContactWrite } from "@/lib/api";

// The «Контакты» block of the profile form (ADR-020, profile-contacts.png). It has no
// request of its own: the list goes with «Сохранить», whole, and only when it changed.

const STANDARD = {
  EMAIL: {
    label: "Email",
    placeholder: "name@example.com",
    hint: "Латиницей, без пробелов",
    maxLength: 254,
  },
  TELEGRAM: {
    label: "Telegram",
    placeholder: "@username",
    hint: "Имя пользователя или ссылка t.me/…",
    maxLength: 64,
  },
  LINKEDIN: {
    label: "LinkedIn",
    placeholder: "linkedin.com/in/…",
    hint: "Ссылка на профиль вида linkedin.com/in/имя",
    maxLength: 150,
  },
  PHONE: {
    label: "Телефон",
    placeholder: "+79991234567",
    hint: "Формат: +79991234567, пробелы и скобки уберём",
    maxLength: 32,
  },
};
type StandardType = keyof typeof STANDARD;

/** The fields in the form, top to bottom. */
const FORM_ORDER: StandardType[] = ["EMAIL", "TELEGRAM", "LINKEDIN", "PHONE"];
/** The order of the list that is sent: the one the public page mockup shows. */
const SEND_ORDER: StandardType[] = ["TELEGRAM", "LINKEDIN", "EMAIL", "PHONE"];

const OTHER_MAX = 3;
const LABEL_MAX_LENGTH = 40;
const URL_MAX_LENGTH = 2048;

export type ContactsForm = Record<StandardType, string> & {
  other: { label: string; url: string }[];
};

/** Error texts by form key: a standard type, `other.<row>.label` or `other.<row>.url`. */
export type ContactErrors = Record<string, string>;

/**
 * What the fields show for stored contacts. LinkedIn takes the link, not the stored
 * slug: the server accepts only linkedin.com/in/{slug}, so a slug would fail the
 * next save.
 */
export function contactsForm(contacts: Contact[]): ContactsForm {
  const form: ContactsForm = { EMAIL: "", TELEGRAM: "", LINKEDIN: "", PHONE: "", other: [] };
  for (const contact of contacts) {
    if (contact.type === "OTHER") {
      form.other.push({ label: contact.label ?? "", url: contact.url });
    } else if (contact.type === "TELEGRAM") {
      form.TELEGRAM = `@${contact.value}`;
    } else {
      form[contact.type] = contact.type === "LINKEDIN" ? contact.url : contact.value;
    }
  }
  return form;
}

/**
 * The list for PATCH and, for each item, the form key it came from: an empty
 * standard field and a fully empty row are not sent, so the index of a server
 * error is not the place in the form.
 */
export function buildContacts(form: ContactsForm): { list: ContactWrite[]; keys: string[] } {
  const list: ContactWrite[] = [];
  const keys: string[] = [];
  for (const type of SEND_ORDER) {
    if (form[type].trim() !== "") {
      list.push({ type, value: form[type] });
      keys.push(type);
    }
  }
  form.other.forEach((row, index) => {
    if (row.label.trim() !== "" || row.url.trim() !== "") {
      list.push({ type: "OTHER", value: row.url, label: row.label });
      keys.push(`other.${index}`);
    }
  });
  return { list, keys };
}

const VALUE_ERRORS: Record<string, string> = {
  invalid_email: "Укажите адрес латиницей: кириллические домены пока не поддерживаются.",
  invalid_telegram: "Нужно имя пользователя или ссылка на профиль, а не приглашение.",
  invalid_linkedin: "Нужна ссылка на профиль вида linkedin.com/in/имя.",
  invalid_phone: "Укажите номер с плюсом, например +79991234567.",
  invalid_url: "Допустимы только ссылки http и https.",
  // Only a row with a name and no link gets here: empty standard fields are not sent.
  string_too_short: "Укажите ссылку.",
};

const LABEL_ERRORS: Record<string, string> = {
  missing: "Укажите название.",
  string_too_long: `Не больше ${LABEL_MAX_LENGTH} символов.`,
  control_characters: "Недопустимые символы.",
};

/** Server item errors as texts by form key; `keys` is from the list that was sent. */
export function contactErrorTexts(items: ContactItemError[], keys: string[]): ContactErrors {
  const errors: ContactErrors = {};
  for (const { index, field, type } of items) {
    const key = keys[index];
    if (key === undefined) {
      continue;
    }
    const isLabel = field === "label";
    const formKey = key.startsWith("other.") ? `${key}.${isLabel ? "label" : "url"}` : key;
    errors[formKey] ??=
      (isLabel ? LABEL_ERRORS[type] : VALUE_ERRORS[type]) ?? "Некорректное значение.";
  }
  return errors;
}

/** «Сохранено как: …» for a stored standard contact. */
function savedAs(contact: Contact): string {
  if (contact.type === "TELEGRAM") {
    return `@${contact.value}`;
  }
  return contact.type === "LINKEDIN" ? `in/${contact.value}` : contact.value;
}

export function ContactsBlock({
  form,
  saved,
  published,
  errors,
  readOnly,
  onChange,
}: {
  form: ContactsForm;
  /** The stored contacts, for «Сохранено как: …». */
  saved: Contact[];
  published: boolean;
  errors: ContactErrors;
  readOnly: boolean;
  /** `rowsChanged` when a row was added or removed: row errors no longer match. */
  onChange: (form: ContactsForm, rowsChanged?: boolean) => void;
}) {
  const savedForm = contactsForm(saved);
  const full = form.other.length >= OTHER_MAX;

  function setRow(index: number, patch: Partial<ContactsForm["other"][number]>) {
    onChange({
      ...form,
      other: form.other.map((row, at) => (at === index ? { ...row, ...patch } : row)),
    });
  }

  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-heading text-base leading-normal uppercase">Контакты</h2>
      <p className="border-4 border-outline bg-bg px-4 py-3">
        {published
          ? "Профиль опубликован: сохранённые контакты сразу видны на публичной странице. Email и телефон показываются только по клику."
          : "Контакты станут видны на публичной странице после публикации профиля. Email и телефон показываются только по клику."}
      </p>

      {FORM_ORDER.map((type) => {
        const text = STANDARD[type];
        const stored = saved.find((contact) => contact.type === type);
        // The caption is about the stored value, so it leaves once the field is edited.
        const untouched = stored !== undefined && form[type] === savedForm[type];
        return (
          <FormField
            key={type}
            id={`contact-${type}`}
            label={text.label}
            placeholder={text.placeholder}
            hint={untouched ? `Сохранено как: ${savedAs(stored)}` : text.hint}
            value={form[type]}
            maxLength={text.maxLength}
            error={errors[type]}
            readOnly={readOnly}
            counter={false}
            onChange={(value) => onChange({ ...form, [type]: value })}
          />
        );
      })}

      {form.other.map((row, index) => (
        <fieldset key={index} className="flex flex-col gap-4 border-4 border-outline px-4 py-4">
          <legend className="sr-only">Другой способ {index + 1}</legend>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p aria-hidden="true" className="caps-label text-text-muted">
              Другой способ {index + 1}
            </p>
            <Button
              type="button"
              variant="secondary"
              disabled={readOnly}
              aria-label={`Удалить: другой способ ${index + 1}`}
              onClick={() =>
                onChange({ ...form, other: form.other.filter((_, at) => at !== index) }, true)
              }
            >
              Удалить
            </Button>
          </div>
          <FormField
            id={`contact-other-${index}-label`}
            label="Название"
            placeholder="Например: Мой блог"
            hint={`До ${LABEL_MAX_LENGTH} символов`}
            value={row.label}
            maxLength={LABEL_MAX_LENGTH}
            error={errors[`other.${index}.label`]}
            readOnly={readOnly}
            counter={false}
            onChange={(label) => setRow(index, { label })}
          />
          <FormField
            id={`contact-other-${index}-url`}
            label="Ссылка"
            hint="Только http и https"
            value={row.url}
            maxLength={URL_MAX_LENGTH}
            error={errors[`other.${index}.url`]}
            readOnly={readOnly}
            counter={false}
            onChange={(url) => setRow(index, { url })}
          />
        </fieldset>
      ))}

      <div className="flex flex-col items-start gap-2">
        <Button
          type="button"
          variant="secondary"
          disabled={full || readOnly}
          onClick={() =>
            onChange({ ...form, other: [...form.other, { label: "", url: "" }] }, true)
          }
        >
          + Другие способы связи
        </Button>
        <p className={full ? "text-sm text-label" : "text-sm text-text-muted"}>
          {full
            ? "Максимум 3 других способа связи"
            : `Добавлено ${form.other.length} из ${OTHER_MAX}`}
        </p>
      </div>
    </div>
  );
}
