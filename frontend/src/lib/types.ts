// Payload shapes emitted by backend/app/agent/tools.py and returned by the REST API.

export interface ProductCard {
  id: string;
  name: string;
  price: number;
  category: string;
  rating: number;
  review_count: number;
  in_stock: boolean;
  ship_days: number;
  image_url: string | null;
  image_credit: string | null;
  image_credit_url: string | null;
  description: string;
  position?: number;
  why?: string[];
  arrival?: string | null;
}

export interface GiftOptions {
  wrap: "classic" | "premium" | "eco" | null;
  message: string | null;
  hide_price: boolean;
  recipient_name: string | null;
  ship_address: string | null;
  ship_city: string | null;
  express: boolean;
}

export interface CartItem {
  product_id: string;
  name: string;
  price: number;
  qty: number;
  line_total: number;
  image_url: string | null;
  ship_days: number;
}

export interface Cart {
  items: CartItem[];
  item_count: number;
  subtotal: number;
  gift_fee: number;
  shipping_fee: number;
  total: number;
  gift_options: GiftOptions;
}

export interface RecipientProfile {
  id: string;
  name: string;
  relationship: string | null;
  interests: string[];
  notes: string | null;
  occasions: { type: string; date: string }[];
  past_gifts?: { product_id: string; name: string | null; occasion: string | null; date: string }[];
}

export interface UpcomingOccasion {
  recipient: string;
  occasion: string;
  date: string;
  days_left: number;
}

export interface CheckoutReady {
  order_id: string;
  total: number;
  eta: string;
  payment_url: string;
}

export interface Order {
  id: string;
  items: { product_id: string; name: string; price: number; qty: number }[];
  subtotal: number;
  gift_fee: number;
  shipping_fee: number;
  total: number;
  gift: GiftOptions;
  status: string;
  created_at: string;
  eta: string;
  payment_url: string | null;
}

export type ServerEvent =
  | { type: "show_products"; payload: { title: string; products: ProductCard[] } }
  | { type: "cart_updated"; payload: Cart }
  | { type: "checkout_ready"; payload: CheckoutReady }
  | { type: "profiles_updated"; payload: { profiles: RecipientProfile[]; upcoming: UpcomingOccasion[] } }
  | { type: "ticket_created"; payload: { ticket_id: string; message: string } }
  | { type: "language_changed"; payload: { language: "en" | "ur" } }
  | { type: "mood"; payload: { mood: string } }
  | { type: "agent_stage"; payload: { stage: string } }
  | { type: "latency"; payload: { stt_ms?: number; llm_ttfb_ms?: number; tts_ttfb_ms?: number; total_ms?: number } };

export interface TranscriptLine {
  id: number;
  role: "user" | "bot" | "system";
  text: string;
  final: boolean;
}
