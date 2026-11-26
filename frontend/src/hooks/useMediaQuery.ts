import { useEffect, useState } from "react";

/** Phone-sized screens: the metric table becomes a per-asset list, charts get tighter margins. */
export const COMPACT_QUERY = "(max-width: 640px)";

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = () => setMatches(mq.matches);
    onChange();
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}
