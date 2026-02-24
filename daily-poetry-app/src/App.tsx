import type { MouseEvent } from "react";
import { useEffect, useState } from "react";
import { FavouritesView } from "./components/FavouritesView";
import { TodayView } from "./components/TodayView";
import { useFavourites } from "./hooks/useFavourites";
import { useNotifications } from "./hooks/useNotifications";
import { fetchDailyPoem, fetchPoemById } from "./lib/api";
import { STORAGE_KEYS } from "./lib/constants";
import { formatIsoDate } from "./lib/date";
import type { DailyPoemResponse, PoemDetailResponse } from "./types/poetry";

type ViewMode = "daily_poem" | "favourites";
type ThemeMode = "light" | "dark";
type AppRoute = { kind: "home" } | { kind: "app" } | { kind: "poem"; poemId: string };

const SITE_ORIGIN = "https://daily-poetry.com";
const DEFAULT_OG_IMAGE = `${SITE_ORIGIN}/dailypoetry-light.png`;

function getInitialTheme(): ThemeMode {
  const stored = localStorage.getItem(STORAGE_KEYS.theme);
  if (stored === "light" || stored === "dark") {
    return stored;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function getAppRoute(pathname: string): AppRoute {
  if (pathname === "/app" || pathname.startsWith("/app/")) {
    return { kind: "app" };
  }

  const poemMatch = pathname.match(/^\/poems\/([^/]+)\/?$/);
  if (poemMatch) {
    return { kind: "poem", poemId: decodeURIComponent(poemMatch[1]) };
  }

  return { kind: "home" };
}

function setCanonicalUrl(href: string): void {
  let canonical = document.querySelector("link[rel='canonical']") as HTMLLinkElement | null;
  if (!canonical) {
    canonical = document.createElement("link");
    canonical.rel = "canonical";
    document.head.append(canonical);
  }
  canonical.href = href;
}

function setMetaTagByName(name: string, content: string): void {
  let meta = document.querySelector(`meta[name='${name}']`) as HTMLMetaElement | null;
  if (!meta) {
    meta = document.createElement("meta");
    meta.name = name;
    document.head.append(meta);
  }
  meta.content = content;
}

function setMetaTagByProperty(property: string, content: string): void {
  let meta = document.querySelector(`meta[property='${property}']`) as HTMLMetaElement | null;
  if (!meta) {
    meta = document.createElement("meta");
    meta.setAttribute("property", property);
    document.head.append(meta);
  }
  meta.content = content;
}

function setStructuredData(data: Record<string, unknown>): void {
  const scriptId = "seo-structured-data";
  let script = document.getElementById(scriptId) as HTMLScriptElement | null;
  if (!script) {
    script = document.createElement("script");
    script.id = scriptId;
    script.type = "application/ld+json";
    document.head.append(script);
  }
  script.textContent = JSON.stringify(data);
}

function LandingView({
  theme,
  onToggleTheme,
  onNavigate,
}: {
  theme: ThemeMode;
  onToggleTheme: () => void;
  onNavigate: (event: MouseEvent<HTMLAnchorElement>, path: string) => void;
}) {
  const topLogoSrc = theme === "dark" ? "/dailypoetry-light.png" : "/dailypoetry-dark.png";
  const currentHour = new Date().getHours();
  const landingHeadline = currentHour >= 4 && currentHour < 17 ? "Start your day in verse" : "End your day in verse";

  return (
    <main className="page">
      <button
        className={theme === "dark" ? "theme-toggle app-theme-toggle theme-toggle-dark" : "theme-toggle app-theme-toggle"}
        type="button"
        onClick={onToggleTheme}
        aria-label={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
        title={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
      >
        <span className="theme-toggle-track" aria-hidden="true">
          <span className="theme-toggle-icon">☀</span>
          <span className="theme-toggle-icon">☾</span>
          <span className="theme-toggle-thumb" />
        </span>
      </button>

      <section className="landing-shell">
        <div className="top-logo-wrap">
          <img className="top-logo" src={topLogoSrc} alt="daily-poetry" />
        </div>

        <section className="panel landing-panel" aria-labelledby="landing-title">
          <h1 id="landing-title" className="landing-title">
            {landingHeadline}
          </h1>
          <p className="landing-copy">Read today&apos;s featured poem and build a quiet daily reading habit.</p>
        </section>
        <div className="landing-actions">
          <a className="landing-cta" href="/app" onClick={(event) => onNavigate(event, "/app")}>
            Today&apos;s poem
          </a>
        </div>
      </section>
    </main>
  );
}

function PoemPageView({
  theme,
  poemId,
  onToggleTheme,
  onNavigate,
}: {
  theme: ThemeMode;
  poemId: string;
  onToggleTheme: () => void;
  onNavigate: (event: MouseEvent<HTMLAnchorElement>, path: string) => void;
}) {
  const topLogoSrc = theme === "dark" ? "/dailypoetry-light.png" : "/dailypoetry-dark.png";
  const [poem, setPoem] = useState<PoemDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function loadPoem() {
      setLoading(true);
      setError(null);
      try {
        const payload = await fetchPoemById(poemId);
        if (!active) {
          return;
        }
        setPoem(payload);

        const canonicalUrl = `${SITE_ORIGIN}/poems/${encodeURIComponent(payload.poem.id)}`;
        const title = `${payload.poem.title} by ${payload.author.name} | daily-poetry`;
        const description = `Read ${payload.poem.title} by ${payload.author.name} on daily-poetry.`;
        document.title = title;
        setCanonicalUrl(canonicalUrl);
        setMetaTagByName("description", description);
        setMetaTagByName("twitter:title", title);
        setMetaTagByName("twitter:description", description);
        setMetaTagByProperty("og:title", title);
        setMetaTagByProperty("og:description", description);
        setMetaTagByProperty("og:url", canonicalUrl);
        setStructuredData({
          "@context": "https://schema.org",
          "@type": "CreativeWork",
          name: payload.poem.title,
          author: {
            "@type": "Person",
            name: payload.author.name,
          },
          text: payload.poem.text,
          url: canonicalUrl,
          datePublished: payload.date_featured ?? undefined,
        });
      } catch (loadError) {
        if (!active) {
          return;
        }
        setError(loadError instanceof Error ? loadError.message : "Failed to load poem");
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void loadPoem();
    return () => {
      active = false;
    };
  }, [poemId]);

  return (
    <main className="page">
      <button
        className={theme === "dark" ? "theme-toggle app-theme-toggle theme-toggle-dark" : "theme-toggle app-theme-toggle"}
        type="button"
        onClick={onToggleTheme}
        aria-label={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
        title={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
      >
        <span className="theme-toggle-track" aria-hidden="true">
          <span className="theme-toggle-icon">☀</span>
          <span className="theme-toggle-icon">☾</span>
          <span className="theme-toggle-thumb" />
        </span>
      </button>
      <a className="app-home-link" href="/" onClick={(event) => onNavigate(event, "/")}>
        Home
      </a>

      <div className="top-logo-wrap">
        <img className="top-logo" src={topLogoSrc} alt="daily-poetry" />
      </div>

      <section className="panel">
        <p className="date-label">
          {poem?.date_featured ? formatIsoDate(poem.date_featured, "long") : "Poem"}
        </p>
        <p className="poem-permalink-row">
          <a className="poem-permalink-link" href="/app" onClick={(event) => onNavigate(event, "/app")}>
            Today&apos;s poem
          </a>
        </p>

        {loading ? <p className="status">Loading poem...</p> : null}
        {error ? <p className="status status-error">{error}</p> : null}

        {poem ? (
          <>
            <div className="poem-card-wrap">
              <article className="poem-card">
                <h1 className="poem-title">{poem.poem.title}</h1>
                <pre className="poem-text">{poem.poem.text}</pre>
              </article>
            </div>

            <footer className="author-panel">
              <div className="author-block">
                {poem.author.image_url ? (
                  <img className="author-image" src={poem.author.image_url} alt={poem.author.name} />
                ) : null}
                <div>
                  <p className="author-name">{poem.author.name}</p>
                  <p className="author-bio">{poem.author.bio_short}</p>
                </div>
              </div>
            </footer>
          </>
        ) : null}
      </section>
    </main>
  );
}

function PoetryAppShell({
  theme,
  onToggleTheme,
  onNavigate,
}: {
  theme: ThemeMode;
  onToggleTheme: () => void;
  onNavigate: (event: MouseEvent<HTMLAnchorElement>, path: string) => void;
}) {
  const [viewMode, setViewMode] = useState<ViewMode>("daily_poem");
  const [daily, setDaily] = useState<DailyPoemResponse | null>(null);
  const [loadingDaily, setLoadingDaily] = useState(true);
  const [dailyError, setDailyError] = useState<string | null>(null);

  const {
    favourites,
    loading: loadingFavourites,
    syncing: syncingFavourites,
    error: favouritesError,
    isFavourite,
    toggleFavourite,
  } = useFavourites();
  const {
    supported: notificationsSupported,
    enabled: notificationsEnabled,
    loading: notificationsLoading,
    syncing: notificationsSyncing,
    error: notificationsError,
    toggleNotifications,
  } = useNotifications();

  useEffect(() => {
    async function loadDailyPoem() {
      setLoadingDaily(true);
      setDailyError(null);

      try {
        const result = await fetchDailyPoem();
        setDaily(result.data);
      } catch (loadError) {
        setDailyError(loadError instanceof Error ? loadError.message : "Failed to load daily poem");
      } finally {
        setLoadingDaily(false);
      }
    }

    void loadDailyPoem();
  }, []);

  const dailyPoemLogoSrc = theme === "dark" ? "/dailypoetry-light.png" : "/dailypoetry-dark.png";

  return (
    <main className="page">
      <button
        className={theme === "dark" ? "theme-toggle app-theme-toggle theme-toggle-dark" : "theme-toggle app-theme-toggle"}
        type="button"
        onClick={onToggleTheme}
        aria-label={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
        title={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
      >
        <span className="theme-toggle-track" aria-hidden="true">
          <span className="theme-toggle-icon">☀</span>
          <span className="theme-toggle-icon">☾</span>
          <span className="theme-toggle-thumb" />
        </span>
      </button>
      <a className="app-home-link" href="/" onClick={(event) => onNavigate(event, "/")}>
        Home
      </a>
      <section className="content-wrap">
        {loadingDaily ? (
          <section className="loading-splash" aria-label="Loading">
            <div className="loading-shell">
              <img className="loading-logo" src="/logo-transparent.png" alt="daily-poetry" />
              <p className="loading-title">Loading today's poem</p>
              <p className="loading-subtitle">Waking up the API server. This can take a few seconds.</p>
              <div className="loading-progress" aria-hidden="true">
                <span className="loading-progress-fill" />
              </div>
            </div>
          </section>
        ) : null}
        {dailyError ? <p className="status status-error">{dailyError}</p> : null}
        {syncingFavourites ? <p className="status">Syncing favourites...</p> : null}

        {!loadingDaily && daily && viewMode === "daily_poem" ? (
          <TodayView
            daily={daily}
            theme={theme}
            isFavourite={isFavourite(daily.poem.id)}
            favouriteSyncing={syncingFavourites}
            onToggleFavourite={() => void toggleFavourite(daily)}
          />
        ) : null}

        {viewMode === "favourites" ? (
          <FavouritesView
            favourites={favourites}
            loading={loadingFavourites}
            error={favouritesError}
            theme={theme}
            notificationsSupported={notificationsSupported}
            notificationsEnabled={notificationsEnabled}
            notificationsLoading={notificationsLoading}
            notificationsSyncing={notificationsSyncing}
            notificationsError={notificationsError}
            onToggleNotifications={() => void toggleNotifications()}
          />
        ) : null}
      </section>

      <nav className="bottom-tabs" aria-label="Primary">
        <button
          className={viewMode === "daily_poem" ? "tab-btn tab-btn-active" : "tab-btn"}
          type="button"
          onClick={() => setViewMode("daily_poem")}
          aria-label="DailyPoem"
        >
          <img className="tab-logo" src={dailyPoemLogoSrc} alt="daily-poetry" />
        </button>
        <button
          className={viewMode === "favourites" ? "tab-btn tab-btn-active" : "tab-btn"}
          type="button"
          onClick={() => setViewMode("favourites")}
          aria-label="Favourites"
        >
          <svg className="tab-heart-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12.1 21.35 10.55 19.95C5.4 15.3 2 12.25 2 8.5 2 5.45 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.45 22 8.5c0 3.75-3.4 6.8-8.55 11.45z" />
          </svg>
        </button>
      </nav>
    </main>
  );
}

function App() {
  const [theme, setTheme] = useState<ThemeMode>(getInitialTheme);
  const [route, setRoute] = useState<AppRoute>(() => getAppRoute(window.location.pathname));

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(STORAGE_KEYS.theme, theme);
  }, [theme]);

  useEffect(() => {
    function handlePopState() {
      setRoute(getAppRoute(window.location.pathname));
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    if (route.kind === "app") {
      const title = "daily-poetry";
      const description = "Read today's featured poem on daily-poetry, save favourites, and return each day for a new poem.";
      const canonicalUrl = `${SITE_ORIGIN}/app`;

      document.title = title;
      setCanonicalUrl(canonicalUrl);
      setMetaTagByName("description", description);
      setMetaTagByName("robots", "index,follow,max-image-preview:large");
      setMetaTagByName("twitter:card", "summary");
      setMetaTagByName("twitter:title", title);
      setMetaTagByName("twitter:description", description);
      setMetaTagByName("twitter:image", DEFAULT_OG_IMAGE);
      setMetaTagByProperty("og:type", "website");
      setMetaTagByProperty("og:site_name", "daily-poetry");
      setMetaTagByProperty("og:title", title);
      setMetaTagByProperty("og:description", description);
      setMetaTagByProperty("og:url", canonicalUrl);
      setMetaTagByProperty("og:image", DEFAULT_OG_IMAGE);
      setStructuredData({
        "@context": "https://schema.org",
        "@type": "WebApplication",
        name: "daily-poetry",
        url: canonicalUrl,
        applicationCategory: "LifestyleApplication",
        operatingSystem: "Web",
        description,
      });
      return;
    }

    if (route.kind === "poem") {
      const canonicalUrl = `${SITE_ORIGIN}/poems/${encodeURIComponent(route.poemId)}`;
      const title = "Poem | daily-poetry";
      const description = "Read a featured poem from daily-poetry.";

      document.title = title;
      setCanonicalUrl(canonicalUrl);
      setMetaTagByName("description", description);
      setMetaTagByName("robots", "index,follow,max-image-preview:large");
      setMetaTagByName("twitter:card", "summary");
      setMetaTagByName("twitter:title", title);
      setMetaTagByName("twitter:description", description);
      setMetaTagByName("twitter:image", DEFAULT_OG_IMAGE);
      setMetaTagByProperty("og:type", "article");
      setMetaTagByProperty("og:site_name", "daily-poetry");
      setMetaTagByProperty("og:title", title);
      setMetaTagByProperty("og:description", description);
      setMetaTagByProperty("og:url", canonicalUrl);
      setMetaTagByProperty("og:image", DEFAULT_OG_IMAGE);
      return;
    }

    const title = "daily-poetry | poetry, one day at a time";
    const description = "One poem each day, delivered simply. Read today's featured poem and save favourites.";
    const canonicalUrl = `${SITE_ORIGIN}/`;

    document.title = title;
    setCanonicalUrl(canonicalUrl);
    setMetaTagByName("description", description);
    setMetaTagByName("robots", "index,follow,max-image-preview:large");
    setMetaTagByName("twitter:card", "summary");
    setMetaTagByName("twitter:title", title);
    setMetaTagByName("twitter:description", description);
    setMetaTagByName("twitter:image", DEFAULT_OG_IMAGE);
    setMetaTagByProperty("og:type", "website");
    setMetaTagByProperty("og:site_name", "daily-poetry");
    setMetaTagByProperty("og:title", title);
    setMetaTagByProperty("og:description", description);
    setMetaTagByProperty("og:url", canonicalUrl);
    setMetaTagByProperty("og:image", DEFAULT_OG_IMAGE);
    setStructuredData({
      "@context": "https://schema.org",
      "@type": "WebSite",
      name: "daily-poetry",
      url: SITE_ORIGIN,
      description,
      potentialAction: {
        "@type": "ReadAction",
        target: `${SITE_ORIGIN}/app`,
      },
    });
  }, [route]);

  function navigate(path: string): void {
    if (window.location.pathname === path) {
      return;
    }
    window.history.pushState({}, "", path);
    setRoute(getAppRoute(path));
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  function handleInternalNavigate(event: MouseEvent<HTMLAnchorElement>, path: string): void {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return;
    }
    event.preventDefault();
    navigate(path);
  }

  if (route.kind === "app") {
    return (
      <PoetryAppShell
        theme={theme}
        onToggleTheme={() => setTheme((current) => (current === "light" ? "dark" : "light"))}
        onNavigate={handleInternalNavigate}
      />
    );
  }

  if (route.kind === "poem") {
    return (
      <PoemPageView
        theme={theme}
        poemId={route.poemId}
        onToggleTheme={() => setTheme((current) => (current === "light" ? "dark" : "light"))}
        onNavigate={handleInternalNavigate}
      />
    );
  }

  return (
    <LandingView
      theme={theme}
      onToggleTheme={() => setTheme((current) => (current === "light" ? "dark" : "light"))}
      onNavigate={handleInternalNavigate}
    />
  );
}

export default App;
