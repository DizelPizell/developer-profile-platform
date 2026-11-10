import { Press_Start_2P, Tektur } from "next/font/google";

// next/font needs literal options here. Both fonts must keep the cyrillic subset:
// the interface is in Russian (DESIGN.md). fonts.test.ts checks this file.

// Large headings only, at multiples of 8 px: the face is drawn on an 8 px grid.
export const pressStart2P = Press_Start_2P({
  weight: "400",
  subsets: ["latin", "cyrillic"],
  display: "swap",
  variable: "--font-press-start-2p",
});

// Body text, form fields, buttons, names and small labels. It replaced Pixelify
// Sans, whose Cyrillic «д», «в», «з», «ы», «ь» read as Latin letters.
export const tektur = Tektur({
  subsets: ["latin", "cyrillic"],
  display: "swap",
  variable: "--font-tektur",
});
