import { useState } from "react";
import type { DailyPoemResponse } from "../types/poetry";
import { formatIsoDate } from "../lib/date";

type TodayViewProps = {
  daily: DailyPoemResponse;
  isFavourite: boolean;
  theme: "light" | "dark";
  favouriteSyncing: boolean;
  onToggleFavourite: () => void;
  showActualDate?: boolean;
};

export function TodayView({
  daily,
  isFavourite,
  theme,
  favouriteSyncing,
  onToggleFavourite,
  showActualDate = false,
}: TodayViewProps) {
  const topLogoSrc = theme === "dark" ? "/dailypoetry-light.png" : "/dailypoetry-dark.png";
  const [shareState, setShareState] = useState<"idle" | "copied">("idle");
  const [isBioExpanded, setIsBioExpanded] = useState(false);
  const dateLabel = showActualDate ? formatIsoDate(daily.date, "long") : "Today";
  const authorBio =
    typeof daily.author.bio_short === "string" && daily.author.bio_short.trim()
      ? daily.author.bio_short.trim()
      : "Author bio coming soon.";
  const canExpandBio = authorBio.length > 140;
  const displayedBio = canExpandBio && !isBioExpanded ? `${authorBio.slice(0, 140).trimEnd()}...` : authorBio;

  async function handleShare() {
    const text = `${daily.poem.title}\nby ${daily.author.name}\n\n${daily.poem.text}`;
    const sharePayload = {
      title: `${daily.poem.title} • daily-poetry`,
      text,
      url: window.location.href,
    };

    try {
      if (typeof navigator.share === "function") {
        await navigator.share(sharePayload);
        return;
      }

      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(`${text}\n\n${window.location.href}`);
        setShareState("copied");
        window.setTimeout(() => setShareState("idle"), 1800);
      }
    } catch {
      // Ignore share cancellation/errors to avoid noisy UI in normal use.
    }
  }

  return (
    <>
      <div className="top-logo-wrap">
        <img className="top-logo" src={topLogoSrc} alt="daily-poetry" />
      </div>
      <section className="panel">
        <p className="date-label">{dateLabel}</p>

        <div className="poem-card-wrap">
          <article className="poem-card">
            <h1 className="poem-title">{daily.poem.title}</h1>
            <pre className="poem-text">{daily.poem.text}</pre>
          </article>

          <div className="poem-actions" aria-label="Poem actions">
            {shareState === "copied" ? (
              <span className="share-feedback" role="status" aria-live="polite">
                Copied
              </span>
            ) : null}
            <button
              className="share-button"
              type="button"
              aria-label={shareState === "copied" ? "Copied poem link and text" : "Share poem"}
              title={shareState === "copied" ? "Copied" : "Share poem"}
              onClick={() => void handleShare()}
            >
              <svg className="share-icon" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M18 16a3 3 0 0 0-2.4 1.2l-6.7-3.35a3.1 3.1 0 0 0 0-1.7l6.7-3.35A3 3 0 1 0 15 7a3.2 3.2 0 0 0 .04.49L8.3 10.86a3 3 0 1 0 0 2.28l6.74 3.37A3 3 0 1 0 18 16z" />
              </svg>
            </button>

            <button
              className={isFavourite ? "heart-button heart-button-active" : "heart-button"}
              type="button"
              aria-label={isFavourite ? "Remove favourite" : "Add favourite"}
              title={isFavourite ? "Remove favourite" : "Add favourite"}
              onClick={onToggleFavourite}
              disabled={favouriteSyncing}
            >
              {favouriteSyncing ? (
                "..."
              ) : (
                <svg className="heart-icon" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M12.1 21.35 10.55 19.95C5.4 15.3 2 12.25 2 8.5 2 5.45 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.45 22 8.5c0 3.75-3.4 6.8-8.55 11.45z" />
                </svg>
              )}
            </button>
          </div>
        </div>

        <footer className="author-panel">
          <div className="author-block">
            {daily.author.image_url ? (
              <img className="author-image" src={daily.author.image_url} alt={daily.author.name} />
            ) : null}
            <div>
              <p className="author-name">{daily.author.name}</p>
              {canExpandBio ? (
                <button
                  className="author-bio-toggle"
                  type="button"
                  aria-expanded={isBioExpanded}
                  onClick={() => setIsBioExpanded((current) => !current)}
                >
                  {displayedBio}
                </button>
              ) : (
                <p className="author-bio">{authorBio}</p>
              )}
            </div>
          </div>
        </footer>
      </section>
    </>
  );
}
