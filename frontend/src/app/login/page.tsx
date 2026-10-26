import type { Metadata } from "next";
import { Suspense } from "react";

import { LoginLayout, LoginScreen } from "./login-screen";

export const metadata: Metadata = {
  title: "Вход — Developer Profile Platform",
};

export default function LoginPage() {
  // useSearchParams needs a Suspense boundary for the page to be prerendered.
  // The fallback is the screen with a disabled button and no error block.
  return (
    <Suspense fallback={<LoginLayout errorMessage={null} />}>
      <LoginScreen />
    </Suspense>
  );
}
