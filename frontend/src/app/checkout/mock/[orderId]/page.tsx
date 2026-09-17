"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";

import { formatDate, formatMoney } from "@/lib/format";
import type { Order } from "@/lib/types";

/** Stand-in for Stripe Checkout when no STRIPE_SECRET_KEY is configured. No payment details are collected. */
export default function MockCheckout({ params }: PageProps<"/checkout/mock/[orderId]">) {
  const { orderId } = use(params);
  const router = useRouter();
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [paying, setPaying] = useState(false);

  useEffect(() => {
    fetch(`/api/orders/${orderId}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("Order not found"))))
      .then(setOrder)
      .catch((e: Error) => setError(e.message));
  }, [orderId]);

  async function pay() {
    setPaying(true);
    const res = await fetch(`/api/orders/${orderId}/mock-pay`, { method: "POST" });
    if (res.ok) router.push(`/order/${orderId}`);
    else {
      setError("Payment simulation failed.");
      setPaying(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-md flex-1 px-4 py-10">
      <p className="text-xs font-medium uppercase tracking-widest text-gold">Test mode · no real payment</p>
      <h1 className="mt-1 font-display text-3xl">Checkout</h1>
      {error && <p className="mt-4 text-danger">{error}</p>}
      {order && (
        <div className="mt-6 rounded-2xl border border-border bg-surface p-5">
          <p className="text-sm text-muted">Order {order.id}</p>
          <ul className="mt-3 space-y-2 text-sm">
            {order.items.map((i) => (
              <li key={i.product_id} className="flex justify-between gap-3">
                <span>
                  {i.qty} × {i.name}
                </span>
                <span>{formatMoney(i.price * i.qty)}</span>
              </li>
            ))}
          </ul>
          <dl className="mt-4 space-y-1 border-t border-border pt-3 text-sm text-muted">
            <div className="flex justify-between"><dt>Gift wrap</dt><dd>{formatMoney(order.gift_fee)}</dd></div>
            <div className="flex justify-between"><dt>Shipping</dt><dd>{formatMoney(order.shipping_fee)}</dd></div>
            <div className="flex justify-between font-semibold text-foreground"><dt>Total</dt><dd>{formatMoney(order.total)}</dd></div>
          </dl>
          <p className="mt-3 text-sm">Expected arrival: {formatDate(order.eta)}</p>
          {order.status === "pending_payment" ? (
            <button
              type="button"
              onClick={pay}
              disabled={paying}
              className="mt-5 w-full rounded-full bg-accent py-2.5 font-medium text-accent-contrast disabled:opacity-60"
            >
              {paying ? "Processing…" : `Simulate payment of ${formatMoney(order.total)}`}
            </button>
          ) : (
            <Link href={`/order/${order.id}`} className="mt-5 block text-center text-accent underline">
              This order is already {order.status.replace("_", " ")}. View order
            </Link>
          )}
        </div>
      )}
    </main>
  );
}
