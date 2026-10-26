import { Pixelify_Sans, Press_Start_2P } from "next/font/google";

// next/font needs literal options here. Both fonts must keep the cyrillic subset:
// the interface is in Russian (DESIGN.md). fonts.test.ts checks this file.

// Short headings and labels only.
export const pressStart2P = Press_Start_2P({
  weight: "400",
  subsets: ["latin", "cyrillic"],
  display: "swap",
  variable: "--font-press-start-2p",
});

// Body text, form fields and buttons.
export const pixelifySans = Pixelify_Sans({
  subsets: ["latin", "cyrillic"],
  display: "swap",
  variable: "--font-pixelify-sans",
});
