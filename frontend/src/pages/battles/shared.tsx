import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { TypeBadge } from "../../components/pokemon";
import { Input } from "../../components/ui";
import { api } from "../../lib/api";

export interface SpeciesOption {
  key: string;
  name: string;
  dex: number;
  types: string[];
  class: string | null;
}

/** Search box for choosing a raid boss or an opponent from the Game Data. */
export function SpeciesPicker({ onPick, placeholder }: { onPick: (option: SpeciesOption) => void; placeholder: string }) {
  const [text, setText] = useState("");
  const query = useQuery({
    queryKey: ["species-search", text],
    queryFn: () => api.get<SpeciesOption[]>("/api/v1/battles/species", { q: text }),
    enabled: text.trim().length >= 2,
  });
  return (
    <div className="relative">
      <Input value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} aria-label={placeholder} />
      {text.trim().length >= 2 && (query.data?.length ?? 0) > 0 && (
        <ul className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-lg border border-line bg-surface shadow-lg">
          {query.data?.map((option) => (
            <li key={option.key}>
              <button
                className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-surface-3"
                onClick={() => {
                  onPick(option);
                  setText("");
                }}
              >
                <span>
                  #{option.dex} {option.name}
                </span>
                <span className="flex gap-1">
                  {option.types.map((t) => (
                    <TypeBadge key={t} type={t} />
                  ))}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
