"use client";

import { PipecatClient, type TransportState } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";
import { WebSocketTransport } from "@pipecat-ai/websocket-transport";
import { useCallback, useEffect, useRef, useState } from "react";

import { getCustomerId, newSessionId } from "./format";
import type {
  Cart,
  CheckoutReady,
  ProductCard,
  RecipientProfile,
  ServerEvent,
  TranscriptLine,
  UpcomingOccasion,
} from "./types";

export type BotActivity = "idle" | "listening" | "user-speaking" | "thinking" | "bot-speaking";

type Ready = {
  ready: boolean;
  transport?: "smallwebrtc" | "websocket";
  session_limit_secs?: number | null;
  busy?: boolean;
};

/** Resolves once the backend has loaded its models (about a minute after it starts), or if it can't be reached.
 *  The answer also says which transport this deployment speaks. */
async function waitForBackend(): Promise<Ready> {
  for (;;) {
    const res = await fetch("/api/ready").catch(() => null);
    if (!res?.ok) return { ready: false };
    const body = (await res.json()) as Ready;
    if (body.ready) return body;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}

/** The hosted demo streams audio over a websocket; local development uses peer-to-peer WebRTC. */
function buildTransport(kind: Ready["transport"]) {
  return kind === "websocket"
    ? new WebSocketTransport()
    : new SmallWebRTCTransport({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] });
}

export interface Latency {
  stt_ms?: number;
  llm_ttfb_ms?: number;
  tts_ttfb_ms?: number;
  total_ms?: number;
}

/** Owns the Pipecat client, the transcript and all UI state driven by the agent's tool events. */
export function useGiftVoice() {
  const clientRef = useRef<PipecatClient | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const lineId = useRef(0);
  const idsRef = useRef<{ sessionId: string; customerId: string } | null>(null);
  const [transportState, setTransportState] = useState<TransportState>("disconnected");
  const [warming, setWarming] = useState(false);
  const [activity, setActivity] = useState<BotActivity>("idle");
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [shelf, setShelf] = useState<{ title: string; products: ProductCard[] } | null>(null);
  const [cart, setCart] = useState<Cart | null>(null);
  const [profiles, setProfiles] = useState<RecipientProfile[]>([]);
  const [upcoming, setUpcoming] = useState<UpcomingOccasion[]>([]);
  const [checkout, setCheckout] = useState<CheckoutReady | null>(null);
  const [language, setLanguage] = useState<"en" | "ur">("en");
  const [mood, setMood] = useState<string | null>(null);
  const [stage, setStage] = useState<string>("gift_concierge");
  const [latency, setLatency] = useState<Latency | null>(null);
  const [error, setError] = useState<string | null>(null);

  const addLine = useCallback((role: TranscriptLine["role"], text: string, final = true) => {
    setTranscript((lines) => [...lines, { id: ++lineId.current, role, text, final }]);
  }, []);

  const refreshProfiles = useCallback(async (customerId: string) => {
    const res = await fetch(`/api/profiles/${customerId}`);
    if (res.ok) {
      const data = await res.json();
      setProfiles(data.profiles);
      setUpcoming(data.upcoming);
    }
  }, []);

  // Ids live in localStorage, so they are created lazily on the client rather than during render.
  const getIds = useCallback(() => {
    idsRef.current ??= { sessionId: newSessionId(), customerId: getCustomerId() };
    return idsRef.current;
  }, []);

  useEffect(() => {
    refreshProfiles(getIds().customerId).catch(() => undefined);
  }, [getIds, refreshProfiles]);

  const handleServerEvent = useCallback(
    (event: ServerEvent) => {
      switch (event.type) {
        case "show_products":
          setShelf(event.payload);
          break;
        case "cart_updated":
          setCart(event.payload);
          break;
        case "checkout_ready":
          setCheckout(event.payload);
          break;
        case "profiles_updated":
          setProfiles(event.payload.profiles);
          setUpcoming(event.payload.upcoming);
          break;
        case "ticket_created":
          addLine("system", `Support ticket ${event.payload.ticket_id} created. ${event.payload.message}`);
          break;
        case "language_changed":
          setLanguage(event.payload.language);
          break;
        case "mood":
          setMood(event.payload.mood);
          break;
        case "agent_stage":
          setStage(event.payload.stage);
          break;
        case "latency":
          setLatency(event.payload);
          break;
      }
    },
    [addLine],
  );

  const createClient = useCallback((kind: Ready["transport"]) => {
    const client = new PipecatClient({
      transport: buildTransport(kind),
      enableMic: true,
      enableCam: false,
      callbacks: {
        onTransportStateChanged: (state) => {
          setTransportState(state);
          if (state === "ready") setActivity("listening");
          if (state === "disconnected" || state === "error") setActivity("idle");
        },
        onTrackStarted: (track, participant) => {
          if (participant?.local || track.kind !== "audio") return;
          if (!audioRef.current) audioRef.current = new Audio();
          audioRef.current.srcObject = new MediaStream([track]);
          audioRef.current.play().catch(() => setError("Click anywhere to allow audio playback."));
        },
        onUserStartedSpeaking: () => setActivity("user-speaking"),
        onUserStoppedSpeaking: () => setActivity("thinking"),
        onBotStartedSpeaking: () => setActivity("bot-speaking"),
        onBotStoppedSpeaking: () => setActivity("listening"),
        onUserTranscript: (data) => {
          setTranscript((lines) => {
            const last = lines[lines.length - 1];
            if (last && last.role === "user" && !last.final) {
              return [...lines.slice(0, -1), { ...last, text: data.text, final: data.final }];
            }
            return [...lines, { id: ++lineId.current, role: "user", text: data.text, final: data.final }];
          });
        },
        onBotOutput: (data) => {
          if (data.aggregated_by === "word" || !data.text.trim()) return;
          // Speakable sentences arrive twice: announced before synthesis ("new") and again once
          // spoken ("completed"). Keep the spoken copy so interrupted text never shows.
          if (data.will_be_spoken && data.spoken_status && data.spoken_status !== "completed") return;
          setTranscript((lines) => {
            const last = lines[lines.length - 1];
            if (last && last.role === "bot") {
              return [...lines.slice(0, -1), { ...last, text: `${last.text} ${data.text.trim()}` }];
            }
            return [...lines, { id: ++lineId.current, role: "bot", text: data.text.trim(), final: true }];
          });
        },
        onServerMessage: (data) => {
          if (data && typeof data === "object" && "type" in data) handleServerEvent(data as ServerEvent);
        },
        onError: (message) => {
          const detail = (message.data as { message?: string } | undefined)?.message;
          setError(detail ?? "Something went wrong with the voice connection.");
        },
      },
    });
    return client;
  }, [handleServerEvent]);

  const connect = useCallback(async () => {
    const ids = getIds();
    setError(null);
    try {
      // A session opened while the backend is still loading models starts late and misses its greeting.
      setWarming(true);
      const backend = await waitForBackend().finally(() => setWarming(false));
      if (backend.busy) {
        // The shared demo runs on one free-tier key, so it only takes a couple of callers at once.
        setError("The live demo is busy right now - please try again in a minute.");
        return;
      }
      if (!clientRef.current) clientRef.current = createClient(backend.transport);
      if (backend.transport === "websocket") {
        // Both ends of the socket start the session: connecting is what launches the bot.
        const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const query = new URLSearchParams({ session_id: ids.sessionId, customer_id: ids.customerId });
        await clientRef.current.connect({ wsUrl: `${wsProtocol}//${window.location.host}/ws?${query}` });
      } else {
        // The backend has no /start step: the WebRTC offer itself starts the bot, so connect straight
        // to it (startBotAndConnect would first POST the bare request data to this endpoint).
        await clientRef.current.connect({
          webrtcRequestParams: {
            endpoint: "/api/offer",
            requestData: { session_id: ids.sessionId, customer_id: ids.customerId },
          },
        });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not reach the voice agent. Is the backend running?");
      setTransportState("error");
    }
  }, [createClient, getIds]);

  const disconnect = useCallback(async () => {
    await clientRef.current?.disconnect();
  }, []);

  useEffect(() => () => void clientRef.current?.disconnect(), []);

  const sendText = useCallback(
    async (text: string) => {
      if (!clientRef.current || transportState !== "ready") return;
      addLine("user", text);
      await clientRef.current.sendText(text);
    },
    [addLine, transportState],
  );

  const uploadPhoto = useCallback(
    async (file: File) => {
      const ids = getIds();
      const form = new FormData();
      form.append("session_id", ids.sessionId);
      form.append("file", file);
      const res = await fetch("/api/image-upload", { method: "POST", body: form });
      if (!res.ok) {
        setError("Could not upload that photo.");
        return;
      }
      addLine("system", `Photo uploaded: ${file.name}`);
      if (clientRef.current && transportState === "ready") {
        await clientRef.current.sendText("I just uploaded a photo. Find gifts that look similar to it.");
      }
    },
    [addLine, getIds, transportState],
  );

  return {
    transportState,
    warming,
    activity,
    transcript,
    shelf,
    cart,
    profiles,
    upcoming,
    checkout,
    language,
    mood,
    stage,
    latency,
    error,
    connect,
    disconnect,
    sendText,
    uploadPhoto,
    dismissCheckout: () => setCheckout(null),
    dismissError: () => setError(null),
  };
}
