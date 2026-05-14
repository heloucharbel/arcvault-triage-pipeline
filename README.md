# ArcVault AI Intake & Triage Pipeline

An AI-powered intake and triage system that automatically classifies, enriches, routes, and escalates inbound customer requests for a synthetic B2B SaaS company.

Built as a technical assessment for the AI Engineer role at Valsoft Corporation.

## How It Works

1. **Ingestion** - Reads inbound customer messages from `sample_inputs.json`
2. **Classification** - Uses an LLM to assign category, priority, and confidence score
3. **Enrichment** - Extracts entities (account IDs, invoice numbers, error codes, monetary amounts, systems mentioned, urgency signals)
4. **Routing** - Maps classifications to destination queues (Engineering, Product, Billing, IT/Security, Escalation)
5. **Escalation** - Flags records for human review based on confidence thresholds, outage keywords, and billing discrepancies
6. **Output** - Writes all processed records to `output_records.json`

## Quick Start

### Prerequisites

- Python 3.11+

### Setup

```bash
# Clone or download the project
cd arcvault-triage-pipeline

# (Optional) Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure your API key (optional — mock mode works without it)
cp .env.example .env
# Edit .env and add your OpenAI API key
```

### Run

```bash
# Run with OpenAI API (requires OPENAI_API_KEY in environment or .env)
python pipeline.py

# Run in mock mode (no API key needed)
python pipeline.py
```

If `OPENAI_API_KEY` is set in the environment, the pipeline uses OpenAI's gpt-4o-mini model. Otherwise, it runs in **mock mode** with pre-built responses — useful for demos and testing.

## Project Structure

```
.
├── pipeline.py           # Main pipeline script
├── sample_inputs.json    # Five sample inbound requests
├── output_records.json   # Generated output (after running)
├── requirements.txt      # Python dependencies
├── .env.example          # Environment variable template
├── prompts.md            # Prompt documentation and rationale
├── architecture.md       # System design and architecture write-up
└── README.md             # This file
```

## Output Format

Each processed record in `output_records.json` contains:

```json
{
  "request_id": 1,
  "source": "Email",
  "raw_message": "...",
  "timestamp": "2026-05-14T...",
  "classification": {
    "category": "Bug Report",
    "priority": "High",
    "confidence_score": 0.92
  },
  "enrichment": {
    "core_issue": "...",
    "extracted_entities": {
      "account_ids": [],
      "invoice_numbers": [],
      "error_codes": ["403"],
      "monetary_amounts": [],
      "systems_or_tools": ["ArcVault login"],
      "urgency_signal": "medium"
    }
  },
  "routing": {
    "routed_to": "Engineering Queue",
    "escalation_flag": false,
    "escalation_reasons": []
  },
  "summary": "..."
}
```

## Escalation Rules

A record is escalated if any of the following conditions are met:
- Confidence score is below 0.70
- Category is Incident/Outage
- Message contains keywords: "outage", "down", "stopped loading", "unavailable", "multiple users affected"
- Billing discrepancy exceeds $500

## Documentation

- **[prompts.md](prompts.md)** - LLM prompt text and design rationale
- **[architecture.md](architecture.md)** - System design, routing logic, escalation logic, and production scaling notes
