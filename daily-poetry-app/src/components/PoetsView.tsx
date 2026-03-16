import { useEffect, useState } from "react";
import { fetchPoets } from "../lib/api";
import type { PoetItem } from "../types/poetry";

function getInitial(name: string): string {
  return name.trim().charAt(0).toUpperCase();
}

function getSectionLetter(name: string): string {
  return name.trim().charAt(0).toUpperCase();
}

function groupAlphabetically(poets: PoetItem[]): Array<{ letter: string; poets: PoetItem[] }> {
  const map = new Map<string, PoetItem[]>();

  for (const poet of poets) {
    const letter = getSectionLetter(poet.name);
    const group = map.get(letter) ?? [];
    group.push(poet);
    map.set(letter, group);
  }

  return Array.from(map.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([letter, group]) => ({ letter, poets: group }));
}

type PoetCardProps = {
  poet: PoetItem;
  isExpanded: boolean;
  onToggle: () => void;
};

function PoetCard({ poet, isExpanded, onToggle }: PoetCardProps) {
  const bio =
    typeof poet.bio === "string" && poet.bio.trim()
      ? poet.bio.trim()
      : "No biography available.";

  return (
    <li className={isExpanded ? "poet-card poet-card-expanded" : "poet-card"}>
      <button
        className="poet-card-thumb"
        type="button"
        aria-expanded={isExpanded}
        aria-label={`${poet.name} — ${isExpanded ? "collapse" : "expand"} biography`}
        onClick={onToggle}
      >
        {poet.image_url ? (
          <img
            className="poet-card-image"
            src={poet.image_url}
            alt={poet.name}
            loading="lazy"
          />
        ) : (
          <div className="poet-card-initial" aria-hidden="true">
            {getInitial(poet.name)}
          </div>
        )}
        <div className="poet-card-overlay" aria-hidden="true">
          <span className="poet-card-name">{poet.name}</span>
        </div>
      </button>

      {isExpanded ? (
        <div className="poet-bio-panel" role="region" aria-label={`${poet.name} biography`}>
          <p className="poet-bio-name">{poet.name}</p>
          <p className="poet-bio-text">{bio}</p>
        </div>
      ) : null}
    </li>
  );
}

export function PoetsView() {
  const [poets, setPoets] = useState<PoetItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function load() {
      setLoading(true);
      setError(null);

      try {
        const data = await fetchPoets();
        if (active) {
          setPoets(data);
        }
      } catch (loadError) {
        if (active) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load poets");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      active = false;
    };
  }, []);

  function handleToggle(id: string): void {
    setExpandedId((current) => (current === id ? null : id));
  }

  const groups = groupAlphabetically(poets);

  return (
    <section className="poets-view" aria-label="Poets">
      <header className="poets-header">
        <h2 className="poets-title">Poets</h2>
        <p className="poets-subtitle">The voices behind the verse</p>
      </header>

      {loading ? (
        <p className="status">Loading poets...</p>
      ) : null}

      {error ? (
        <p className="status status-error">{error}</p>
      ) : null}

      {!loading && !error && poets.length === 0 ? (
        <p className="empty-state">No poets found.</p>
      ) : null}

      {!loading && !error && groups.length > 0 ? (
        <div className="poets-alphabet">
          {groups.map(({ letter, poets: group }) => (
            <div key={letter} className="poets-section">
              <p className="poets-section-letter" aria-label={`Section ${letter}`}>{letter}</p>
              <ul className="poets-grid" aria-label={`Poets starting with ${letter}`}>
                {group.map((poet) => (
                  <PoetCard
                    key={poet.id}
                    poet={poet}
                    isExpanded={expandedId === poet.id}
                    onToggle={() => handleToggle(poet.id)}
                  />
                ))}
              </ul>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}
