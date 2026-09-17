/* eslint-disable @next/next/no-img-element -- product photos are served by the FastAPI backend */
"use client";

import { formatMoney, titleCase } from "@/lib/format";
import type { Cart, CheckoutReady } from "@/lib/types";

interface Props {
  cart: Cart | null;
  checkout: CheckoutReady | null;
}

export function CartPanel({ cart, checkout }: Props) {
  const gift = cart?.gift_options;
  const empty = !cart || cart.items.length === 0;

  return (
    <section className="rounded-2xl border border-border bg-surface p-4">
      <h2 className="flex items-center justify-between font-display text-lg">
        Gift bag
        {!empty && <span className="font-sans text-sm text-muted">{cart.item_count} item(s)</span>}
      </h2>

      {checkout && (
        <div className="mt-3 rounded-xl bg-accent-soft p-3 text-sm">
          <p className="font-medium">Order {checkout.order_id} is ready to pay</p>
          <p className="text-muted">Total {formatMoney(checkout.total)}</p>
          <a
            href={checkout.payment_url}
            target="_blank"
            rel="noreferrer"
            className="mt-2 inline-block rounded-full bg-accent px-4 py-1.5 font-medium text-accent-contrast"
          >
            Open payment page
          </a>
        </div>
      )}

      {empty ? (
        <p className="mt-2 text-sm text-muted">{checkout ? "" : "Nothing in the bag yet."}</p>
      ) : (
        <>
          <ul className="mt-3 flex flex-col gap-3">
            {cart.items.map((item) => (
              <li key={item.product_id} className="flex items-center gap-3">
                {item.image_url && (
                  <img src={item.image_url} alt="" className="size-12 rounded-lg object-cover" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{item.name}</p>
                  <p className="text-xs text-muted">
                    {item.qty} × {formatMoney(item.price)}
                  </p>
                </div>
                <span className="text-sm">{formatMoney(item.line_total)}</span>
              </li>
            ))}
          </ul>

          {gift && (gift.wrap || gift.message || gift.recipient_name || gift.hide_price || gift.express) && (
            <div className="mt-4 space-y-1 rounded-xl bg-surface-muted p-3 text-xs">
              {gift.wrap && <p>🎀 {titleCase(gift.wrap)} gift wrap</p>}
              {gift.message && <p className="italic">“{gift.message}”</p>}
              {gift.hide_price && <p>Gift receipt, prices hidden</p>}
              {gift.express && <p>Express shipping</p>}
              {gift.recipient_name && (
                <p className="text-muted">
                  To {gift.recipient_name}
                  {gift.ship_address ? `, ${gift.ship_address}` : ""}
                  {gift.ship_city ? `, ${gift.ship_city}` : ""}
                </p>
              )}
            </div>
          )}

          <dl className="mt-4 space-y-1 border-t border-border pt-3 text-sm">
            <Row label="Subtotal" value={cart.subtotal} />
            {cart.gift_fee > 0 && <Row label="Gift wrap" value={cart.gift_fee} />}
            <Row label="Shipping" value={cart.shipping_fee} />
            <div className="flex justify-between pt-1 font-semibold">
              <dt>Total</dt>
              <dd>{formatMoney(cart.total)}</dd>
            </div>
          </dl>
        </>
      )}
    </section>
  );
}

function Row({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex justify-between text-muted">
      <dt>{label}</dt>
      <dd>{value === 0 ? "Free" : formatMoney(value)}</dd>
    </div>
  );
}
