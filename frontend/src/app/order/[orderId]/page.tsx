"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, use, useEffect, useState } from "react";

import { formatDate, formatMoney, titleCase } from "@/lib/format";
import type { Order } from "@/lib/types";

export default function OrderPage({ params }: PageProps<"/order/[orderId]">) {
  const { orderId } = use(params);
  return (
    <Suspense>
      <OrderDetails orderId={orderId} />
    </Suspense>
  );
}

function OrderDetails({ orderId }: { orderId: string }) {
  const stripeSession = useSearchParams().get("session_id");
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      if (stripeSession) {
        await fetch(`/api/orders/${orderId}/verify-stripe?session_id=${encodeURIComponent(stripeSession)}`, {
          method: "POST",
        });
      }
      const res = await fetch(`/api/orders/${orderId}`);
      if (!res.ok) throw new Error("Order not found");
      setOrder(await res.json());
    };
    load().catch((e: Error) => setError(e.message));
  }, [orderId, stripeSession]);

  return (
    <main className="mx-auto w-full max-w-md flex-1 px-4 py-10">
      {error && <p className="text-danger">{error}</p>}
      {order && (
        <>
          <p className="text-4xl" aria-hidden>
            🎁
          </p>
          <h1 className="mt-2 font-display text-3xl">
            {order.status === "pending_payment" ? "Awaiting payment" : "Your gift is on its way"}
          </h1>
          <p className="mt-1 text-muted">
            Order {order.id} · {titleCase(order.status)} · arrives {formatDate(order.eta)}
          </p>
          <div className="mt-6 rounded-2xl border border-border bg-surface p-5 text-sm">
            <ul className="space-y-2">
              {order.items.map((i) => (
                <li key={i.product_id} className="flex justify-between gap-3">
                  <span>
                    {i.qty} × {i.name}
                  </span>
                  <span>{formatMoney(i.price * i.qty)}</span>
                </li>
              ))}
            </ul>
            {order.gift.message && <p className="mt-4 italic">“{order.gift.message}”</p>}
            {order.gift.recipient_name && (
              <p className="mt-2 text-muted">
                Shipping to {order.gift.recipient_name}, {order.gift.ship_address}, {order.gift.ship_city}
              </p>
            )}
            <p className="mt-4 border-t border-border pt-3 font-semibold">Total {formatMoney(order.total)}</p>
          </div>
          <p className="mt-6 text-sm text-muted">
            Ask Gigi “where is my order?” any time to track it.{" "}
            <Link href="/" className="text-accent underline">
              Back to Gigi
            </Link>
          </p>
        </>
      )}
    </main>
  );
}
