import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

/** Refreshes cached queries whenever the server reports a change. */
export function useEventStream(enabled: boolean) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!enabled) return;
    let timer: number | undefined;
    const source = new EventSource("/api/system/events");

    const schedule = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        void queryClient.invalidateQueries();
      }, 400);
    };

    source.addEventListener("change", schedule);
    source.onerror = () => {
      // EventSource reconnects automatically; nothing to do.
    };

    return () => {
      window.clearTimeout(timer);
      source.removeEventListener("change", schedule);
      source.close();
    };
  }, [enabled, queryClient]);
}
