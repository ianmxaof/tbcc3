# Hcnsec gateway vs HuggingFace uncensored models

**Wallet:** [api.hcnsec.cn usage logs](https://api.hcnsec.cn/usage-logs/common)

## What “Model Square” is

Hcnsec’s **Model Square** is their **menu of models the gateway will run and bill**. It is not Hugging Face Hub. If a model is not on that menu (~21 frontier / guarded models in your account), their API key **cannot** load it — no custom script can redirect those credits to an arbitrary `org/model` on huggingface.co.

## Hard limit (important)

| Want | Possible with hcnsec ¥/$ balance? |
|------|-----------------------------------|
| Call `step-3.5-flash` etc. they list | Yes |
| Point secretary at a HF model you like that is **not** on Model Square | **No** — credits stay locked to their roster |
| “Custom script so HF runs off hcnsec credits” | **Not possible** — different product, different GPUs |

## Ways to actually run uncensored HF-class models for secretary / spicy

1. **Host yourself (true HF weights)** — download the GGUF/safetensors you already trust; serve OpenAI-compatible API with Ollama / vLLM / llama.cpp; set secretary `base_url` to that host. Cost = your GPU/VPS, not hcnsec.
2. **Aggregator that already hosts uncensored HF forks** — OpenRouter / Featherless / Venice (TBCC already has presets + `tbcc_uncensored_chat.py`). You pay *their* wallet; pick slugs like Hermes / Dolphin / MythoMax.
3. **Hugging Face Inference** — `HF_TOKEN` + Inference Providers / Endpoints for models they allow. Separate bill from hcnsec; many adult models are restricted or unavailable on HF Inference.
4. **Keep hcnsec for SFW/ops FAQ** — use guarded models for secretary drafts when you want cheap Chinese-gateway tokens; route spicy companion to (1) or (2).

## Env today

```env
# Hcnsec (guarded roster only)
TBCC_LLM_BASE_URL=https://api.hcnsec.cn/v1
TBCC_LLM_API_KEY=sk-...
TBCC_LLM_MODEL=step-3.5-flash

# Uncensored path (pick one host — not hcnsec)
# TBCC_OPENROUTER_API_KEY=...
# or local: TBCC_LLM_BASE_URL=http://127.0.0.1:11434/v1  TBCC_LLM_MODEL=<ollama-tag>
```

## Operator next decision

Name the HF model ids you already use (e.g. `cognitivecomputations/dolphin-…`). Then choose host path **1 (local)** or **2 (OpenRouter/Featherless/Venice)** — not hcnsec Model Square.
