---
title: GiftVoice
emoji: 🎁
colorFrom: purple
colorTo: pink
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Real-time voice gift concierge - talk to it, it shops for you
---

# GiftVoice

Talk to Gigi, a real-time voice gift concierge: describe who the gift is for, hear two or three
grounded picks from a 214-product catalog, add gift wrap and a message card, and check out — all
by voice, in English or Urdu.

Click **Start talking**, allow the microphone, and say something like
*"I need a birthday gift for my mom, she loves gardening, under fifty dollars."*

The agent never invents a product: every recommendation comes from a tool call against the
catalog, and an order is only created after it reads the total back and hears a "yes".

**Demo limits:** this Space runs on free API tiers, so sessions are capped in length and only a
couple can run at once. If it says the demo is busy, try again in a minute. Payments are Stripe
test mode / a mock checkout — no real money and no card details are ever collected.

Source code, architecture notes and the local (WebRTC) setup:
**https://github.com/usamahassan965/GiftVoice**
