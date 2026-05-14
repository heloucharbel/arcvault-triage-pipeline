"""
ArcVault AI-Powered Intake & Triage Pipeline
=============================================
Processes inbound customer requests through classification, enrichment,
routing, and escalation using an LLM (OpenAI API or mock mode).
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CATEGORIES = [
    "Bug Report",
    "Feature Request",
    "Billing Issue",
    "Technical Question",
    "Incident/Outage",
]

ROUTING_MAP = {
    "Bug Report": "Engineering Queue",
    "Feature Request": "Product Queue",
    "Billing Issue": "Billing Queue",
    "Technical Question": "IT/Security Queue",
    "Incident/Outage": "Escalation Queue",
}

ESCALATION_KEYWORDS = [
    "outage",
    "down",
    "stopped loading",
    "unavailable",
    "all users affected",
    "multiple users affected",
]

CONFIDENCE_THRESHOLD = 0.70
BILLING_DISCREPANCY_THRESHOLD = 500

# ---------------------------------------------------------------------------
# LLM Prompt
# ---------------------------------------------------------------------------

CLASSIFICATION_PROMPT = """You are a customer support triage assistant for ArcVault, a B2B SaaS company.

Analyze the following customer message and return a JSON object with these exact fields:

{{
  "category": "<one of: Bug Report, Feature Request, Billing Issue, Technical Question, Incident/Outage>",
  "priority": "<one of: Low, Medium, High>",
  "confidence_score": <float between 0.0 and 1.0>,
  "core_issue": "<one sentence summarizing the core problem or request>",
  "extracted_entities": {{
    "account_ids": [<list of account IDs or URLs found>],
    "invoice_numbers": [<list of invoice numbers found>],
    "error_codes": [<list of error codes found>],
    "monetary_amounts": [<list of dollar amounts found>],
    "systems_or_tools": [<list of products, tools, or systems mentioned>],
    "urgency_signal": "<none | low | medium | high>"
  }},
  "summary": "<2-3 sentence human-readable summary for the receiving team>"
}}

Rules:
- confidence_score should reflect how certain you are about the category assignment.
- urgency_signal should be "high" if the message mentions outages, downtime, or multiple users affected.
- Be precise with entity extraction. Only include entities actually present in the message.
- Return ONLY valid JSON. No markdown, no explanation.

Customer message (source: {source}):
\"\"\"{message}\"\"\"
"""

# ---------------------------------------------------------------------------
# Mock LLM Responses (for running without an API key)
# ---------------------------------------------------------------------------

MOCK_RESPONSES = {
    1: {
        "category": "Bug Report",
        "priority": "High",
        "confidence_score": 0.92,
        "core_issue": "User is receiving a 403 error when attempting to log in, started after a recent platform update.",
        "extracted_entities": {
            "account_ids": ["arcvault.io/user/jsmith"],
            "invoice_numbers": [],
            "error_codes": ["403"],
            "monetary_amounts": [],
            "systems_or_tools": ["ArcVault login"],
            "urgency_signal": "medium",
        },
        "summary": "A user reports being unable to log in due to a persistent 403 error tied to their account. The issue began after a platform update last Tuesday. This should be investigated as a potential regression from the recent release.",
    },
    2: {
        "category": "Feature Request",
        "priority": "Medium",
        "confidence_score": 0.95,
        "core_issue": "Customer requests a bulk export feature for audit logs to support compliance workflows.",
        "extracted_entities": {
            "account_ids": [],
            "invoice_numbers": [],
            "error_codes": [],
            "monetary_amounts": [],
            "systems_or_tools": ["audit logs", "bulk export"],
            "urgency_signal": "low",
        },
        "summary": "A compliance-focused customer is requesting a bulk export capability for audit logs. They indicate this would save significant manual effort each month. This is a feature enhancement request with no immediate urgency.",
    },
    3: {
        "category": "Billing Issue",
        "priority": "High",
        "confidence_score": 0.96,
        "core_issue": "Invoice #8821 shows a charge of $1,240 versus the contracted rate of $980/month — a $260 billing discrepancy.",
        "extracted_entities": {
            "account_ids": [],
            "invoice_numbers": ["#8821"],
            "error_codes": [],
            "monetary_amounts": ["$1,240", "$980"],
            "systems_or_tools": ["billing", "invoicing"],
            "urgency_signal": "medium",
        },
        "summary": "The customer reports a billing discrepancy on Invoice #8821. They were charged $1,240 but their contract rate is $980/month, resulting in a $260 overcharge. The billing team should review the invoice and contract terms.",
    },
    4: {
        "category": "Technical Question",
        "priority": "Low",
        "confidence_score": 0.88,
        "core_issue": "Customer is asking whether ArcVault supports SSO integration with Okta.",
        "extracted_entities": {
            "account_ids": [],
            "invoice_numbers": [],
            "error_codes": [],
            "monetary_amounts": [],
            "systems_or_tools": ["SSO", "Okta", "auth provider"],
            "urgency_signal": "none",
        },
        "summary": "A customer is evaluating whether ArcVault supports SSO with Okta as they consider switching authentication providers. This is a pre-sales or technical configuration question with no urgency. Route to IT/Security for a capability response.",
    },
    5: {
        "category": "Incident/Outage",
        "priority": "High",
        "confidence_score": 0.97,
        "core_issue": "ArcVault dashboard stopped loading around 2pm EST, affecting multiple users.",
        "extracted_entities": {
            "account_ids": [],
            "invoice_numbers": [],
            "error_codes": [],
            "monetary_amounts": [],
            "systems_or_tools": ["dashboard"],
            "urgency_signal": "high",
        },
        "summary": "A customer reports that the ArcVault dashboard stopped loading at approximately 2pm EST. They have confirmed the issue is not on their end and that multiple users are affected. This is a potential service outage requiring immediate investigation.",
    },
}

# ---------------------------------------------------------------------------
# OpenAI API Integration
# ---------------------------------------------------------------------------


def classify_with_openai(message: str, source: str) -> dict:
    """Call the OpenAI API to classify and enrich a customer message."""
    from openai import OpenAI

    client = OpenAI()  # uses OPENAI_API_KEY from environment

    prompt = CLASSIFICATION_PROMPT.format(source=source, message=message)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a precise JSON-outputting triage assistant. Return only valid JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=600,
    )

    raw = response.choices[0].message.content.strip()
    return parse_llm_json(raw)


def classify_with_mock(request_id: int) -> dict:
    """Return a pre-built mock response for demo/testing without an API key."""
    return MOCK_RESPONSES[request_id]


# ---------------------------------------------------------------------------
# JSON Parsing & Validation
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = [
    "category",
    "priority",
    "confidence_score",
    "core_issue",
    "extracted_entities",
    "summary",
]

REQUIRED_ENTITY_FIELDS = [
    "account_ids",
    "invoice_numbers",
    "error_codes",
    "monetary_amounts",
    "systems_or_tools",
    "urgency_signal",
]


def parse_llm_json(raw: str) -> dict:
    """Parse JSON from LLM output, handling common formatting issues."""
    # Strip markdown code fences if present
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Attempt to find JSON object in the response
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError(f"Could not parse JSON from LLM response: {raw[:200]}")

    return validate_classification(data)


def validate_classification(data: dict) -> dict:
    """Validate and normalize the classification output."""
    # Check required top-level fields
    for field in REQUIRED_FIELDS:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")

    # Validate category
    if data["category"] not in CATEGORIES:
        raise ValueError(f"Invalid category: {data['category']}")

    # Validate priority
    if data["priority"] not in ("Low", "Medium", "High"):
        raise ValueError(f"Invalid priority: {data['priority']}")

    # Validate and clamp confidence score
    score = float(data["confidence_score"])
    data["confidence_score"] = max(0.0, min(1.0, score))

    # Validate extracted_entities
    entities = data.get("extracted_entities", {})
    for field in REQUIRED_ENTITY_FIELDS:
        if field not in entities:
            entities[field] = [] if field != "urgency_signal" else "none"
    data["extracted_entities"] = entities

    return data


# ---------------------------------------------------------------------------
# Routing & Escalation Logic
# ---------------------------------------------------------------------------


def determine_route(classification: dict, raw_message: str) -> dict:
    """Apply deterministic routing and escalation rules."""
    category = classification["category"]
    confidence = classification["confidence_score"]
    destination = ROUTING_MAP.get(category, "General Queue")

    escalation_reasons = []

    # Rule 1: Low confidence
    if confidence < CONFIDENCE_THRESHOLD:
        escalation_reasons.append(
            f"Low confidence score ({confidence:.2f} < {CONFIDENCE_THRESHOLD})"
        )

    # Rule 2: Incident/Outage always escalates
    if category == "Incident/Outage":
        escalation_reasons.append("Category is Incident/Outage")

    # Rule 3: Escalation keywords in message
    message_lower = raw_message.lower()
    for keyword in ESCALATION_KEYWORDS:
        if keyword in message_lower:
            escalation_reasons.append(f"Message contains escalation keyword: '{keyword}'")
            break  # one keyword match is enough

    # Rule 4: Billing discrepancy > $500
    if category == "Billing Issue":
        amounts = classification["extracted_entities"].get("monetary_amounts", [])
        dollar_values = []
        for amt in amounts:
            cleaned = re.sub(r"[^\d.]", "", str(amt))
            if cleaned:
                dollar_values.append(float(cleaned))
        if len(dollar_values) >= 2:
            discrepancy = abs(dollar_values[0] - dollar_values[1])
            if discrepancy > BILLING_DISCREPANCY_THRESHOLD:
                escalation_reasons.append(
                    f"Billing discrepancy ${discrepancy:,.0f} exceeds ${BILLING_DISCREPANCY_THRESHOLD} threshold"
                )

    escalate = len(escalation_reasons) > 0

    return {
        "routed_to": "Escalation Queue" if escalate else destination,
        "escalation_flag": escalate,
        "escalation_reasons": escalation_reasons,
    }


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------


def process_request(request: dict, use_openai: bool) -> dict:
    """Process a single inbound request through the full pipeline."""
    request_id = request["id"]
    source = request["source"]
    message = request["message"]

    # Step 1: Classification + Enrichment
    if use_openai:
        classification = classify_with_openai(message, source)
    else:
        classification = classify_with_mock(request_id)

    # Step 2: Routing + Escalation
    routing = determine_route(classification, message)

    # Step 3: Assemble output record
    record = {
        "request_id": request_id,
        "source": source,
        "raw_message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "classification": {
            "category": classification["category"],
            "priority": classification["priority"],
            "confidence_score": classification["confidence_score"],
        },
        "enrichment": {
            "core_issue": classification["core_issue"],
            "extracted_entities": classification["extracted_entities"],
        },
        "routing": routing,
        "summary": classification["summary"],
    }

    return record


def run_pipeline():
    """Run the full intake pipeline on all sample inputs."""
    # Determine mode
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    use_openai = bool(api_key)
    mode = "OpenAI API (gpt-4o-mini)" if use_openai else "Mock Mode"

    print(f"ArcVault Intake & Triage Pipeline")
    print(f"Mode: {mode}")
    print("-" * 50)

    # Load inputs
    with open("sample_inputs.json", "r") as f:
        requests = json.load(f)

    print(f"Loaded {len(requests)} inbound requests.\n")

    # Process each request
    records = []
    for req in requests:
        print(f"Processing request #{req['id']} ({req['source']})...")
        try:
            record = process_request(req, use_openai)
            records.append(record)
            cat = record["classification"]["category"]
            pri = record["classification"]["priority"]
            conf = record["classification"]["confidence_score"]
            dest = record["routing"]["routed_to"]
            esc = record["routing"]["escalation_flag"]
            print(f"  -> {cat} | {pri} | Confidence: {conf:.2f} | -> {dest}", end="")
            if esc:
                print(f" [ESCALATED]")
            else:
                print()
        except Exception as e:
            print(f"  ERROR processing request #{req['id']}: {e}")
            records.append({
                "request_id": req["id"],
                "source": req["source"],
                "raw_message": req["message"],
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    # Write output
    output_path = "output_records.json"
    with open(output_path, "w") as f:
        json.dump(records, f, indent=2)

    print(f"\nDone. {len(records)} records written to {output_path}")

    # Print summary table
    print(f"\n{'='*70}")
    print(f"{'#':<4} {'Category':<20} {'Priority':<10} {'Conf':<7} {'Destination':<22} {'Esc'}")
    print(f"{'-'*70}")
    for r in records:
        if "error" in r:
            print(f"{r['request_id']:<4} ERROR: {r['error'][:50]}")
            continue
        c = r["classification"]
        print(
            f"{r['request_id']:<4} {c['category']:<20} {c['priority']:<10} "
            f"{c['confidence_score']:<7.2f} {r['routing']['routed_to']:<22} "
            f"{'YES' if r['routing']['escalation_flag'] else 'No'}"
        )
    print(f"{'='*70}")


if __name__ == "__main__":
    run_pipeline()
