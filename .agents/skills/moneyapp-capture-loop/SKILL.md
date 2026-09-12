---
name: moneyapp-capture-loop
description: Design or implement MoneyApp Quick Add and transaction-entry UX around a roughly 3–5 second open-app-to-save flow. Use for amount, merchant, category, keyboard, suggestion, duplicate-recovery, or save-latency work.
---

# MoneyApp Capture Loop

Optimize the primary path:

`open app -> amount -> merchant -> save`

The normal expense should take roughly 3–5 seconds without weakening financial correctness.

## Evaluate the flow

- Count required taps, focus changes, scrolls, and decisions for amount-only and amount-plus-merchant entry.
- Put the amount in immediate reach; evaluate autofocus, numeric keyboard choice, submit/next behavior, and keyboard dismissal.
- Prefer intelligent, trustworthy defaults for date, transaction type, recent merchant, and category.
- Use backend merchant confidence correctly. Auto-select only trusted identities; make confirmation explicit when required.
- Surface category suggestions without making category selection block save. Preserve user correction and category-learning behavior.
- Keep optional fields and long category lists out of the critical path unless evidence shows they improve speed.
- Provide recoverable handling for duplicate-looking entries and large-amount mistakes without blocking the initial save.
- Preserve entered data on failure and distinguish network, validation, and authentication errors appropriately.
- Consider perceived latency: disabled states, immediate feedback, retry behavior, refresh timing, and any artificial post-save delay.

## Verification

Trace the actual component-to-API path, verify request/response behavior with `moneyapp-contract-guard`, and test the flow in a mobile runtime when UI behavior changes. Record the normal-path tap count and any measured or observed save latency.

Do not add decorative steps, prompts, or dependencies that slow the normal path without a demonstrated product benefit.
