import { MessageScreen } from "@/components/message-screen";

// One screen for every case the API does not tell apart (step 4.3): no profile, a
// private one, another user's project, a draft, hidden or archived one, a malformed
// id. No link back to the profile: it would tell which case it is.
export default function ProjectNotFound() {
  return (
    <MessageScreen
      code="404"
      title="Проект не найден"
      text="Возможно, он скрыт, ещё не опубликован или ссылка неверна."
    />
  );
}
