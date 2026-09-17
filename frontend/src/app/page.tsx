"use client";

import { useRef } from "react";

import { CartPanel } from "@/components/CartPanel";
import { ProductShelf } from "@/components/ProductShelf";
import { ProfilesPanel } from "@/components/ProfilesPanel";
import { Transcript } from "@/components/Transcript";
import { VoiceOrb } from "@/components/VoiceOrb";
import { titleCase } from "@/lib/format";
import { useGiftVoice } from "@/lib/useGiftVoice";

const STAGES: Record<string, string> = {
  gift_concierge: "Gift concierge",
  checkout: "Checkout",
  after_sales: "Orders & returns",
};

export default function Home() {
  const voice = useGiftVoice();
  const fileRef = useRef<HTMLInputElement>(null);
  const live = voice.transportState === "ready";

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-4 py-6 lg:px-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl tracking-tight">
            Gift<span className="text-accent">Voice</span>
          </h1>
          <p className="text-sm text-muted">Talk to Gigi. Find it, wrap it, get it there on time.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {live && (
            <span className="rounded-full border border-border bg-surface px-3 py-1">
              {STAGES[voice.stage] ?? titleCase(voice.stage)}
            </span>
          )}
          <span className="rounded-full border border-border bg-surface px-3 py-1">
            {voice.language === "ur" ? "اردو" : "English"}
          </span>
          {voice.mood && voice.mood !== "calm" && (
            <span className="rounded-full border border-border bg-surface px-3 py-1">Tone: {voice.mood}</span>
          )}
          {voice.latency?.total_ms !== undefined && (
            <span
              className="rounded-full border border-border bg-surface px-3 py-1 tabular-nums"
              title={`STT ${voice.latency.stt_ms ?? "–"} ms · LLM first token ${voice.latency.llm_ttfb_ms ?? "–"} ms · TTS first audio ${voice.latency.tts_ttfb_ms ?? "–"} ms`}
            >
              Reply in {(voice.latency.total_ms / 1000).toFixed(1)}s
            </span>
          )}
        </div>
      </header>

      {voice.error && (
        <div role="alert" className="flex items-start justify-between gap-3 rounded-xl border border-danger/40 bg-danger/10 px-4 py-3 text-sm">
          <span>{voice.error}</span>
          <button type="button" onClick={voice.dismissError} className="font-medium underline">
            Dismiss
          </button>
        </div>
      )}

      <div className="grid flex-1 gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex min-w-0 flex-col gap-6">
          <ProductShelf shelf={voice.shelf} />
          <div className="grid gap-6 md:grid-cols-[220px_minmax(0,1fr)]">
            <div className="flex flex-col items-center gap-4 rounded-2xl border border-border bg-surface p-5">
              <VoiceOrb
                transportState={voice.transportState}
                warming={voice.warming}
                activity={voice.activity}
                onConnect={voice.connect}
                onDisconnect={voice.disconnect}
              />
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) voice.uploadPhoto(file);
                  e.target.value = "";
                }}
              />
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                disabled={!live}
                className="rounded-full border border-border px-4 py-1.5 text-sm disabled:opacity-40"
              >
                Search by photo
              </button>
            </div>
            <Transcript lines={voice.transcript} canType={live} onSend={voice.sendText} />
          </div>
        </div>

        <aside className="flex flex-col gap-6 lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:self-start lg:overflow-y-auto">
          <CartPanel cart={voice.cart} checkout={voice.checkout} />
          <ProfilesPanel profiles={voice.profiles} upcoming={voice.upcoming} />
        </aside>
      </div>
    </main>
  );
}
