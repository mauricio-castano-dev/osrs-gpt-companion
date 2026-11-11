import { useEffect, useState } from "react";
export function useClock() {
  const [now, set] = useState(0);
  useEffect(() => {
    set(Date.now());
    const id = setInterval(() => set(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}
