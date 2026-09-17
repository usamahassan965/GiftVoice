"use client";

import { useEffect, useRef, useState } from "react";

import type { TranscriptLine } from "@/lib/types";

interface Props {
  lines: TranscriptLine[];
  canType: boolean;
  onSend: (text: string) => void;
}

const URDU = /[؀-ۿ]/;

export function Transcript({ lines, canType, onSend }: Props) {
  const endRef = useRef<HTMLDivElement>(null);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [lines]);

  return (
    <section className="flex min-h-0 flex-1 flex-col rounded-2xl border border-border bg-surface">
      <div className="scrollbar-thin flex min-h-48 flex-1 flex-col gap-2 overflow-y-auto p-4">
        {lines.length === 0 && (
          <p className="m-auto max-w-64 text-center text-sm text-muted">
            Try: “A gift for my mom who loves gardening, under fifty dollars. Her birthday is Friday.”
          </p>
        )}
        {lines.map((line) =>
          line.role === "system" ? (
            <p key={line.id} className="self-center rounded-full bg-surface-muted px-3 py-1 text-xs text-muted">
              {line.text}
            </p>
          ) : (
            <p
              key={line.id}
              dir={URDU.test(line.text) ? "rtl" : "ltr"}
              className={`max-w-[85%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed ${
                line.role === "user"
                  ? "self-end rounded-br-sm bg-accent text-accent-contrast"
                  : "self-start rounded-bl-sm bg-surface-muted"
              } ${line.final ? "" : "opacity-60"}`}
            >
              {line.text}
            </p>
          ),
        )}
        <div ref={endRef} />
      </div>
      <form
        className="flex gap-2 border-t border-border p-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (!draft.trim()) return;
          onSend(draft.trim());
          setDraft("");
        }}
      >
        <label htmlFor="type-message" className="sr-only">
          Type a message
        </label>
        <input
          id="type-message"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={!canType}
          placeholder={canType ? "Or type a message…" : "Start the conversation to type"}
          className="min-w-0 flex-1 rounded-full border border-border bg-background px-4 py-2 text-sm outline-none focus:border-accent disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={!canType || !draft.trim()}
          className="rounded-full bg-accent px-4 py-2 text-sm font-medium text-accent-contrast disabled:opacity-40"
        >
          Send
        </button>
      </form>
    </section>
  );
}
