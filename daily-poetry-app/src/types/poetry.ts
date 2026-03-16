export type DailyPoemResponse = {
  date: string;
  poem: {
    id: string;
    title: string;
    text: string;
    linecount: number;
  };
  author: {
    id: string;
    name: string;
    bio: string;
    image_url: string;
  };
};

export type PoemDetailResponse = {
  poem: {
    id: string;
    title: string;
    text: string;
    linecount: number;
  };
  author: {
    id: string;
    name: string;
    bio: string;
    image_url: string | null;
  };
  date_featured: string | null;
};

export type ArchiveItem = {
  date_featured: string;
  poem_id: string;
  title: string;
  author: string;
};

export type FavouritePoem = {
  poemId: string;
  title: string;
  author: string;
  dateFeatured: string;
  poemText?: string;
};

export type PoetItem = {
  id: string;
  name: string;
  bio: string | null;
  image_url: string | null;
};

export type FavouritesSource = "remote" | "local";

export type NotificationPreference = {
  enabled: boolean;
  time_zone: string;
  local_hour: number;
};
