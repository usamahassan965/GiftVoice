/* eslint-disable @next/next/no-img-element -- product photos are served by the FastAPI backend */
"use client";

import { formatDate, formatMoney, titleCase } from "@/lib/format";
import type { ProductCard } from "@/lib/types";

interface Props {
  shelf: { title: string; products: ProductCard[] } | null;
}

export function ProductShelf({ shelf }: Props) {
  if (!shelf || shelf.products.length === 0) {
    return (
      <section className="grid min-h-64 place-items-center rounded-2xl border border-dashed border-border p-8 text-center">
        <div className="max-w-sm">
          <p className="font-display text-2xl">Gift ideas will appear here</p>
          <p className="mt-2 text-sm text-muted">
            Tell Gigi who you&apos;re shopping for. Say “the second one” to pick from the cards.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section aria-label={shelf.title}>
      <h2 className="mb-3 font-display text-xl">{shelf.title}</h2>
      <ol className="scrollbar-thin -mx-1 flex snap-x gap-4 overflow-x-auto px-1 pb-3">
        {shelf.products.map((p) => (
          <li key={p.id} className="w-60 shrink-0 snap-start">
            <article className="flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-surface">
              <div className="relative aspect-square bg-surface-muted">
                {p.image_url && (
                  <img src={p.image_url} alt={p.name} loading="lazy" className="size-full object-cover" />
                )}
                <span className="absolute left-2 top-2 grid size-8 place-items-center rounded-full bg-accent text-sm font-semibold text-accent-contrast shadow">
                  {p.position}
                </span>
                {!p.in_stock && (
                  <span className="absolute right-2 top-2 rounded-full bg-danger px-2 py-0.5 text-xs text-white">
                    Sold out
                  </span>
                )}
                {p.image_credit && (
                  <a
                    href={p.image_credit_url ?? undefined}
                    target="_blank"
                    rel="noreferrer"
                    className="absolute bottom-1 right-1 rounded bg-black/55 px-1.5 py-0.5 text-[10px] text-white"
                  >
                    Photo: {p.image_credit}
                  </a>
                )}
              </div>
              <div className="flex flex-1 flex-col gap-1.5 p-3">
                <p className="text-xs uppercase tracking-wide text-muted">{titleCase(p.category)}</p>
                <h3 className="line-clamp-2 font-medium leading-snug">{p.name}</h3>
                <div className="flex items-center justify-between text-sm">
                  <span className="font-semibold">{formatMoney(p.price)}</span>
                  <span className="text-muted">
                    <span className="text-gold" aria-hidden>
                      ★
                    </span>{" "}
                    {p.rating.toFixed(1)} ({p.review_count})
                  </span>
                </div>
                {p.why && p.why.length > 0 && (
                  <ul className="mt-1 flex flex-wrap gap-1">
                    {p.why.slice(0, 3).map((reason) => (
                      <li key={reason} className="rounded-full bg-accent-soft px-2 py-0.5 text-[11px] text-accent">
                        {reason}
                      </li>
                    ))}
                  </ul>
                )}
                <p className="mt-auto pt-1 text-xs text-muted">
                  {p.ship_days === 0 ? "Instant digital delivery" : p.arrival ? `Arrives ${formatDate(p.arrival)}` : ""}
                </p>
              </div>
            </article>
          </li>
        ))}
      </ol>
    </section>
  );
}
