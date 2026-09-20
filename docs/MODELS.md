# Model reference: OpenAI and Claude

A side-by-side of the models you can point this Action at, as of **2026-09-20**. It exists so
you can compare options when choosing `openai_model` or `anthropic_model` without opening a
dozen provider pages.

## ⚠️ Important disclaimer: read this first

> **This page is provided for convenience only. Do not rely on it for pricing, budgeting, or
> purchasing decisions.**
>
> - **The figures may be wrong for you.** They were gathered on **2026-09-20** from provider
>   documentation, including pages viewed from a **personal account**, and may not reflect the
>   prices, limits, or model availability that apply to **your** account, tier, region, or
>   contract.
> - **Your costs may differ.** Real cost depends on your usage tier, data-residency or regional
>   surcharges, batch, flex, or fast processing, promotional or negotiated rates, taxes, and
>   how many tokens your pull requests actually use.
> - **It goes out of date.** Providers change prices, add models, and retire them, often with
>   little notice. Nothing here is updated automatically.
> - **It is not a quote, a guarantee, or an endorsement.** The providers' own pages are the only
>   authoritative source (see [Sources](#sources)). Always check them before you rely on a number.
> - **Being listed here does not mean the Action supports a model.** The Action's defaults are
>   `gpt-5-mini` and `claude-haiku-4-5-20251001`; other models are not guaranteed to work.
>
> This project is not affiliated with OpenAI or Anthropic. Product and model names belong to
> their owners.

All prices are US dollars per **million tokens** (MTok), for the standard tier, "input / output"
unless stated. Context, output, and cutoff figures are as the providers state them.

## OpenAI

### How it compares

| Model | Context | Max input | Max output | Price / MTok (in / out) | Thinking | Default effort | Knowledge cutoff |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GPT-6 Astra | 1.05M | 922K | 128K | $10 / $50 | Reasoning; effort `low` to `max` (no `none`) | Not stated on the model page | Apr 30, 2026 |
| GPT-5.6 Sol | 1.05M | 922K | 128K | $4 / $20 (promotional pricing through at least Nov 21, 2026) | Reasoning; effort `none` to `max` | `medium` | Feb 16, 2026 |
| GPT-5.6 Terra | 1.05M | 922K | 128K | $2 / $12 | Reasoning; effort `none` to `max` | `medium` | Feb 16, 2026 |
| GPT-5.6 Luna | 1.05M | 922K | 128K | $0.20 / $1.20 | Reasoning; effort `none` to `max` | `medium` | Feb 16, 2026 |
| GPT-5 Mini (the Action's default) | 400K | 272K | 128K | $0.25 / $2 | Reasoning | Not stated on the model page | May 31, 2024 |

The OpenAI pages used here give no latency rating. OpenAI offers Fast mode instead (about 2x the price for up to
2.5x the speed). All of these take text and images in and give text out.

### Model IDs, pricing detail and availability

| Model | Model ID | Cached input | Cache write | Batch / Flex (50% off) | Released | Retirement |
| --- | --- | --- | --- | --- | --- | --- |
| GPT-6 Astra | `gpt-6-astra` | $1 | $12.50 | $5 / $25 | Sep 3, 2026 | None announced |
| GPT-5.6 Sol | `gpt-5.6-sol` (alias `gpt-5.6`) | $0.40 | $5 | $2 / $10 | Jul 9, 2026 | None announced |
| GPT-5.6 Terra | `gpt-5.6-terra` | $0.20 | $2.50 | $1 / $6 | Jul 9, 2026 | None announced |
| GPT-5.6 Luna | `gpt-5.6-luna` | $0.02 | $0.25 | $0.10 / $0.60 | Jul 9, 2026 | None announced |
| GPT-5 Mini | `gpt-5-mini` (snapshot `gpt-5-mini-2025-08-07`) | $0.025 | Not listed | Not listed | Aug 2025 (snapshot date) | Snapshot listed for removal on Dec 11, 2026 |

- Prompts over 272K input tokens are priced at 2x input and 1.5x output for the whole request
  (GPT-6 Astra and the GPT-5.6 models).
- Cache writes are billed at 1.25x the uncached input rate.
- Regional processing (data residency) endpoints carry a 10% uplift for eligible models released
  on or after March 5, 2026.
- OpenAI describes Sol, Terra and Luna as roughly the standard, mini and nano tiers of earlier
  GPT-5 families.
- OpenAI states that GPT-6 Astra does not support custom `temperature`, `top_p` or log
  probabilities. The Action treats `gpt-6*` models like the other reasoning models, so it never
  sends `temperature` to them and uses `max_completion_tokens`.

## Claude (Anthropic)

### How it compares

| Model | Context | Max output | Price / MTok (in / out) | Latency | Thinking | Default effort | Knowledge cutoff |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Claude Fable 5.1 | 1M | 128K | $10 / $50 | Slower | Adaptive (always on) | `high` | Jun 2026 |
| Claude Opus 5 | 1M | 128K | $5 / $25 | Moderate | Adaptive | `high` | May 2026 |
| Claude Sonnet 5 | 1M | 128K | $2 / $10 | Fast | Adaptive | `high` | Jan 2026 |
| Claude Haiku 4.5 (the Action's default) | 200K | 64K | $1 / $5 | Fastest | Extended | Not supported | Feb 2025 |

All of these take text and images in and give text out. Only the comparison row was captured for
Claude Fable 5.1, so it has no detail row below.

### Model IDs, pricing detail and availability

| Model | Model ID (Claude API) | Cache write (5 min / 1 hour) | Cache read | Batch | Released | Retirement |
| --- | --- | --- | --- | --- | --- | --- |
| Claude Opus 5 | `claude-opus-5` | $6.25 / $10 | $0.50 | 50% off input and output | Jul 24, 2026 | Not sooner than Jul 24, 2027 |
| Claude Sonnet 5 | `claude-sonnet-5` | $2.50 / $4 | $0.20 | 50% off input and output | Jun 30, 2026 | Not sooner than Jun 30, 2027 |
| Claude Haiku 4.5 | `claude-haiku-4-5-20251001` (alias `claude-haiku-4-5`) | $1.25 / $2 | $0.10 | 50% off input and output | Oct 15, 2025 | Not sooner than Oct 15, 2026 |

- Sonnet 5 and Opus 5 list a larger maximum output for the Batch API (300K tokens, beta).
- Haiku 4.5's other platform IDs: Amazon Bedrock `anthropic.claude-haiku-4-5`, Google Cloud
  `claude-haiku-4-5@20251001`, Microsoft Foundry `claude-haiku-4-5`. This Action uses the direct
  Claude API only.
- Haiku 4.5 lists a reliable knowledge cutoff of Feb 2025 and a training-data cutoff of Jul 2025;
  Sonnet 5 lists Jan 2026 for both, and Opus 5 lists May 2026 for both.
- Sonnet 5 and Opus 5 think by default, and that counts against `max_tokens`. See
  [Choosing a provider](CONFIGURATION.md#choosing-a-provider).

## Retirement dates for the defaults

Both default models have a date worth knowing about. These come from the same sources and carry
the same disclaimer:

- **`gpt-5-mini`:** OpenAI's deprecations page lists its snapshot, `gpt-5-mini-2025-08-07`, for
  removal on **Dec 11, 2026**, with `gpt-5.6-terra` as the suggested replacement.
- **`claude-haiku-4-5-20251001`:** Anthropic lists its retirement as **not sooner than Oct 15,
  2026**. That is a floor, not a scheduled shutdown date.

If a default is retired, set `openai_model` or `anthropic_model` explicitly.

## Sources

Compiled on 2026-09-20 from:

- OpenAI: the [models](https://developers.openai.com/api/docs/models),
  [pricing](https://developers.openai.com/api/docs/pricing),
  [deprecations](https://developers.openai.com/api/docs/deprecations) and
  [changelog](https://developers.openai.com/api/docs/changelog) pages, and the individual model
  pages for `gpt-6-astra`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` and `gpt-5-mini`.
- Anthropic: the [Claude models overview](https://platform.claude.com/docs/en/models/overview)
  and the individual model pages for Haiku 4.5, Sonnet 5 and Opus 5, transcribed from
  screenshots taken from a personal account.

**Reminder: check the provider's own pages before relying on any figure above.**
