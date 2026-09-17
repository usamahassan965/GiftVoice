const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export function formatMoney(value: number): string {
  return money.format(value);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(`${iso.slice(0, 10)}T12:00:00`);
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

export function titleCase(s: string): string {
  return s.replace(/[_-]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Stable per-browser shopper id so recipient memory survives page reloads. */
export function getCustomerId(): string {
  const key = "giftvoice.customer_id";
  let id = localStorage.getItem(key);
  if (!id) {
    id = `cust-${crypto.randomUUID().slice(0, 8)}`;
    localStorage.setItem(key, id);
  }
  return id;
}

export function newSessionId(): string {
  return `sess-${crypto.randomUUID().slice(0, 12)}`;
}
