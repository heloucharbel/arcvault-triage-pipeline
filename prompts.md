# Prompt Documentation

## Classification & Enrichment Prompt

### The Prompt

The pipeline uses a single, combined prompt that handles classification, enrichment, and summary generation in one LLM call. The full prompt is defined in `pipeline.py` as `CLASSIFICATION_PROMPT`.

The prompt instructs the model to return a JSON object with six fields: `category`, `priority`, `confidence_score`, `core_issue`, `extracted_entities`, and `summary`.

### Design Rationale

**Single-pass design.** I chose to combine classification, entity extraction, and summary generation into one prompt rather than chaining multiple calls. For a five-message pipeline, the latency and cost savings of a single call outweigh the marginal accuracy gain of dedicated extraction steps. Each additional LLM call adds ~500ms-1s of latency and doubles token cost. At production scale with thousands of messages, I would split these into separate steps for independent tuning and retry logic.

**Strict JSON output format.** The prompt explicitly defines the JSON schema the model must return, including field names, types, and allowed values. This makes parsing deterministic and avoids post-processing guesswork. I also set `temperature=0.1` to minimize creative variation — for triage, consistency matters more than novelty.

**Enumerated categories and priorities.** By listing the exact valid values in the prompt (e.g., "one of: Bug Report, Feature Request, ..."), the model is constrained to the routing vocabulary. This prevents drift into synonyms like "Defect" or "Enhancement" that would break downstream routing logic.

**Confidence score as a self-assessment.** Asking the model to self-report confidence is imperfect — LLMs are not calibrated probability estimators. However, for a triage pipeline, even a rough confidence signal is useful for flagging ambiguous messages for human review. In production, I would supplement this with a secondary classifier or use logprobs from the API for a more grounded confidence measure.

**Entity extraction in structured sub-fields.** Rather than asking for a flat list of "entities," I specified exact sub-fields (account_ids, invoice_numbers, error_codes, monetary_amounts, systems_or_tools, urgency_signal). This forces the model to categorize entities by type, which makes downstream processing (e.g., checking billing discrepancies) straightforward without additional parsing.

### Tradeoffs

- **Combining steps reduces debuggability.** If the model miscategorizes a message, it is harder to isolate whether the error was in classification or in entity extraction. Separate prompts would allow independent evaluation.
- **Self-reported confidence is unreliable.** The model may report high confidence even when wrong. A production system should use logprobs or ensemble methods.
- **Single model dependency.** The pipeline relies entirely on one model (gpt-4o-mini). A production version should support model fallback (e.g., try gpt-4o, fall back to gpt-4o-mini, fall back to a local model).

### What I Would Change With More Time

- Add few-shot examples to the prompt for each category to improve classification accuracy on edge cases.
- Split into two prompts: one for classification (category + priority + confidence) and one for enrichment (entities + summary), to allow independent tuning.
- Implement prompt versioning so changes can be tracked and A/B tested.
- Use OpenAI's structured output mode (`response_format={"type": "json_object"}`) for guaranteed JSON compliance.
