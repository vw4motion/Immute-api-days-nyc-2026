# Immute — Live Demo

**One API contract. Any model. Zero client changes.**

APIDays May 2026 — live CLI demo.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in your three API keys in .env
```

## Run

```bash
python immute.py
```

## What it demos

| Act | What happens |
|-----|-------------|
| 1 — Unified contract | Same `complete("default", prompt)` call routes to Anthropic, OpenAI, and Google in turn |
| 2 — Model swap | Registry switches from Sonnet → Haiku mid-demo. Client call never changes. |
| 3 — Fallback routing | Anthropic + OpenAI simulated as down. Google serves the request. Client sees 200 OK. |

## Structure

```
immute.py
├── REGISTRY        # logical name → provider + model (config, not code)
├── ADAPTERS        # one function per provider SDK
├── complete()      # the only function callers ever use
└── complete_with_fallback()  # routing + health-check simulation
```
