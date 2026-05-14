# Architecture Write-Up

## System Design

The pipeline is built as a single Python script (`pipeline.py`) that processes inbound customer messages through four sequential stages:

```
sample_inputs.json -> [Ingestion] -> [Classification + Enrichment] -> [Routing + Escalation] -> output_records.json
```

**Ingestion:** Messages are read from `sample_inputs.json`. Each message includes an ID, source channel (Email, Web Form, Support Portal), and the raw text. In a production environment, this would be replaced by a webhook listener, email polling service, or message queue consumer.

**Classification & Enrichment (LLM):** Each message is sent to an LLM (OpenAI gpt-4o-mini) with a structured prompt that returns category, priority, confidence score, extracted entities, and a human-readable summary. The prompt enforces a strict JSON schema so the output can be parsed deterministically. A mock mode provides pre-built responses for demo and testing without an API key.

**Routing & Escalation (Deterministic):** Pure Python logic maps categories to destination queues and evaluates escalation rules. This is intentionally separated from the LLM step — routing rules are business logic that should be auditable, testable, and not subject to LLM hallucination.

**Output:** All processed records are written to `output_records.json` with a complete audit trail (raw message, classification, entities, routing decision, escalation reasons, timestamp).

**State:** There is no persistent state between runs. Each execution processes all inputs fresh. The output file is the single source of truth. In production, this would be backed by a database or message queue with deduplication.

## Routing Logic

Classifications map to queues via a simple dictionary:

| Category           | Destination Queue  |
|--------------------|-------------------|
| Bug Report         | Engineering Queue  |
| Feature Request    | Product Queue      |
| Billing Issue      | Billing Queue      |
| Technical Question | IT/Security Queue  |
| Incident/Outage    | Escalation Queue   |

This mapping is defined as a constant (`ROUTING_MAP`) so it can be changed without modifying logic. I chose these five queues because they align with the typical team structure of a B2B SaaS company: engineering handles bugs, product handles feature requests, finance/billing handles invoicing, IT handles auth/infrastructure questions, and incidents go directly to an escalation path.

## Escalation Logic

A record is escalated (rerouted to the Escalation Queue) if any of the following conditions are met:

1. **Low confidence (< 0.70):** If the LLM is not confident in its classification, a human should verify before the message enters a queue. The 0.70 threshold balances coverage (catching ambiguous messages) with noise (not escalating everything).

2. **Incident/Outage category:** All outage reports escalate regardless of confidence because the cost of missing a real outage far exceeds the cost of a false escalation.

3. **Escalation keywords:** Messages containing "outage," "down," "stopped loading," "unavailable," "all users affected," or "multiple users affected" trigger escalation. These are checked via simple string matching on the lowercase message, which is fast and predictable.

4. **Billing discrepancy > $500:** If a billing issue involves two monetary amounts and the difference exceeds $500, it escalates. This catches significant overcharges that need immediate attention. The threshold is configurable via `BILLING_DISCREPANCY_THRESHOLD`.

Each escalation reason is recorded in the output so reviewers can see exactly why a record was flagged.

## What I Would Do Differently at Production Scale

- **Message queue ingestion:** Replace file-based input with a message broker (RabbitMQ, SQS, or Kafka) for real-time processing, backpressure handling, and retry on failure.
- **Async processing:** Use async HTTP calls to the LLM API to process messages concurrently, reducing end-to-end latency.
- **Model fallback chain:** Try gpt-4o first, fall back to gpt-4o-mini, then to a local model (Ollama) if API calls fail. This improves reliability and reduces single-vendor dependency.
- **Confidence calibration:** Replace self-reported confidence with logprob-based scoring or an ensemble of classifiers to get calibrated uncertainty estimates.
- **Persistent storage:** Write records to a database (PostgreSQL) with proper indexing for audit, search, and analytics.
- **Monitoring and alerting:** Track classification distribution, confidence trends, escalation rates, and LLM latency. Alert on anomalies (e.g., sudden spike in low-confidence classifications).
- **Rate limiting and cost controls:** Add per-minute API call limits and token budget tracking to prevent runaway costs.

## Phase 2 Additions (Given Another Week)

- **Feedback loop:** Let human reviewers correct classifications, then use those corrections to build a fine-tuning dataset or few-shot prompt bank.
- **Duplicate detection:** Use embedding similarity to detect near-duplicate messages and link related requests.
- **SLA tracking:** Assign response-time targets per priority level and track whether routed teams meet them.
- **Multi-language support:** Add language detection and translation for non-English messages before classification.
- **Dashboard:** Build a simple web UI (Streamlit or Gradio) showing pipeline status, escalation queue, and classification metrics.
