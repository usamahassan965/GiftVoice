# Running the demo for other people

The local setup runs the browser (Next.js on :3000) and the agent (FastAPI on :7860) separately and
streams audio peer-to-peer over WebRTC. Anywhere else you get one HTTPS port and no UDP, so the
shared demo differs in two ways:

| | Local | Shared (Colab / Docker) |
|---|---|---|
| Audio | SmallWebRTC, peer-to-peer | one websocket, PCM frames (`TRANSPORT=websocket`) |
| UI | `next dev`, proxying `/api` to the backend | static export served by FastAPI, same origin |
| Limits | none | `MAX_CONCURRENT_SESSIONS`, `SESSION_TIMEOUT_SECS` |

The browser asks `/api/ready` which transport this deployment speaks, so the same build works both
ways — nothing is hard-coded into the frontend.

## Colab notebook (free, no card, no account beyond Google)

[`colab/giftvoice_demo.ipynb`](colab/giftvoice_demo.ipynb) clones this repo, installs the
dependencies into an isolated env, builds the UI and starts the agent on Colab's free CPU, then
opens a [Cloudflare quick tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/)
so it has a public HTTPS address — browsers only hand over the microphone on HTTPS.

1. Open the notebook in Colab.
2. Put your own `GROQ_API_KEY` and `GOOGLE_API_KEY` in the *Secrets* panel (the key icon on the
   left) and switch on *Notebook access*. They stay in your Google account.
3. *Runtime -> Run all*. After about five minutes the last cell prints a
   `https://....trycloudflare.com` link.

The link lives as long as the notebook runs, and a new run gets a new address.

## Run the container locally

```bash
docker build -t giftvoice .
docker run -p 7860:7860 --env-file .env giftvoice
```

Then open http://localhost:7860. The image bakes in the seeded catalog (`data/catalog.zip`), the
exported UI and the search models; only the API keys come from the environment.

## Always-on hosting

The same image runs anywhere that takes a Dockerfile and one port — Google Cloud Run, Fly.io, a
small VPS. Set at least `GROQ_API_KEY` and `GOOGLE_API_KEY`; `TRANSPORT=websocket` and the session
limits already have defaults in the Dockerfile.

Hugging Face Spaces used to be the free option here, and
[`space_sync.sh`](space_sync.sh) plus [`space/README.md`](space/README.md) still push this repo to
one. Since July 2026 only *static* Spaces are free, though: hosting a Docker Space on free
cpu-basic hardware needs a PRO subscription.

A shared demo runs on one person's free API quota, so the container caps it at two concurrent
sessions of seven minutes each — change `MAX_CONCURRENT_SESSIONS` and `SESSION_TIMEOUT_SECS` to
taste.
