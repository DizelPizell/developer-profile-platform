import { redirect } from "next/navigation";

// "/" leads to the cabinet; /me sends a visitor without a session to /login.
export default function Home() {
  redirect("/me");
}
