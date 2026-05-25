import { useEffect } from "react";

import { useGameStore } from "../store/gameStore";

export function useSSE(gameId: string | undefined, skipReset = false) {
  const addEvent = useGameStore((state) => state.addEvent);
  const reset = useGameStore((state) => state.reset);
  const setConnected = useGameStore((state) => state.setConnected);
  const setConnectionError = useGameStore((state) => state.setConnectionError);

  useEffect(() => {
    if (!gameId) {
      if (!skipReset) reset();
      return;
    }

    if (!skipReset) reset();
    const stream = new EventSource(`/api/events/${gameId}`);

    const handlers = [
      "phase_change",
      "speech",
      "vote_cast",
      "death",
      "game_over",
      "gm_announcement",
      "night_action",
      "seating",
      "sheriff_update",
      "agent_notes_update",
      "wolf_chat",
      "game_saved",
      "vote_result",
      "error",
    ] as const;

    const listeners = handlers.map((type) => {
      const listener = (event: MessageEvent) => {
        try {
          const data = event.data ? JSON.parse(event.data) : {};
          addEvent({ event: type, data });
          if (type === "error" && typeof data?.message === "string") {
            setConnectionError(data.message);
          }
        } catch {
          // Ignore malformed payloads and keep the stream alive.
        }
      };

      stream.addEventListener(type, listener as EventListener);
      return { type, listener };
    });

    stream.onopen = () => {
      setConnected(true);
      setConnectionError(null);
    };

    stream.onerror = () => {
      setConnected(false);
      if (stream.readyState === EventSource.CLOSED) {
        setConnectionError("实时连接已关闭。");
      }
    };

    return () => {
      listeners.forEach(({ type, listener }) => {
        stream.removeEventListener(type, listener as EventListener);
      });
      stream.close();
      setConnected(false);
    };
  }, [addEvent, gameId, reset, setConnected, setConnectionError, skipReset]);
}
