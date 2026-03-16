import { API_BASE_URL, STORAGE_KEYS } from "./constants";
import { mockDailyPoem } from "./mockData";
import { readJson, writeJson } from "./storage";
import type { ArchiveItem, DailyPoemResponse, FavouritePoem, NotificationPreference, PoemDetailResponse, PoetItem } from "../types/poetry";

type RawFavourite = {
  poem_id?: string;
  poemId?: string;
  title?: string;
  author?: string;
  date_featured?: string;
  dateFeatured?: string;
  poem_text?: string;
  poemText?: string;
};

type AnonymousAuthResponse = {
  user_id: string;
  token: string;
};

type PushSubscriptionPayload = {
  endpoint: string;
  keys: {
    p256dh: string;
    auth: string;
  };
};

function getStoredToken(): string | null {
  const fromStorage = localStorage.getItem(STORAGE_KEYS.authToken);
  if (fromStorage && fromStorage.trim()) {
    return fromStorage;
  }

  const fromEnv = import.meta.env.VITE_AUTH_TOKEN;
  if (typeof fromEnv === "string" && fromEnv.trim()) {
    return fromEnv;
  }

  return null;
}

async function issueAnonymousToken(): Promise<string> {
  const endpoint = `${API_BASE_URL}/v1/auth/anonymous`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new Error(`anonymous auth endpoint returned ${response.status}`);
  }

  const payload = (await response.json()) as AnonymousAuthResponse;
  if (!payload.token || !payload.token.trim()) {
    throw new Error("anonymous auth endpoint did not return a token");
  }

  localStorage.setItem(STORAGE_KEYS.authToken, payload.token);
  return payload.token;
}

async function ensureAuthToken(): Promise<string> {
  const token = getStoredToken();
  if (token) {
    return token;
  }

  return issueAnonymousToken();
}

async function authHeaders(): Promise<Record<string, string>> {
  const token = await ensureAuthToken();
  return {
    Authorization: `Bearer ${token}`,
  };
}

function normalizeFavourite(item: RawFavourite): FavouritePoem | null {
  const poemId = item.poem_id ?? item.poemId;
  if (!poemId) {
    return null;
  }

  return {
    poemId,
    title: item.title ?? "Untitled",
    author: item.author ?? "Unknown Author",
    dateFeatured: item.date_featured ?? item.dateFeatured ?? "",
    poemText: item.poem_text ?? item.poemText,
  };
}

export async function fetchDailyPoem(): Promise<{ data: DailyPoemResponse; fromCache: boolean }> {
  const endpoint = `${API_BASE_URL}/v1/daily`;

  try {
    const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
    if (!response.ok) {
      throw new Error(`daily endpoint returned ${response.status}`);
    }

    const data = (await response.json()) as DailyPoemResponse;
    writeJson(STORAGE_KEYS.cachedDaily, data);
    return { data, fromCache: false };
  } catch {
    const cached = readJson<DailyPoemResponse>(STORAGE_KEYS.cachedDaily);
    if (cached) {
      return { data: cached, fromCache: true };
    }

    writeJson(STORAGE_KEYS.cachedDaily, mockDailyPoem);
    return { data: mockDailyPoem, fromCache: true };
  }
}

export async function fetchPoemById(poemId: string): Promise<PoemDetailResponse> {
  const endpoint = `${API_BASE_URL}/v1/poems/${encodeURIComponent(poemId)}`;
  const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`poem endpoint returned ${response.status}`);
  }
  return (await response.json()) as PoemDetailResponse;
}

export async function fetchPoets(): Promise<PoetItem[]> {
  const endpoint = `${API_BASE_URL}/v1/poets`;
  const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`poets endpoint returned ${response.status}`);
  }
  const payload = (await response.json()) as unknown;
  if (
    typeof payload === "object" &&
    payload !== null &&
    "poets" in payload &&
    Array.isArray((payload as { poets: unknown }).poets)
  ) {
    return (payload as { poets: PoetItem[] }).poets;
  }
  return [];
}

export async function fetchArchive(limit = 365): Promise<ArchiveItem[]> {
  const endpoint = `${API_BASE_URL}/v1/archive?limit=${encodeURIComponent(String(limit))}`;
  const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`archive endpoint returned ${response.status}`);
  }
  const payload = (await response.json()) as unknown;
  if (
    typeof payload === "object" &&
    payload !== null &&
    "poems" in payload &&
    Array.isArray((payload as { poems: unknown }).poems)
  ) {
    return (payload as { poems: ArchiveItem[] }).poems;
  }
  return [];
}

export async function fetchFavourites(): Promise<FavouritePoem[]> {
  const endpoint = `${API_BASE_URL}/v1/me/favourites`;
  const response = await fetch(endpoint, {
    headers: {
      Accept: "application/json",
      ...(await authHeaders()),
    },
  });

  if (!response.ok) {
    throw new Error(`favourites endpoint returned ${response.status}`);
  }

  const payload = (await response.json()) as unknown;
  const rawItems = Array.isArray(payload)
    ? payload
    : typeof payload === "object" && payload !== null && "favourites" in payload
      ? (payload as { favourites: unknown }).favourites
      : [];

  if (!Array.isArray(rawItems)) {
    return [];
  }

  return rawItems
    .map((item) => (typeof item === "object" && item !== null ? normalizeFavourite(item as RawFavourite) : null))
    .filter((item): item is FavouritePoem => item !== null);
}

export async function createFavourite(poemId: string): Promise<void> {
  const endpoint = `${API_BASE_URL}/v1/me/favourites`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(await authHeaders()),
    },
    body: JSON.stringify({ poem_id: poemId }),
  });

  if (!response.ok) {
    throw new Error(`create favourite endpoint returned ${response.status}`);
  }
}

export async function deleteFavourite(poemId: string): Promise<void> {
  const endpoint = `${API_BASE_URL}/v1/me/favourites/${encodeURIComponent(poemId)}`;
  const response = await fetch(endpoint, {
    method: "DELETE",
    headers: {
      ...(await authHeaders()),
    },
  });

  if (!response.ok) {
    throw new Error(`delete favourite endpoint returned ${response.status}`);
  }
}

export async function fetchNotificationPreference(): Promise<NotificationPreference> {
  const endpoint = `${API_BASE_URL}/v1/me/notifications/preferences`;
  const response = await fetch(endpoint, {
    headers: {
      Accept: "application/json",
      ...(await authHeaders()),
    },
  });

  if (!response.ok) {
    throw new Error(`notification preferences endpoint returned ${response.status}`);
  }

  return (await response.json()) as NotificationPreference;
}

export async function updateNotificationPreference(payload: NotificationPreference): Promise<NotificationPreference> {
  const endpoint = `${API_BASE_URL}/v1/me/notifications/preferences`;
  const response = await fetch(endpoint, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(await authHeaders()),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`update notification preferences endpoint returned ${response.status}`);
  }

  return (await response.json()) as NotificationPreference;
}

export async function createNotificationSubscription(payload: PushSubscriptionPayload): Promise<void> {
  const endpoint = `${API_BASE_URL}/v1/me/notifications/subscriptions`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(await authHeaders()),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`create notification subscription endpoint returned ${response.status}`);
  }
}

export async function deleteNotificationSubscription(endpointUrl: string): Promise<void> {
  const endpoint = `${API_BASE_URL}/v1/me/notifications/subscriptions`;
  const response = await fetch(endpoint, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
      ...(await authHeaders()),
    },
    body: JSON.stringify({ endpoint: endpointUrl }),
  });

  if (!response.ok) {
    throw new Error(`delete notification subscription endpoint returned ${response.status}`);
  }
}
