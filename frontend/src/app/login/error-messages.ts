// Texts for /login?error=<CODE> (DESIGN.md). The callback sends only these codes
// (ADR-012); any other value gets the neutral text and is never shown itself.
const LOGIN_ERROR_MESSAGES: Record<string, string> = {
  ACCESS_DENIED: "Вход отменён на стороне GitHub. Попробуйте ещё раз.",
  INVALID_STATE: "Сеанс входа устарел или был прерван. Начните вход заново.",
  MISSING_CODE: "GitHub не вернул код входа. Начните вход заново.",
  OAUTH_CODE_INVALID: "Код входа истёк или уже использован. Начните вход заново.",
  GITHUB_UNAVAILABLE: "GitHub сейчас недоступен. Попробуйте позже.",
  INTERNAL_ERROR: "Что-то пошло не так на нашей стороне. Попробуйте позже.",
};

export const UNKNOWN_LOGIN_ERROR_MESSAGE = "Не удалось войти. Попробуйте ещё раз.";

/** null when there is no error parameter at all. */
export function loginErrorMessage(code: string | null): string | null {
  if (code === null) {
    return null;
  }
  return Object.hasOwn(LOGIN_ERROR_MESSAGES, code)
    ? LOGIN_ERROR_MESSAGES[code]
    : UNKNOWN_LOGIN_ERROR_MESSAGE;
}
