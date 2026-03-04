import type { DailyPoemResponse } from "../types/poetry";

export const mockDailyPoem: DailyPoemResponse = {
  date: "2026-02-19",
  poem: {
    id: "mock-ozymandias",
    title: "Ozymandias",
    text: [
      "I met a traveller from an antique land",
      "Who said: \"Two vast and trunkless legs of stone",
      "Stand in the desert. Near them, on the sand,",
      "Half sunk, a shattered visage lies...",
    ].join("\n"),
    linecount: 4,
  },
  author: {
    id: "percy-bysshe-shelley",
    name: "Percy Bysshe Shelley",
    bio: "English Romantic poet known for lyrical intensity and political radicalism.",
    image_url: "https://upload.wikimedia.org/wikipedia/commons/6/64/Percy_Bysshe_Shelley_by_Alfred_Clint_1829.jpg",
  },
};
