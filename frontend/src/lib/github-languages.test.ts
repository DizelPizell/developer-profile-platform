import { describe, expect, test } from "vitest";

import { languageShares, LANGUAGES_SHOWN, shareText } from "./github-languages";

const language = (name: string, bytes: number) => ({ name, bytes });

describe("languageShares", () => {
  test("each share is its bytes over the sum, in the given order", () => {
    expect(languageShares([language("Python", 750), language("Shell", 250)])).toEqual({
      shown: [
        { name: "Python", percent: 75 },
        { name: "Shell", percent: 25 },
      ],
      others: null,
    });
  });

  test("exactly six languages make no «Другие»", () => {
    const six = ["A", "B", "C", "D", "E", "F"].map((name) => language(name, 10));

    const shares = languageShares(six);

    expect(LANGUAGES_SHOWN).toBe(6);
    expect(shares.shown.map((share) => share.name)).toEqual(["A", "B", "C", "D", "E", "F"]);
    expect(shares.others).toBeNull();
  });

  test("the seventh and later languages are summed into one share of the whole", () => {
    const shares = languageShares([
      language("Python", 600),
      ...["A", "B", "C", "D", "E"].map((name) => language(name, 60)),
      language("G", 70),
      language("H", 30),
    ]);

    expect(shares.shown).toHaveLength(6);
    expect(shares.shown[0]).toEqual({ name: "Python", percent: 60 });
    expect(shares.others).toEqual({ percent: 10 });
  });

  test("a sum of 0 bytes gives names without shares", () => {
    const shares = languageShares([
      ...["A", "B", "C", "D", "E", "F"].map((name) => language(name, 0)),
      language("G", 0),
    ]);

    expect(shares.shown.every((share) => share.percent === null)).toBe(true);
    expect(shares.others).toEqual({ percent: null });
  });

  test("an empty list", () => {
    expect(languageShares([])).toEqual({ shown: [], others: null });
  });

  test("the number of chips can be given; the shares stay shares of the whole", () => {
    const shares = languageShares(
      [
        language("A", 400),
        language("B", 300),
        language("C", 200),
        language("D", 60),
        language("E", 40),
      ],
      3,
    );

    expect(shares.shown).toEqual([
      { name: "A", percent: 40 },
      { name: "B", percent: 30 },
      { name: "C", percent: 20 },
    ]);
    expect(shares.others).toEqual({ percent: 10 });
  });

  test("as many languages as chips make no «Другие»", () => {
    const three = ["A", "B", "C"].map((name) => language(name, 10));

    expect(languageShares(three, 3).shown).toHaveLength(3);
    expect(languageShares(three, 3).others).toBeNull();
  });

  test("the default stays six when no number is given", () => {
    const seven = ["A", "B", "C", "D", "E", "F", "G"].map((name) => language(name, 10));

    expect(languageShares(seven).shown).toHaveLength(LANGUAGES_SHOWN);
  });
});

describe("shareText", () => {
  test.each([
    [62, "62 %"],
    [61.5, "62 %"],
    [61.4, "61 %"],
    [100, "100 %"],
    [0.5, "1 %"],
    [0.49, "<1 %"],
    [0, "<1 %"],
  ])("%s → %s", (percent, text) => {
    expect(shareText(percent)).toBe(text);
  });
});
