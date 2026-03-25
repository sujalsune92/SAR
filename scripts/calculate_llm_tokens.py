from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import ollama

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from rag_pipeline.pipeline_service import SarRagService, load_alert_from_file, mask_alert
from rag_pipeline.rule_engine import build_rag_query, evaluate_rules


DEFAULT_ALERT_PATH = ROOT_DIR / "data" / "alert_case.json"


def approx_token_count(text: str) -> int:
    if not text:
        return 0
    return len(re.findall(r"\w+|[^\w\s]", text))


def build_token_report(alert: dict[str, Any], model_name: str | None = None) -> dict[str, Any]:
    service = SarRagService(model_name=model_name) if model_name else SarRagService()

    masked_alert = mask_alert(alert)
    evidence_blocks = evaluate_rules(alert)
    if not evidence_blocks:
        return {
            "status": "NO_SAR_REQUIRED",
            "message": "No AML rules fired, so no LLM prompt was built.",
            "rule_count": 0,
        }

    query = build_rag_query(evidence_blocks, masked_alert)
    retrieval_payload = service._retrieve_context(query)
    prompt_payload = service._build_prompt_bundle(masked_alert, evidence_blocks, retrieval_payload)

    documents = retrieval_payload.get("documents", [])
    docs_breakdown = []
    docs_total = 0
    for item in documents:
        token_count = approx_token_count(item.get("document", ""))
        docs_total += token_count
        docs_breakdown.append(
            {
                "document_id": item.get("id"),
                "doc_type": (item.get("metadata") or {}).get("type", "general"),
                "token_count_estimate": token_count,
            }
        )

    system_prompt = prompt_payload["system_prompt"]
    user_prompt = prompt_payload["user_prompt"]

    response = ollama.chat(
        model=prompt_payload.get("model_name", service.model_name),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        options=prompt_payload.get("model_options", {}),
    )

    report = {
        "status": "OK",
        "model_name": prompt_payload.get("model_name", service.model_name),
        "model_options": prompt_payload.get("model_options", {}),
        "token_usage": {
            "query_tokens_estimate": approx_token_count(query),
            "retrieved_documents_tokens_estimate": docs_total,
            "retrieved_documents_breakdown": docs_breakdown,
            "system_prompt_tokens_estimate": approx_token_count(system_prompt),
            "user_prompt_tokens_estimate": approx_token_count(user_prompt),
            "llm_input_tokens_estimate": approx_token_count(system_prompt) + approx_token_count(user_prompt),
            "ollama_prompt_eval_count": response.get("prompt_eval_count"),
            "ollama_eval_count": response.get("eval_count"),
            "token_count_method": "regex_estimate_plus_ollama_runtime_counts",
        },
        "query_preview": query[:500],
        "retrieved_document_count": len(documents),
        "retrieval_timestamp": retrieval_payload.get("retrieval_timestamp"),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Calculate LLM token usage for SAR prompt flow without changing pipeline code.")
    parser.add_argument("--alert", type=str, default=str(DEFAULT_ALERT_PATH), help="Path to alert JSON file")
    parser.add_argument("--model", type=str, default=None, help="Optional model override (for example: mistral:7b)")
    parser.add_argument("--out", type=str, default=None, help="Optional output JSON path")
    args = parser.parse_args()

    alert = load_alert_from_file(args.alert)
    report = build_token_report(alert=alert, model_name=args.model)

    payload = json.dumps(report, indent=2)
    print(payload)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload, encoding="utf-8")
        print(f"\nSaved report to: {out_path}")


if __name__ == "__main__":
    main()
