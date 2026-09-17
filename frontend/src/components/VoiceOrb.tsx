"use client";

import type { TransportState } from "@pipecat-ai/client-js";

import type { BotActivity } from "@/lib/useGiftVoice";

const LABELS: Record<BotActivity, string> = {
  idle: "Tap to talk to Gigi",
  listening: "Listening…",
  "user-speaking": "Hearing you",
  thinking: "Thinking…",
  "bot-speaking": "Gigi is speaking",
};

interface Props {
  transportState: TransportState;
  warming: boolean;
  activity: BotActivity;
  onConnect: () => void;
  onDisconnect: () => void;
}

export function VoiceOrb({ transportState, warming, activity, onConnect, onDisconnect }: Props) {
  const connecting = warming || ["initializing", "initialized", "authenticating", "authenticated", "connecting", "connected"]
    .includes(transportState);
  const live = transportState === "ready";
  const label = warming ? "Gigi is warming up…" : connecting ? "Connecting…" : LABELS[activity];

  const ring =
    activity === "bot-speaking"
      ? "from-accent to-gold"
      : activity === "user-speaking"
        ? "from-success to-accent"
        : "from-accent/70 to-gold/70";

  return (
    <div className="flex flex-col items-center gap-3">
      <button
        type="button"
        onClick={live ? onDisconnect : onConnect}
        disabled={connecting}
        aria-label={live ? "End conversation" : "Start conversation"}
        className={`relative grid size-28 place-items-center rounded-full bg-gradient-to-br ${ring} shadow-lg shadow-accent/20 transition-transform focus-visible:outline-4 focus-visible:outline-offset-4 focus-visible:outline-accent disabled:opacity-70`}
        style={{
          animation:
            activity === "bot-speaking" || activity === "user-speaking" || connecting
              ? "orb-pulse 1.2s ease-in-out infinite"
              : undefined,
        }}
      >
        <span className="grid size-24 place-items-center rounded-full bg-surface">
          {live ? (
            <svg viewBox="0 0 24 24" className="size-9 fill-accent" aria-hidden>
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" className="size-10 fill-accent" aria-hidden>
              <path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z" />
            </svg>
          )}
        </span>
      </button>
      <p className="text-sm font-medium text-muted" aria-live="polite">
        {label}
      </p>
    </div>
  );
}
