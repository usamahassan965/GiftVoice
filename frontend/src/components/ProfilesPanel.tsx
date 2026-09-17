"use client";

import { formatDate, titleCase } from "@/lib/format";
import type { RecipientProfile, UpcomingOccasion } from "@/lib/types";

interface Props {
  profiles: RecipientProfile[];
  upcoming: UpcomingOccasion[];
}

export function ProfilesPanel({ profiles, upcoming }: Props) {
  return (
    <section className="rounded-2xl border border-border bg-surface p-4">
      <h2 className="font-display text-lg">People you gift</h2>

      {upcoming.length > 0 && (
        <ul className="mt-3 space-y-1">
          {upcoming.slice(0, 3).map((o) => (
            <li key={`${o.recipient}-${o.occasion}`} className="rounded-lg bg-accent-soft px-3 py-1.5 text-xs text-accent">
              {o.recipient}&apos;s {titleCase(o.occasion)} · {formatDate(o.date)} ({o.days_left} days)
            </li>
          ))}
        </ul>
      )}

      {profiles.length === 0 ? (
        <p className="mt-2 text-sm text-muted">Gigi can remember who you shop for, with your permission.</p>
      ) : (
        <ul className="mt-3 divide-y divide-border">
          {profiles.map((p) => (
            <li key={p.id} className="py-2">
              <p className="text-sm font-medium">
                {p.name}
                {p.relationship && <span className="font-normal text-muted"> · {titleCase(p.relationship)}</span>}
              </p>
              {p.interests.length > 0 && <p className="text-xs text-muted">Loves {p.interests.join(", ")}</p>}
              {p.past_gifts && p.past_gifts.length > 0 && (
                <p className="text-xs text-muted">
                  Past gifts: {p.past_gifts.map((g) => g.name ?? g.product_id).join(", ")}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
