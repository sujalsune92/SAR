
# from __future__ import annotations

# import copy
# import hashlib
# import json
# import os
# import re
# from datetime import datetime, timezone
# from functools import lru_cache
# from pathlib import Path
# from typing import Any

# import chromadb
# import ollama
# from sentence_transformers import SentenceTransformer

# try:
#     from .rule_engine import build_rag_query, calculate_risk_score, evaluate_rules, load_rule_config
# except ImportError:
#     from rule_engine import build_rag_query, calculate_risk_score, evaluate_rules, load_rule_config


# ROOT_DIR = Path(__file__).resolve().parent.parent
# DEFAULT_ALERT_PATH = ROOT_DIR / "data" / "alert_case.json"
# VECTOR_DB_PATH = Path(os.getenv("CHROMA_DB_PATH", ROOT_DIR / "rag_pipeline" / "vector_db"))
# PROMPT_VERSION = "local-fastapi-v4"
# DEFAULT_MODEL_NAME = os.getenv("OLLAMA_MODEL", "phi3:mini")

# RAG_CHUNK_MAX_CHARS = 1800

# STRUCTURING_RULE_IDS  = {"AML-001", "AML-002", "AML-003", "AML-004", "AML-005", "AML-013"}
# JURISDICTION_RULE_IDS = {"AML-006", "AML-007", "AML-008", "AML-009", "AML-010", "AML-011", "AML-012"}

# # Vague words that weaken regulatory prose — flagged by validation
# VAGUE_WORDS = {"multiple", "several", "various", "numerous", "many", "some", "certain"}

# # Tags injected by enrichment layer or phi3:mini — stripped in post-processing
# ANNOTATION_TAGS = re.compile(
#     r"\s*\((FACT|COMPARISON|REASONING|EVIDENCE|ANALYSIS|NOTE)\)\s*",
#     re.IGNORECASE,
# )

# # Enrichment bucket names that must never reach the narrative
# ENRICHMENT_BUCKET_NAMES = re.compile(
#     r"\b(high_velocity_txns|uae_transfers|uea_transfers|structuring_txns"
#     r"|evidence\s*:\s*[\w_]+)\b",
#     re.IGNORECASE,
# )

# TXN_KEYWORDS: dict[str, list[str]] = {
#     "total_amount":        ["INR", "total", "amount", "aggregate", "lakh", "crore"],
#     "transaction_count":   ["transactions", "transfers", "executed", "inbound", "twenty-eight", "28"],
#     "time_window_days":    ["days", "within", "period", "window", "monitoring", "three-day"],
#     "destination_country": ["UAE", "MYANMAR", "CAYMAN", "BAHAMAS", "IRAN",
#                             "SEYCHELLES", "MAURITIUS", "VANUATU", "PANAMA",
#                             "transferred", "jurisdiction", "international", "offshore"],
#     "avg_amount":          ["average", "avg", "per transaction", "individual"],
#     "txn_per_day":         ["velocity", "txn/day", "daily", "threshold", "per day"],
# }


# def _build_rule_keyword_map() -> dict[str, dict[str, Any]]:
#     config = load_rule_config()
#     keyword_map: dict[str, dict[str, Any]] = {}
#     for rule in config.get("rules", []):
#         rule_id = rule["id"]
#         obs_plain = re.sub(r"\{[^}]+\}", " ", rule.get("observation_template", ""))
#         why_plain = re.sub(r"\{[^}]+\}", " ", rule.get("audit_reason", {}).get("why_flagged_template", ""))
#         all_keywords = list(set(
#             [w.strip(".,()[]") for w in obs_plain.split() if len(w.strip(".,()[]")) > 3]
#             + [w.strip(".,()[]") for w in why_plain.split() if len(w.strip(".,()[]")) > 3]
#             + [w for w in rule.get("name", "").split() if len(w) > 3]
#         ))
#         conditions = rule.get("conditions", [])
#         path = conditions[0].get("path", "") if conditions else ""
#         field = path.split(".")[-1] if "." in path else path
#         keyword_map[rule_id] = {
#             "keywords":  all_keywords,
#             "field":     field,
#             "rule_name": rule.get("name", rule_id),
#         }
#     return keyword_map


# def _normalise_amount_for_allowed_set(value: float | int | str) -> set[str]:
#     """Return both float and int string forms of a number to prevent mismatch."""
#     result: set[str] = set()
#     try:
#         f = float(value)
#         result.add(str(f))
#         result.add(str(int(f)) if f == int(f) else str(f))
#         result.add(str(round(f)))
#     except (ValueError, TypeError):
#         result.add(str(value))
#     return result


# def utc_now() -> str:
#     return datetime.now(timezone.utc).isoformat()


# def load_alert_from_file(alert_path: str | Path | None = None) -> dict[str, Any]:
#     path = Path(alert_path or DEFAULT_ALERT_PATH)
#     with path.open("r", encoding="utf-8") as handle:
#         return json.load(handle)


# def mask_identifier(value: str | None) -> str | None:
#     if not value:
#         return value
#     if len(value) <= 4:
#         return "*" * len(value)
#     return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


# def mask_name(value: str | None) -> str | None:
#     if not value:
#         return value
#     return " ".join(
#         f"{p[0]}{'*' * (len(p) - 1)}" if len(p) > 1 else "*"
#         for p in value.split()
#     )


# def mask_alert(alert: dict[str, Any]) -> dict[str, Any]:
#     masked = copy.deepcopy(alert)
#     masked["customer_name"] = mask_name(masked.get("customer_name"))
#     masked["customer_id"] = mask_identifier(masked.get("customer_id"))
#     return masked


# def _extract_prose_from_json_line(line: str) -> str:
#     """
#     If the LLM outputs a JSON object on a line, extract just the
#     "sentence" field text. Strips all JSON structure.
#     Called per-line in _post_process_narrative.
#     """
#     stripped = line.strip()
#     if not stripped.startswith("{"):
#         return line

#     # Try to parse as JSON
#     try:
#         obj = json.loads(stripped)
#         # Extract sentence/text field
#         for key in ("sentence", "text", "content", "narrative"):
#             if key in obj and isinstance(obj[key], str):
#                 return obj[key].strip()
#         # Last resort: join all string values
#         text_parts = [v for v in obj.values() if isinstance(v, str) and len(v) > 20]
#         if text_parts:
#             return max(text_parts, key=len).strip()
#     except (json.JSONDecodeError, ValueError):
#         pass

#     # Regex fallback: extract "sentence": "..." or "text": "..."
#     m = re.search(r'"(?:sentence|text|content)"\s*:\s*"((?:[^"\\]|\\.)*)"', stripped)
#     if m:
#         return m.group(1).replace('\\"', '"').strip()

#     # If we still have a JSON-looking line, strip it entirely
#     if stripped.startswith("{") and stripped.endswith("}"):
#         return ""

#     return line


# def split_paragraphs(text: str) -> list[str]:
#     raw_text = (text or "").strip()
#     if not raw_text:
#         return []

#     # Format 1: heading-prefixed
#     heading_pattern = re.compile(
#         r"^(background|transaction summary|typology|evidence|conclusion)\s*:?$",
#         flags=re.IGNORECASE | re.MULTILINE,
#     )
#     if heading_pattern.search(raw_text):
#         lines = [line.rstrip() for line in raw_text.splitlines()]
#         sections: list[str] = []
#         current_lines: list[str] = []
#         for line in lines:
#             if heading_pattern.match(line.strip()):
#                 if current_lines:
#                     section = " ".join(c.strip() for c in current_lines if c.strip()).strip()
#                     if section:
#                         sections.append(section)
#                 current_lines = []
#                 continue
#             if line.strip():
#                 current_lines.append(line.strip())
#             elif current_lines:
#                 current_lines.append(" ")
#         if current_lines:
#             section = " ".join(c.strip() for c in current_lines if c.strip()).strip()
#             if section:
#                 sections.append(section)
#         if len(sections) == 5:
#             return sections

#     # Format 2: blank-line prose (desired)
#     by_blank = [p.strip() for p in re.split(r"\n\s*\n", raw_text) if p.strip()]
#     if len(by_blank) == 5:
#         return by_blank

#     # Format 3: numbered list
#     numbered_split = re.split(r"\n(?=\d+[\.\)]\s)", raw_text.strip())
#     by_number = [re.sub(r"^\d+[\.\)]\s*", "", p).strip() for p in numbered_split if p.strip()]
#     if len(by_number) == 5:
#         return by_number

#     candidates = sorted([by_blank, by_number], key=len, reverse=True)
#     return candidates[0] if candidates[0] else by_blank


# def split_sentences(text: str) -> list[str]:
#     parts = re.split(r"(?<=[.!?])\s+", text.strip())
#     return [part.strip() for part in parts if part.strip()]


# def normalise_number_tokens(text: str) -> set[str]:
#     return {token.replace(",", "") for token in re.findall(r"\d+(?:,\d+)*(?:\.\d+)?", text)}


# def build_text_diff(original: str, updated: str) -> list[dict[str, Any]]:
#     import difflib
#     diff = difflib.unified_diff(
#         original.splitlines(), updated.splitlines(),
#         fromfile="generated", tofile="analyst", lineterm="",
#     )
#     return [{"line": line} for line in diff]


# @lru_cache(maxsize=1)
# def get_embedding_model() -> SentenceTransformer:
#     return SentenceTransformer("all-MiniLM-L6-v2")


# @lru_cache(maxsize=1)
# def get_collection():
#     client = chromadb.PersistentClient(path=str(VECTOR_DB_PATH))
#     return client.get_collection("sar_knowledge")


# class SarRagService:
#     def __init__(self, model_name: str = DEFAULT_MODEL_NAME) -> None:
#         self.model_name = model_name

#     def _chat_with_fallback(
#         self,
#         model_name: str,
#         system_prompt: str,
#         user_prompt: str,
#         model_options: dict[str, Any],
#     ) -> dict[str, Any]:
#         try:
#             return ollama.chat(
#                 model=model_name,
#                 messages=[
#                     {"role": "system", "content": system_prompt},
#                     {"role": "user", "content": user_prompt},
#                 ],
#                 options=model_options,
#             )
#         except Exception as exc:
#             if "cuda" not in str(exc).lower() and "gpu" not in str(exc).lower():
#                 raise
#             fallback_options = dict(model_options)
#             fallback_options["num_gpu"] = 0
#             return ollama.chat(
#                 model=model_name,
#                 messages=[
#                     {"role": "system", "content": system_prompt},
#                     {"role": "user", "content": user_prompt},
#                 ],
#                 options=fallback_options,
#             )

#     def _generate_narrative(
#         self,
#         alert: dict[str, Any],
#         prompt_payload: dict[str, Any],
#     ) -> str:
#         narrative = ""
#         for attempt in range(3):
#             raw = self._chat_with_fallback(
#                 model_name=self.model_name,
#                 system_prompt=prompt_payload["system_prompt"],
#                 user_prompt=prompt_payload["user_prompt"],
#                 model_options=prompt_payload["model_options"],
#             )
#             narrative = self._post_process_narrative(raw["message"]["content"], alert)
#             paragraphs = split_paragraphs(narrative)
#             word_count = len(narrative.split())
#             if len(paragraphs) == 5 and word_count >= 290:
#                 return narrative
#         return narrative

#     def process_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
#         case_started_at = utc_now()
#         masked_alert = mask_alert(alert)
#         audit_events: list[dict[str, Any]] = [{
#             "event_type": "CASE_INGESTED",
#             "payload": {
#                 "alert_id": alert["alert_id"],
#                 "masked_alert": masked_alert,
#                 "timestamp": case_started_at,
#             },
#         }]

#         evidence_blocks = evaluate_rules(alert)
#         risk_score, risk_level = calculate_risk_score(evidence_blocks)
#         evidence_pack = self._build_evidence_pack(alert, evidence_blocks, risk_score, risk_level)
#         audit_events.append({
#             "event_type": "RULES_EVALUATED",
#             "payload": {
#                 "risk_score": risk_score,
#                 "risk_level": risk_level,
#                 "rule_count": len(evidence_blocks),
#                 "evidence_blocks": evidence_blocks,
#             },
#         })

#         if not evidence_blocks:
#             final_sar = {
#                 "customer_name": alert["customer_name"],
#                 "customer_id": alert["customer_id"],
#                 "account_type": alert["account_type"],
#                 "alert_id": alert["alert_id"],
#                 "alert_type": alert["alert_type"],
#                 "risk_score": risk_score,
#                 "risk_level": risk_level,
#                 "rules_triggered": 0,
#                 "narrative": "No suspicious activity threshold was met. Case closed.",
#                 "generated_at": utc_now(),
#                 "status": "NO_SAR_REQUIRED",
#             }
#             return {
#                 "status": "NO_SAR_REQUIRED",
#                 "masked_alert": masked_alert,
#                 "risk_score": risk_score,
#                 "risk_level": risk_level,
#                 "evidence_pack": evidence_pack,
#                 "retrieval_payload": {},
#                 "prompt_payload": {},
#                 "validation_payload": {
#                     "passed": True,
#                     "checks": [{"name": "no_rules_triggered", "passed": True,
#                                 "details": "No AML rules fired."}],
#                     "failed_checks": [],
#                 },
#                 "final_sar": final_sar,
#                 "analyst_traceability": [],
#                 "audit_events": audit_events,
#             }

#         query = build_rag_query(evidence_blocks, masked_alert)
#         retrieval_payload = self._retrieve_context(query)
#         audit_events.append({"event_type": "RAG_RETRIEVAL_COMPLETED", "payload": retrieval_payload})

#         prompt_payload = self._build_prompt_bundle(masked_alert, evidence_blocks, retrieval_payload)
#         narrative = self._generate_narrative(alert, prompt_payload)
#         validation_payload = self._validate_narrative(alert, narrative)

#         # Hard block: PII → never store
#         pii_check = next((c for c in validation_payload["checks"] if c["name"] == "no_pii_exposed"), None)
#         if pii_check and not pii_check["passed"]:
#             raise RuntimeError(
#                 "HARD BLOCK: Customer PII detected in generated narrative. "
#                 "Case will not be stored."
#             )

#         sentence_traceability = self._build_sentence_traceability(
#             narrative, evidence_blocks, retrieval_payload["documents"],
#         )

#         final_sar = {
#             "customer_name": alert["customer_name"],
#             "customer_id": alert["customer_id"],
#             "account_type": alert["account_type"],
#             "alert_id": alert["alert_id"],
#             "alert_type": alert["alert_type"],
#             "risk_score": risk_score,
#             "risk_level": risk_level,
#             "rules_triggered": len(evidence_blocks),
#             "narrative": narrative,
#             "sentence_traceability": sentence_traceability,
#             "generated_at": utc_now(),
#             "status": "PENDING_ANALYST_REVIEW",
#         }

#         audit_events.extend([
#             {
#                 "event_type": "LLM_GENERATION_COMPLETED",
#                 "payload": {
#                     "model_name": self.model_name,
#                     "model_options": prompt_payload["model_options"],
#                     "prompt_version": prompt_payload["prompt_version"],
#                     "prompt_sha256": prompt_payload["prompt_sha256"],
#                     "prompt_sha": prompt_payload["prompt_sha"],
#                 },
#             },
#             {"event_type": "VALIDATION_COMPLETED", "payload": validation_payload},
#             {
#                 "event_type": "SENTENCE_TRACEABILITY_COMPLETED",
#                 "payload": {
#                     "total_sentences": len(sentence_traceability),
#                     "flagged_count": sum(1 for s in sentence_traceability if s["flagged_for_review"]),
#                     "source_type_breakdown": {
#                         t: sum(1 for s in sentence_traceability if s["source"]["type"] == t)
#                         for t in ("rule", "transaction", "document", "unmatched")
#                     },
#                 },
#             },
#             {
#                 "event_type": "CASE_READY_FOR_REVIEW",
#                 "payload": {"status": "PENDING_ANALYST_REVIEW", "generated_at": final_sar["generated_at"]},
#             },
#         ])

#         return {
#             "status": "PENDING_ANALYST_REVIEW",
#             "masked_alert": masked_alert,
#             "risk_score": risk_score,
#             "risk_level": risk_level,
#             "evidence_pack": evidence_pack,
#             "retrieval_payload": retrieval_payload,
#             "prompt_payload": prompt_payload,
#             "validation_payload": validation_payload,
#             "final_sar": final_sar,
#             "analyst_traceability": sentence_traceability,
#             "audit_events": audit_events,
#         }

#     def replay_case(self, case_record: dict[str, Any]) -> dict[str, Any]:
#         prompt_payload = case_record.get("prompt_payload") or {}
#         if not prompt_payload:
#             return {"replayed": False, "reason": "Prompt payload unavailable.", "replayed_at": utc_now()}
#         raw = self._chat_with_fallback(
#             model_name=prompt_payload.get("model_name", self.model_name),
#             system_prompt=prompt_payload["system_prompt"],
#             user_prompt=prompt_payload["user_prompt"],
#             model_options=prompt_payload.get("model_options", {"num_ctx": 2048, "temperature": 0.2, "top_p": 0.9}),
#         )
#         alert_payload = case_record["alert_payload"]
#         replay_narrative = self._post_process_narrative(raw["message"]["content"], alert_payload)
#         original_narrative = case_record.get("final_sar", {}).get("narrative", "")
#         return {
#             "replayed": True,
#             "replayed_at": utc_now(),
#             "replay_matches_original": replay_narrative == original_narrative,
#             "replayed_narrative": replay_narrative,
#             "original_narrative": original_narrative,
#             "raw_response": raw,
#         }

#     def _retrieve_context(self, query: str, n_results: int = 5) -> dict[str, Any]:
#         model = get_embedding_model()
#         collection = get_collection()
#         query_embedding = model.encode([query])
#         results = collection.query(query_embeddings=query_embedding, n_results=n_results)
#         snapshot = {
#             "snapshot_id": collection.name,
#             "total_docs": collection.count(),
#             "captured_at": utc_now(),
#         }
#         documents = []
#         for index, document in enumerate(results["documents"][0]):
#             distance = float(results["distances"][0][index])
#             documents.append({
#                 "id": results["ids"][0][index],
#                 "document": document[:RAG_CHUNK_MAX_CHARS],
#                 "distance": distance,
#                 "similarity_score": round(max(0.0, 1 - distance), 4),
#                 "metadata": results["metadatas"][0][index],
#             })
#         return {
#             "query_used": query,
#             "documents": documents,
#             "corpus_snapshot": snapshot,
#             "retrieval_timestamp": utc_now(),
#         }

#     def _build_evidence_pack(
#         self,
#         alert: dict[str, Any],
#         evidence_blocks: list[dict[str, Any]],
#         risk_score: float,
#         risk_level: str,
#     ) -> dict[str, Any]:
#         return {
#             "alert_id": alert["alert_id"],
#             "alert_type": alert["alert_type"],
#             "risk_score": risk_score,
#             "risk_level": risk_level,
#             "masked_alert": mask_alert(alert),
#             "transaction_details": self._build_transaction_details(alert),
#             "customer_financials": self._build_financials_block(alert),
#             "rule_summary": [
#                 {
#                     "rule_id": b["rule_id"],
#                     "rule_name": b["rule_name"],
#                     "confidence": b["confidence"],
#                     "observation": b["observation"],
#                     "why_flagged": b["audit_reason"]["why_flagged"],
#                     "regulation": b["audit_reason"]["regulation"],
#                 }
#                 for b in evidence_blocks
#             ],
#             "generated_at": utc_now(),
#         }

#     def _build_transaction_details(self, alert: dict[str, Any]) -> dict[str, Any]:
#         txn = alert["transactions"]
#         avg_amount = round(txn["total_amount"] / txn["transaction_count"])
#         details = {
#             "alert_type": alert["alert_type"],
#             "account_type": alert["account_type"],
#             "customer_profile": alert["customer_profile"],
#             "transaction_count": txn["transaction_count"],
#             "total_amount": txn["total_amount"],
#             "time_window_days": txn["time_window_days"],
#             "average_transaction_amount": avg_amount,
#             "destination_country": txn.get("destination_country", "DOMESTIC"),
#             "txn_per_day": round(txn["transaction_count"] / max(txn["time_window_days"], 1), 1),
#         }
#         for k in ["min_transaction_amount", "max_transaction_amount", "reporting_threshold"]:
#             if k in txn:
#                 details[k] = txn[k]
#         return details

#     def _build_financials_block(self, alert: dict[str, Any]) -> dict[str, Any] | None:
#         if "customer_financials" not in alert:
#             return None
#         financials = {k: v for k, v in copy.deepcopy(alert["customer_financials"]).items() if v is not None}
#         avg_monthly = financials.get("avg_monthly_deposits_12m")
#         if avg_monthly:
#             deviation = round(((alert["transactions"]["total_amount"] - avg_monthly) / avg_monthly) * 100, 1)
#             financials["deviation_from_baseline_pct"] = deviation
#         return financials

#     def _build_prompt_bundle(
#         self,
#         alert: dict[str, Any],
#         evidence_blocks: list[dict[str, Any]],
#         retrieval_payload: dict[str, Any],
#     ) -> dict[str, Any]:
#         td = self._build_transaction_details(alert)
#         financials = self._build_financials_block(alert)

#         evidence_summary = "\n".join(
#             f"- {b['rule_id']} ({b['rule_name']}): {b['observation']} "
#             f"[confidence: {b['confidence']}] — {b['audit_reason']['why_flagged']}"
#             for b in evidence_blocks
#         )

#         structuring_rules = ", ".join(
#             f"{b['rule_name']} ({b['rule_id']})"
#             for b in evidence_blocks
#             if b["rule_id"] in STRUCTURING_RULE_IDS
#         )
#         jurisdiction_rules = ", ".join(
#             f"{b['rule_name']} ({b['rule_id']})"
#             for b in evidence_blocks
#             if b["rule_id"] in JURISDICTION_RULE_IDS
#         )
#         uncategorised_rules = ", ".join(
#             f"{b['rule_name']} ({b['rule_id']})"
#             for b in evidence_blocks
#             if b["rule_id"] not in STRUCTURING_RULE_IDS | JURISDICTION_RULE_IDS
#         )
#         if uncategorised_rules:
#             jurisdiction_rules = f"{jurisdiction_rules}, {uncategorised_rules}".strip(", ")

#         context_parts = []
#         for item in retrieval_payload["documents"]:
#             doc_type = item["metadata"].get("type", "general")
#             prefix = "" if doc_type in {"typology", "guideline"} else \
#                 "[WRITING STYLE REFERENCE ONLY — DO NOT COPY FIGURES]\n"
#             context_parts.append(f"{prefix}{item['document']}")
#         context = "\n\n".join(context_parts)

#         txn_lines = [
#             "Transaction Details (use ONLY these exact figures — no others):",
#             f"- Alert Type            : {td['alert_type']}",
#             f"- Account Type          : {td['account_type']}",
#             f"- Customer Profile      : {td['customer_profile']}",
#             f"- Transaction Count     : {td['transaction_count']}",
#             f"- Total Amount          : INR {td['total_amount']}",
#             f"- Time Window           : {td['time_window_days']} days",
#             f"- Average Txn Amount    : INR {td['average_transaction_amount']}",
#             f"- Destination Country   : {td['destination_country']}",
#             f"- Transaction Velocity  : {td['txn_per_day']} txn/day (threshold: 5 txn/day)",
#         ]
#         for k, label in [
#             ("min_transaction_amount", "Min Transaction"),
#             ("max_transaction_amount", "Max Transaction"),
#             ("reporting_threshold",    "Reporting Threshold"),
#         ]:
#             if k in td:
#                 txn_lines.append(f"- {label:<22}: INR {td[k]}")

#         fin_lines: list[str] = []
#         if financials:
#             fin_lines = [
#                 "Customer Financials (use ONLY these exact figures):",
#                 f"- Declared Monthly Income      : INR {financials.get('declared_monthly_income', 'NOT PROVIDED')}",
#                 f"- Avg Monthly Deposits (12m)   : INR {financials.get('avg_monthly_deposits_12m', 'NOT PROVIDED')}",
#                 f"- Historical Txn Count/Month   : {financials.get('historical_baseline_txn_count', 'NOT PROVIDED')}",
#             ]
#             if "deviation_from_baseline_pct" in financials:
#                 fin_lines.append(
#                     f"- Deviation from Baseline      : {financials['deviation_from_baseline_pct']}% above historical baseline"
#                 )

#         deviation_str = (
#             f"{financials['deviation_from_baseline_pct']}%"
#             if financials and "deviation_from_baseline_pct" in financials
#             else "a significant percentage"
#         )

#         # NOTE: Prompt uses "First paragraph / Second paragraph" framing
#         # NOT "Paragraph 1 / Paragraph 2" — prevents phi3:mini from numbering output.
#         # Each paragraph has explicit MUST NOT rules to prevent bleeding and JSON output.
#         system_prompt = f"""You are a senior AML compliance analyst at a major financial institution.
# Write a SAR (Suspicious Activity Report) narrative. Output plain prose ONLY.

# OUTPUT FORMAT — MANDATORY:
# - Write exactly 5 paragraphs of plain English prose.
# - Separate each paragraph with one blank line.
# - Do NOT number paragraphs.
# - Do NOT write section headings.
# - Do NOT output JSON, markdown, bullet points, or any structured format.
# - Do NOT add (FACT), (COMPARISON), (REASONING), or any annotation tags.
# - Start immediately with the first sentence of the first paragraph.
# - End after the last sentence of the fifth paragraph.

# WRITING RULES:
# - Third person, past tense.
# - All monetary amounts prefixed with INR.
# - Write "the account holder" — NEVER the customer name or ID.
# - Use only numbers from the Transaction Details and Customer Financials below.
# - Minimum 290 words, maximum 460 words total.

# FIVE PARAGRAPHS — CONTENT AND BOUNDARIES:

# First paragraph — state ONLY:
#   The filing institution is submitting a SAR. Account type: {td['account_type']}.
#   Customer profile: {td['customer_profile']}. Alert: {alert['alert_type']}.
#   Monitoring period: {td['time_window_days']} days.
#   MUST NOT contain: transaction count, INR amounts, destination country.

# Second paragraph — state ONLY:
#   {td['transaction_count']} inbound transfers received, aggregating INR {td['total_amount']}.
#   Outbound wire transfers directed to {td['destination_country']} after each receipt.
#   Residual balance returned to near zero. Pass-through transit mechanism.
#   MUST NOT contain: deviation percentages, rule names, filing decision.

# Third paragraph — state ONLY:
#   Deviation of {deviation_str} above twelve-month baseline deposits.
#   Average INR {td['average_transaction_amount']} fell below RBI reporting threshold.
#   Velocity {td['txn_per_day']} txn/day exceeded institutional threshold of 5 txn/day.
#   Then name each of these rules by full name and ID in brackets:
#   {structuring_rules if structuring_rules else "(none)"}
#   MUST NOT contain: destination country, filing decision.

# Fourth paragraph — state ONLY:
#     The exact typology name is '{alert['alert_type']}'. Use this exact phrase in the fourth paragraph, no other name.
#   This pattern constitutes the AML typology of {alert['alert_type']}.
#   {td['destination_country']} is a FATF high-risk jurisdiction.
#   Rapid cross-border fund movement with near-zero residual balances = layering.
#   Then name each of these rules by full name and ID in brackets:
#   {jurisdiction_rules if jurisdiction_rules else "(none)"}
#   MUST NOT contain: filing decision, PMLA, enhanced monitoring.

# Fifth paragraph — state ONLY:
#   Filing institution determined activity is suspicious.
#   SAR filed under PMLA Section 12 and Rule 3 of PMLA (Maintenance of Records) Rules 2005.
#   Account placed under enhanced transaction monitoring.
#   Related accounts flagged through network analysis.
#   Matter escalated to Financial Intelligence Unit.
#   Source of funds documentation requested from the account holder.
#   MUST NOT contain: customer name, customer ID, transaction amounts, rule names."""

#         user_prompt = "\n".join([
#             "Write the SAR narrative now. Plain prose only. No JSON. No annotation tags.",
#             "",
#             *txn_lines,
#             *fin_lines,
#             "",
#             "Triggered AML Rules:",
#             evidence_summary,
#             "",
#             "Reference Knowledge (writing style only — never copy figures from here):",
#             context,
#             "",
#             "Verify before writing:",
#             f"  Section 1 (background): NO amounts, NO transaction count, NO destination",
#             f"  Section 2 (transactions): {td['transaction_count']} transfers, INR {td['total_amount']}, {td['destination_country']}, pass-through",
#             f"  Section 3 (typology): {deviation_str} deviation, {td['txn_per_day']} txn/day, cite rules: {structuring_rules}",
#             f"  Section 4 (evidence): MUST use the exact phrase '{alert['alert_type']}' as the typology name — not any other name. FATF {td['destination_country']}, cite rules: {jurisdiction_rules}",
#             f"  Section 5 (conclusion): PMLA Section 12, FIU, enhanced monitoring",
#             f"  Never write the customer name. Always write 'the account holder'.",
#             f"  Plain prose only — no JSON, no (FACT)/(REASONING) tags.",
#         ])

#         prompt_sha = hashlib.sha256(f"{system_prompt}\n---\n{user_prompt}".encode()).hexdigest()
#         return {
#             "prompt_version": PROMPT_VERSION,
#             "prompt_sha256": prompt_sha,
#             "prompt_sha": prompt_sha,
#             "model_name": self.model_name,
#             "model_options": {"num_ctx": 4096, "temperature": 0.2, "top_p": 0.9},
#             "system_prompt": system_prompt,
#             "user_prompt": user_prompt,
#         }

#     def _post_process_narrative(self, text: str, alert: dict[str, Any]) -> str:
#         """
#         Multi-layer cleaning pipeline:
#           1. Strip preamble phrases
#           2. Extract prose from JSON lines (phi3:mini defence)
#           3. Strip paragraph numbers
#           4. Strip (FACT)/(COMPARISON)/(REASONING) annotation tags
#           5. Strip enrichment bucket names
#           6. Strip square-bracket placeholders
#           7. Hard-strip customer name and ID
#         """
#         preamble_phrases = {
#             "here is the sar narrative", "here's the sar narrative",
#             "here is the narrative", "based on the compliance findings",
#             "sar narrative:", "narrative:", "suspicious activity report:",
#             "sar report:", "here is the suspicious activity report:",
#             "sure, here is", "certainly, here is",
#         }

#         lines = []
#         for line in text.strip().splitlines():
#             # Skip pure preamble lines
#             if line.strip().lower() in preamble_phrases:
#                 continue
#             # Extract prose from JSON lines
#             line = _extract_prose_from_json_line(line)
#             if not line:
#                 continue
#             # Strip leading paragraph numbers
#             line = re.sub(r"^\d+[\.\)]\s+", "", line)
#             line = re.sub(r"^PARAGRAPH\s+\d+\s*[:\-—]\s*", "", line, flags=re.IGNORECASE)
#             lines.append(line)

#         cleaned = "\n".join(lines).strip()

#         # Strip annotation tags from enrichment layer
#         cleaned = ANNOTATION_TAGS.sub(" ", cleaned)

#         # Strip enrichment bucket names
#         cleaned = ENRICHMENT_BUCKET_NAMES.sub("", cleaned)

#         # Strip evidence markers like [E1], [TXN:xxx], [evidence: xxx]
#         cleaned = re.sub(r"\[(?:E\d+|TXN:[^\]]+|evidence:[^\]]+)\]", "", cleaned, flags=re.IGNORECASE)

#         # Strip square-bracket placeholders
#         replacements = {
#             "[Filing Institution Name]": "The filing institution",
#             "[FILING INSTITUTION NAME]": "The filing institution",
#             "[Bank Name]":               "The filing institution",
#             "[CUSTOMER NAME]":           "the account holder",
#             "[Customer Name]":           "the account holder",
#             "[CUSTOMER ID]":             "",
#             "[ACCOUNT NUMBER]":          "",
#             "[ACCOUNT TYPE]":            alert["account_type"],
#             "[ALERT DATE]":              "the monitoring period",
#             "[START DATE]":              "the monitoring period",
#             "[END DATE]":                "the monitoring period",
#             "[APPLICABLE REGULATION]":   "PMLA Section 12",
#         }
#         for placeholder, replacement in replacements.items():
#             cleaned = cleaned.replace(placeholder, replacement)

#         # Hard-strip customer name and ID
#         customer_name = alert.get("customer_name", "")
#         customer_id   = alert.get("customer_id", "")
#         if customer_name:
#             cleaned = re.sub(re.escape(customer_name), "the account holder", cleaned, flags=re.IGNORECASE)
#         if customer_id:
#             cleaned = re.sub(re.escape(customer_id), "", cleaned, flags=re.IGNORECASE)

#         # Clean up any double spaces left by stripping
#         cleaned = re.sub(r"  +", " ", cleaned)
#         cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

#         return cleaned.strip()

#     def _build_sentence_traceability(
#         self,
#         narrative: str,
#         evidence_blocks: list[dict[str, Any]],
#         retrieved_documents: list[dict[str, Any]],
#     ) -> list[dict[str, Any]]:
#         rule_keyword_map = _build_rule_keyword_map()
#         fired_rule_ids = {b["rule_id"] for b in evidence_blocks}
#         traceability: list[dict[str, Any]] = []

#         for sentence in split_sentences(narrative):
#             lowered = sentence.lower()
#             source: dict[str, Any] | None = None

#             # Priority 1: fired AML rule
#             for rule_id, meta in rule_keyword_map.items():
#                 if rule_id not in fired_rule_ids:
#                     continue
#                 if any(kw.lower() in lowered for kw in meta["keywords"] if kw):
#                     block = next((b for b in evidence_blocks if b["rule_id"] == rule_id), {})
#                     source = {
#                         "type":        "rule",
#                         "id":          rule_id,
#                         "rule_name":   meta["rule_name"],
#                         "field":       meta["field"],
#                         "observation": block.get("observation", ""),
#                         "why_flagged": block.get("audit_reason", {}).get("why_flagged", ""),
#                     }
#                     break

#             # Priority 2: transaction field
#             if not source:
#                 for field, keywords in TXN_KEYWORDS.items():
#                     if any(kw.lower() in lowered for kw in keywords):
#                         source = {"type": "transaction", "id": "alert_payload", "field": field}
#                         break

#             # Priority 3: retrieved RAG document
#             if not source:
#                 best_doc: dict[str, Any] | None = None
#                 best_overlap = 0
#                 sentence_tokens = set(lowered.split())
#                 for doc in retrieved_documents:
#                     overlap = len(sentence_tokens & set(doc["document"].lower().split()))
#                     if overlap > best_overlap:
#                         best_overlap = overlap
#                         best_doc = doc
#                 if best_doc and best_overlap > 3:
#                     source = {
#                         "type":  "document",
#                         "id":    best_doc["id"],
#                         "field": best_doc["metadata"].get("type", "general"),
#                     }

#             # Priority 4: unmatched
#             if not source:
#                 source = {"type": "unmatched", "id": None, "field": None}

#             traceability.append({
#                 "sentence":           sentence,
#                 "source":             source,
#                 "flagged_for_review": source["type"] == "unmatched",
#             })

#         return traceability

#     def _validate_narrative(self, alert: dict[str, Any], narrative: str) -> dict[str, Any]:
#         paragraphs = split_paragraphs(narrative)
#         words = re.findall(r"\b\w+\b", "\n\n".join(paragraphs))
#         numbers_in_narrative = normalise_number_tokens(narrative)

#         txn = alert["transactions"]
#         txn_per_day = round(txn["transaction_count"] / max(txn["time_window_days"], 1), 1)
#         avg_amount  = round(txn["total_amount"] / txn["transaction_count"])

#         allowed_numbers: set[str] = set()
#         for static in ["5", "12", "20"]:
#             allowed_numbers.add(static)
#         allowed_numbers.add("2002")  # PMLA year — always present in regulation citation

#         for val in [txn["transaction_count"], txn["total_amount"],
#                     txn["time_window_days"], avg_amount, txn_per_day]:
#             allowed_numbers |= _normalise_amount_for_allowed_set(val)

#         for k in ["reporting_threshold", "min_transaction_amount", "max_transaction_amount"]:
#             if k in txn:
#                 allowed_numbers |= _normalise_amount_for_allowed_set(txn[k])

#         if "customer_financials" in alert:
#             for v in alert["customer_financials"].values():
#                 if v is not None:
#                     allowed_numbers |= _normalise_amount_for_allowed_set(v)

#         avg_monthly = None
#         if "customer_financials" in alert:
#             avg_monthly = alert["customer_financials"].get("avg_monthly_deposits_12m")
#         if avg_monthly is None:
#             avg_monthly = txn.get("avg_monthly_deposits_12m")
#         if avg_monthly is None:
#             avg_monthly = alert.get("avg_monthly_deposits_12m")
#         if avg_monthly:
#             deviation = round(((txn["total_amount"] - avg_monthly) / avg_monthly) * 100, 1)
#             allowed_numbers |= _normalise_amount_for_allowed_set(deviation)

#         # Check for vague words — find which ones are present
#         narrative_lower = narrative.lower()
#         found_vague = [w for w in VAGUE_WORDS if re.search(rf"\b{w}\b", narrative_lower)]

#         # Check for annotation tags that should have been stripped
#         has_annotation_tags = bool(ANNOTATION_TAGS.search(narrative))

#         # Check for enrichment bucket names leaking into narrative
#         has_bucket_names = bool(ENRICHMENT_BUCKET_NAMES.search(narrative))

#         # Check for JSON structure in narrative
#         has_json_output = bool(re.search(r'"\w+":\s*"', narrative))

#         checks = [
#             {
#                 "name": "five_paragraphs",
#                 "passed": len(paragraphs) == 5,
#                 "details": f"Found {len(paragraphs)} paragraphs.",
#             },
#             {
#                 "name": "word_count_range",
#                 "passed": 290 <= len(words) <= 460,
#                 "details": f"Narrative contains {len(words)} words.",
#             },
#             {
#                 "name": "no_pii_exposed",
#                 "passed": (
#                     alert["customer_name"].lower() not in narrative.lower()
#                     and alert["customer_id"].lower() not in narrative.lower()
#                 ),
#                 "details": "Customer name and ID absent from narrative.",
#             },
#             {
#                 "name": "no_placeholders",
#                 "passed": re.search(r"\[[^\]]+\]", narrative) is None,
#                 "details": "No unresolved placeholders.",
#             },
#             {
#                 "name": "correct_typology_used",
#                 "passed": alert["alert_type"].lower() in narrative.lower(),
#                 "details": f"Narrative references typology: {alert['alert_type']}.",
#             },
#             {
#                 "name": "no_bullet_formatting",
#                 "passed": not re.search(r"(^\s*[\*\-•]\s|\n\s*[\*\-•]\s)", narrative),
#                 "details": "Narrative is paragraph prose.",
#             },
#             {
#                 "name": "contains_filing_statement",
#                 "passed": "filing" in narrative_lower and "sar" in narrative_lower,
#                 "details": "Narrative includes filing decision.",
#             },
#             {
#                 "name": "numbers_are_evidence_bounded",
#                 "passed": numbers_in_narrative.issubset(allowed_numbers),
#                 "details": (
#                     f"Unexpected numbers: {sorted(numbers_in_narrative - allowed_numbers)}"
#                     if not numbers_in_narrative.issubset(allowed_numbers)
#                     else "All numbers are evidence-bounded."
#                 ),
#             },
#             {
#                 "name": "no_vague_words",
#                 "passed": len(found_vague) == 0,
#                 "details": (
#                     f"Vague words found: {found_vague}" if found_vague
#                     else "No vague words detected."
#                 ),
#             },
#             {
#                 "name": "no_annotation_tags",
#                 "passed": not has_annotation_tags,
#                 "details": "No (FACT)/(COMPARISON)/(REASONING) tags in narrative.",
#             },
#             {
#                 "name": "no_json_output",
#                 "passed": not has_json_output,
#                 "details": "Narrative is plain prose, not JSON.",
#             },
#             {
#                 "name": "no_bucket_names",
#                 "passed": not has_bucket_names,
#                 "details": "No enrichment bucket names leaked into narrative.",
#             },
#             {
#                 "name": "paragraph_content_isolation",
#                 "passed": (
#                     ("INR" not in paragraphs[0].upper() if len(paragraphs) >= 1 else True)
#                     and ("pmla" in paragraphs[4].lower() if len(paragraphs) >= 5 else True)
#                 ),
#                 "details": "Paragraph 1 has no INR amounts. Paragraph 5 has PMLA reference.",
#             },
#         ]

#         failed_checks = [c["name"] for c in checks if not c["passed"]]
#         return {
#             "passed": not failed_checks,
#             "checks": checks,
#             "failed_checks": failed_checks,
#             "validated_at": utc_now(),
#         }


# def export_case_files(result: dict[str, Any], output_dir: str | Path | None = None) -> tuple[Path, Path]:
#     destination = Path(output_dir or ROOT_DIR / "rag_pipeline")
#     destination.mkdir(parents=True, exist_ok=True)
#     final_sar = result["final_sar"]
#     alert_id = final_sar["alert_id"]
#     sar_path  = destination / f"final_sar_{alert_id}.json"
#     audit_path = destination / f"audit_{alert_id}.json"

#     audit_payload = {
#         "masked_alert": result["masked_alert"],
#         "risk_score": result["risk_score"],
#         "risk_level": result["risk_level"],
#         "evidence_pack": result["evidence_pack"],
#         "retrieval_payload": result["retrieval_payload"],
#         "prompt_payload": {
#             k: v for k, v in result["prompt_payload"].items()
#             if k not in {"system_prompt", "user_prompt"}
#         },
#         "validation_payload": result["validation_payload"],
#         "audit_events": result["audit_events"],
#     }

#     sar_path.write_text(json.dumps(final_sar, indent=2), encoding="utf-8")
#     audit_path.write_text(json.dumps(audit_payload, indent=2), encoding="utf-8")
#     return sar_path, audit_path

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import chromadb
import ollama
from sentence_transformers import SentenceTransformer

try:
    from .rule_engine import build_rag_query, calculate_risk_score, evaluate_rules, load_rule_config
except ImportError:
    from rule_engine import build_rag_query, calculate_risk_score, evaluate_rules, load_rule_config


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ALERT_PATH = ROOT_DIR / "data" / "alert_case.json"
VECTOR_DB_PATH = Path(os.getenv("CHROMA_DB_PATH", ROOT_DIR / "rag_pipeline" / "vector_db"))
PROMPT_VERSION = "local-fastapi-v5"
DEFAULT_MODEL_NAME = os.getenv("OLLAMA_MODEL", "phi3:mini")

RAG_CHUNK_MAX_CHARS = 1800

STRUCTURING_RULE_IDS  = {"AML-001", "AML-002", "AML-003", "AML-004", "AML-005", "AML-013"}
JURISDICTION_RULE_IDS = {"AML-006", "AML-007", "AML-008", "AML-009", "AML-010", "AML-011", "AML-012"}

VAGUE_WORDS = {"several", "various", "numerous", "many", "some", "certain"}

ANNOTATION_TAGS = re.compile(
    r"\s*\((FACT|COMPARISON|REASONING|EVIDENCE|ANALYSIS|NOTE)\)\s*",
    re.IGNORECASE,
)

ENRICHMENT_BUCKET_NAMES = re.compile(
    r"\b(high_velocity_txns|uae_transfers|uea_transfers|structuring_txns"
    r"|evidence\s*:\s*[\w_]+)\b",
    re.IGNORECASE,
)

# ── Paragraph boundary signals ────────────────────────────────────────────────
# Used by _reconstruct_paragraphs() when the LLM outputs no blank lines.
# Each group is (list_of_regex_patterns, min_paragraph_index_before_break).
# min_paragraph_index = the paragraph index that must be completed first.
_P2_SIGNALS = [
    r"\bduring the monitoring period\b",
    r"\bthe account received\b",
    r"\binbound (transfers|fund transfers)\b",
    r"\binbound wire\b",
]
_P3_SIGNALS = [
    r"\bdeviat(ed|ion)\b",
    r"\bvelocity\b",
    r"\bbelow the rbi\b",
    r"\babove (the |historical |twelve-month )",
    r"\bexceeded the institutional\b",
    r"\brepresented a \d",
    r"\btxn/day\b",
]
_P4_SIGNALS = [
    r"\btypology of\b",
    r"\baml typology\b",
    r"\bfatf high.risk\b",
    r"\bobserved pattern (constitutes|is consistent)\b",
    r"\bcircular fund flow\b",
    r"\bconstitutes the\b",
]
_P5_SIGNALS = [
    r"\bhas determined that the activity is suspicious\b",
    r"\bpmla section 12\b",
    r"\bfiling institution (has determined|files|filed)\b",
    r"\bthis sar is filed\b",
    r"\bfiled (this sar|pursuant)\b",
]

_PARAGRAPH_BOUNDARY_GROUPS = [
    (_P2_SIGNALS, 0),
    (_P3_SIGNALS, 1),
    (_P4_SIGNALS, 2),
    (_P5_SIGNALS, 3),
]


TXN_KEYWORDS: dict[str, list[str]] = {
    "total_amount":        ["INR", "total", "amount", "aggregate", "lakh", "crore"],
    "transaction_count":   ["transactions", "transfers", "executed", "inbound", "twenty-eight", "28"],
    "time_window_days":    ["days", "within", "period", "window", "monitoring", "three-day"],
    "destination_country": ["UAE", "MYANMAR", "CAYMAN", "BAHAMAS", "IRAN",
                            "SEYCHELLES", "MAURITIUS", "VANUATU", "PANAMA",
                            "transferred", "jurisdiction", "international", "offshore"],
    "avg_amount":          ["average", "avg", "per transaction", "individual"],
    "txn_per_day":         ["velocity", "txn/day", "daily", "threshold", "per day"],
}


def _build_rule_keyword_map() -> dict[str, dict[str, Any]]:
    config = load_rule_config()
    keyword_map: dict[str, dict[str, Any]] = {}
    for rule in config.get("rules", []):
        rule_id = rule["id"]
        obs_plain = re.sub(r"\{[^}]+\}", " ", rule.get("observation_template", ""))
        why_plain = re.sub(r"\{[^}]+\}", " ", rule.get("audit_reason", {}).get("why_flagged_template", ""))
        all_keywords = list(set(
            [w.strip(".,()[]") for w in obs_plain.split() if len(w.strip(".,()[]")) > 3]
            + [w.strip(".,()[]") for w in why_plain.split() if len(w.strip(".,()[]")) > 3]
            + [w for w in rule.get("name", "").split() if len(w) > 3]
        ))
        conditions = rule.get("conditions", [])
        path = conditions[0].get("path", "") if conditions else ""
        field = path.split(".")[-1] if "." in path else path
        keyword_map[rule_id] = {
            "keywords":  all_keywords,
            "field":     field,
            "rule_name": rule.get("name", rule_id),
        }
    return keyword_map


def _normalise_amount_for_allowed_set(value: float | int | str) -> set[str]:
    result: set[str] = set()
    try:
        f = float(value)
        result.add(str(f))
        result.add(str(int(f)) if f == int(f) else str(f))
        result.add(str(round(f)))
    except (ValueError, TypeError):
        result.add(str(value))
    return result


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_alert_from_file(alert_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(alert_path or DEFAULT_ALERT_PATH)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def mask_identifier(value: str | None) -> str | None:
    if not value:
        return value
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def mask_name(value: str | None) -> str | None:
    if not value:
        return value
    return " ".join(
        f"{p[0]}{'*' * (len(p) - 1)}" if len(p) > 1 else "*"
        for p in value.split()
    )


def mask_alert(alert: dict[str, Any]) -> dict[str, Any]:
    masked = copy.deepcopy(alert)
    masked["customer_name"] = mask_name(masked.get("customer_name"))
    masked["customer_id"] = mask_identifier(masked.get("customer_id"))
    return masked


def _extract_prose_from_json_line(line: str) -> str:
    stripped = line.strip()
    if not stripped.startswith("{"):
        return line
    try:
        obj = json.loads(stripped)
        for key in ("sentence", "text", "content", "narrative"):
            if key in obj and isinstance(obj[key], str):
                return obj[key].strip()
        text_parts = [v for v in obj.values() if isinstance(v, str) and len(v) > 20]
        if text_parts:
            return max(text_parts, key=len).strip()
    except (json.JSONDecodeError, ValueError):
        pass
    m = re.search(r'"(?:sentence|text|content)"\s*:\s*"((?:[^"\\]|\\.)*)"', stripped)
    if m:
        return m.group(1).replace('\\"', '"').strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return ""
    return line


def _matches_any(sentence: str, patterns: list[str]) -> bool:
    s = sentence.lower()
    return any(re.search(p, s) for p in patterns)


def _reconstruct_paragraphs(text: str) -> str:
    """
    When the LLM outputs all sentences as one wall of text (no blank lines),
    detect paragraph boundaries using content-transition signals and insert
    blank lines to produce a proper 5-paragraph structure.

    Signal priority order: P2 → P3 → P4 → P5.
    Each signal only fires once, and only after the preceding paragraph
    has accumulated at least 1 sentence.
    """
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    if not sentences:
        return text

    paragraphs: list[list[str]] = [[]]

    for sentence in sentences:
        current_idx = len(paragraphs) - 1

        broke = False
        for signals, min_completed_idx in _PARAGRAPH_BOUNDARY_GROUPS:
            if current_idx > min_completed_idx:
                continue  # already past this boundary
            if current_idx < min_completed_idx:
                continue  # haven't reached this boundary yet
            # current_idx == min_completed_idx: we're in the right paragraph to break
            if paragraphs[current_idx] and _matches_any(sentence, signals):
                paragraphs.append([])
                current_idx += 1
                broke = True
                break

        paragraphs[current_idx].append(sentence)

    result = [" ".join(p) for p in paragraphs if p]
    return "\n\n".join(result)


def split_paragraphs(text: str) -> list[str]:
    raw_text = (text or "").strip()
    if not raw_text:
        return []

    # Format 1: heading-prefixed
    heading_pattern = re.compile(
        r"^(background|transaction summary|typology|evidence|conclusion)\s*:?$",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if heading_pattern.search(raw_text):
        lines = [line.rstrip() for line in raw_text.splitlines()]
        sections: list[str] = []
        current_lines: list[str] = []
        for line in lines:
            if heading_pattern.match(line.strip()):
                if current_lines:
                    section = " ".join(c.strip() for c in current_lines if c.strip()).strip()
                    if section:
                        sections.append(section)
                current_lines = []
                continue
            if line.strip():
                current_lines.append(line.strip())
            elif current_lines:
                current_lines.append(" ")
        if current_lines:
            section = " ".join(c.strip() for c in current_lines if c.strip()).strip()
            if section:
                sections.append(section)
        if len(sections) == 5:
            return sections

    # Format 2: blank-line prose (desired)
    by_blank = [p.strip() for p in re.split(r"\n\s*\n", raw_text) if p.strip()]
    if len(by_blank) == 5:
        return by_blank

    # Format 3: numbered list
    numbered_split = re.split(r"\n(?=\d+[\.\)]\s)", raw_text.strip())
    by_number = [re.sub(r"^\d+[\.\)]\s*", "", p).strip() for p in numbered_split if p.strip()]
    if len(by_number) == 5:
        return by_number

    # Format 4: wall-of-text — reconstruct paragraphs from content signals
    reconstructed = _reconstruct_paragraphs(raw_text)
    by_reconstructed = [p.strip() for p in reconstructed.split("\n\n") if p.strip()]
    if len(by_reconstructed) == 5:
        return by_reconstructed

    # Fallback
    candidates = sorted([by_blank, by_number, by_reconstructed], key=len, reverse=True)
    return candidates[0] if candidates[0] else by_blank


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def normalise_number_tokens(text: str) -> set[str]:
    return {token.replace(",", "") for token in re.findall(r"\d+(?:,\d+)*(?:\.\d+)?", text)}


def build_text_diff(original: str, updated: str) -> list[dict[str, Any]]:
    import difflib
    diff = difflib.unified_diff(
        original.splitlines(), updated.splitlines(),
        fromfile="generated", tofile="analyst", lineterm="",
    )
    return [{"line": line} for line in diff]


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer("all-MiniLM-L6-v2")


@lru_cache(maxsize=1)
def get_collection():
    client = chromadb.PersistentClient(path=str(VECTOR_DB_PATH))
    return client.get_collection("sar_knowledge")


class SarRagService:
    def __init__(self, model_name: str = DEFAULT_MODEL_NAME) -> None:
        self.model_name = model_name

    def _chat_with_fallback(
        self,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        model_options: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return ollama.chat(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                options=model_options,
            )
        except Exception as exc:
            if "cuda" not in str(exc).lower() and "gpu" not in str(exc).lower():
                raise
            fallback_options = dict(model_options)
            fallback_options["num_gpu"] = 0
            return ollama.chat(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                options=fallback_options,
            )

    def _generate_narrative(
        self,
        alert: dict[str, Any],
        prompt_payload: dict[str, Any],
    ) -> str:
        narrative = ""
        for _ in range(3):
            raw = self._chat_with_fallback(
                model_name=self.model_name,
                system_prompt=prompt_payload["system_prompt"],
                user_prompt=prompt_payload["user_prompt"],
                model_options=prompt_payload["model_options"],
            )
            narrative = self._post_process_narrative(raw["message"]["content"], alert)
            paragraphs = split_paragraphs(narrative)
            if len(paragraphs) == 5 and len(narrative.split()) >= 200:
                return narrative
        return narrative

    def process_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        case_started_at = utc_now()
        masked_alert = mask_alert(alert)
        audit_events: list[dict[str, Any]] = [{
            "event_type": "CASE_INGESTED",
            "payload": {"alert_id": alert["alert_id"], "masked_alert": masked_alert,
                        "timestamp": case_started_at},
        }]

        evidence_blocks = evaluate_rules(alert)
        risk_score, risk_level = calculate_risk_score(evidence_blocks)
        evidence_pack = self._build_evidence_pack(alert, evidence_blocks, risk_score, risk_level)
        audit_events.append({
            "event_type": "RULES_EVALUATED",
            "payload": {"risk_score": risk_score, "risk_level": risk_level,
                        "rule_count": len(evidence_blocks), "evidence_blocks": evidence_blocks},
        })

        if not evidence_blocks:
            final_sar = {
                "customer_name": alert["customer_name"], "customer_id": alert["customer_id"],
                "account_type": alert["account_type"], "alert_id": alert["alert_id"],
                "alert_type": alert["alert_type"], "risk_score": risk_score,
                "risk_level": risk_level, "rules_triggered": 0,
                "narrative": "No suspicious activity threshold was met. Case closed.",
                "generated_at": utc_now(), "status": "NO_SAR_REQUIRED",
            }
            return {
                "status": "NO_SAR_REQUIRED", "masked_alert": masked_alert,
                "risk_score": risk_score, "risk_level": risk_level,
                "evidence_pack": evidence_pack, "retrieval_payload": {}, "prompt_payload": {},
                "validation_payload": {"passed": True,
                    "checks": [{"name": "no_rules_triggered", "passed": True,
                                "details": "No AML rules fired."}], "failed_checks": []},
                "final_sar": final_sar, "analyst_traceability": [], "audit_events": audit_events,
            }

        query = build_rag_query(evidence_blocks, masked_alert)
        retrieval_payload = self._retrieve_context(query)
        audit_events.append({"event_type": "RAG_RETRIEVAL_COMPLETED", "payload": retrieval_payload})

        prompt_payload = self._build_prompt_bundle(masked_alert, evidence_blocks, retrieval_payload)
        narrative = self._generate_narrative(alert, prompt_payload)
        validation_payload = self._validate_narrative(alert, narrative)

        pii_check = next((c for c in validation_payload["checks"] if c["name"] == "no_pii_exposed"), None)
        if pii_check and not pii_check["passed"]:
            raise RuntimeError("HARD BLOCK: PII detected in generated narrative. Case not stored.")

        sentence_traceability = self._build_sentence_traceability(
            narrative, evidence_blocks, retrieval_payload["documents"],
        )

        final_sar = {
            "customer_name": alert["customer_name"], "customer_id": alert["customer_id"],
            "account_type": alert["account_type"], "alert_id": alert["alert_id"],
            "alert_type": alert["alert_type"], "risk_score": risk_score,
            "risk_level": risk_level, "rules_triggered": len(evidence_blocks),
            "narrative": narrative, "sentence_traceability": sentence_traceability,
            "generated_at": utc_now(), "status": "PENDING_ANALYST_REVIEW",
        }

        audit_events.extend([
            {"event_type": "LLM_GENERATION_COMPLETED", "payload": {
                "model_name": self.model_name, "model_options": prompt_payload["model_options"],
                "prompt_version": prompt_payload["prompt_version"],
                "prompt_sha256": prompt_payload["prompt_sha256"],
                "prompt_sha": prompt_payload["prompt_sha"]}},
            {"event_type": "VALIDATION_COMPLETED", "payload": validation_payload},
            {"event_type": "SENTENCE_TRACEABILITY_COMPLETED", "payload": {
                "total_sentences": len(sentence_traceability),
                "flagged_count": sum(1 for s in sentence_traceability if s["flagged_for_review"]),
                "source_type_breakdown": {
                    t: sum(1 for s in sentence_traceability if s["source"]["type"] == t)
                    for t in ("rule", "transaction", "document", "unmatched")}}},
            {"event_type": "CASE_READY_FOR_REVIEW", "payload": {
                "status": "PENDING_ANALYST_REVIEW", "generated_at": final_sar["generated_at"]}},
        ])

        return {
            "status": "PENDING_ANALYST_REVIEW", "masked_alert": masked_alert,
            "risk_score": risk_score, "risk_level": risk_level,
            "evidence_pack": evidence_pack, "retrieval_payload": retrieval_payload,
            "prompt_payload": prompt_payload, "validation_payload": validation_payload,
            "final_sar": final_sar, "analyst_traceability": sentence_traceability,
            "audit_events": audit_events,
        }

    def replay_case(self, case_record: dict[str, Any]) -> dict[str, Any]:
        prompt_payload = case_record.get("prompt_payload") or {}
        if not prompt_payload:
            return {"replayed": False, "reason": "Prompt payload unavailable.", "replayed_at": utc_now()}
        raw = self._chat_with_fallback(
            model_name=prompt_payload.get("model_name", self.model_name),
            system_prompt=prompt_payload["system_prompt"],
            user_prompt=prompt_payload["user_prompt"],
            model_options=prompt_payload.get("model_options", {"num_ctx": 2048, "temperature": 0.2, "top_p": 0.9}),
        )
        alert_payload = case_record["alert_payload"]
        replay_narrative = self._post_process_narrative(raw["message"]["content"], alert_payload)
        original_narrative = case_record.get("final_sar", {}).get("narrative", "")
        return {
            "replayed": True, "replayed_at": utc_now(),
            "replay_matches_original": replay_narrative == original_narrative,
            "replayed_narrative": replay_narrative, "original_narrative": original_narrative,
            "raw_response": raw,
        }

    def _retrieve_context(self, query: str, n_results: int = 5) -> dict[str, Any]:
        model = get_embedding_model()
        collection = get_collection()
        query_embedding = model.encode([query])
        results = collection.query(query_embeddings=query_embedding, n_results=n_results)
        snapshot = {"snapshot_id": collection.name, "total_docs": collection.count(),
                    "captured_at": utc_now()}
        documents = []
        for index, document in enumerate(results["documents"][0]):
            distance = float(results["distances"][0][index])
            documents.append({
                "id": results["ids"][0][index],
                "document": document[:RAG_CHUNK_MAX_CHARS],
                "distance": distance,
                "similarity_score": round(max(0.0, 1 - distance), 4),
                "metadata": results["metadatas"][0][index],
            })
        return {"query_used": query, "documents": documents,
                "corpus_snapshot": snapshot, "retrieval_timestamp": utc_now()}

    def _build_evidence_pack(
        self,
        alert: dict[str, Any],
        evidence_blocks: list[dict[str, Any]],
        risk_score: float,
        risk_level: str,
    ) -> dict[str, Any]:
        return {
            "alert_id": alert["alert_id"], "alert_type": alert["alert_type"],
            "risk_score": risk_score, "risk_level": risk_level,
            "masked_alert": mask_alert(alert),
            "transaction_details": self._build_transaction_details(alert),
            "customer_financials": self._build_financials_block(alert),
            "rule_summary": [
                {"rule_id": b["rule_id"], "rule_name": b["rule_name"],
                 "confidence": b["confidence"], "observation": b["observation"],
                 "why_flagged": b["audit_reason"]["why_flagged"],
                 "regulation": b["audit_reason"]["regulation"]}
                for b in evidence_blocks
            ],
            "generated_at": utc_now(),
        }

    def _build_transaction_details(self, alert: dict[str, Any]) -> dict[str, Any]:
        txn = alert["transactions"]
        avg_amount = round(txn["total_amount"] / txn["transaction_count"])
        details = {
            "alert_type": alert["alert_type"], "account_type": alert["account_type"],
            "customer_profile": alert["customer_profile"],
            "transaction_count": txn["transaction_count"],
            "total_amount": txn["total_amount"],
            "time_window_days": txn["time_window_days"],
            "average_transaction_amount": avg_amount,
            "destination_country": txn.get("destination_country", "DOMESTIC"),
            "txn_per_day": round(txn["transaction_count"] / max(txn["time_window_days"], 1), 1),
        }
        for k in ["min_transaction_amount", "max_transaction_amount", "reporting_threshold"]:
            if k in txn:
                details[k] = txn[k]
        return details

    def _build_financials_block(self, alert: dict[str, Any]) -> dict[str, Any] | None:
        if "customer_financials" not in alert:
            return None
        financials = {k: v for k, v in copy.deepcopy(alert["customer_financials"]).items()
                      if v is not None}
        avg_monthly = financials.get("avg_monthly_deposits_12m")
        if avg_monthly:
            deviation = round(((alert["transactions"]["total_amount"] - avg_monthly) / avg_monthly) * 100, 1)
            financials["deviation_from_baseline_pct"] = deviation
        return financials

    def _build_prompt_bundle(
        self,
        alert: dict[str, Any],
        evidence_blocks: list[dict[str, Any]],
        retrieval_payload: dict[str, Any],
    ) -> dict[str, Any]:
        td = self._build_transaction_details(alert)
        financials = self._build_financials_block(alert)

        evidence_summary = "\n".join(
            f"- {b['rule_id']} ({b['rule_name']}): {b['observation']} "
            f"[confidence: {b['confidence']}] — {b['audit_reason']['why_flagged']}"
            for b in evidence_blocks
        )

        structuring_rules = ", ".join(
            f"{b['rule_name']} ({b['rule_id']})"
            for b in evidence_blocks if b["rule_id"] in STRUCTURING_RULE_IDS
        )
        jurisdiction_rules = ", ".join(
            f"{b['rule_name']} ({b['rule_id']})"
            for b in evidence_blocks if b["rule_id"] in JURISDICTION_RULE_IDS
        )
        uncategorised_rules = ", ".join(
            f"{b['rule_name']} ({b['rule_id']})"
            for b in evidence_blocks
            if b["rule_id"] not in STRUCTURING_RULE_IDS | JURISDICTION_RULE_IDS
        )
        if uncategorised_rules:
            jurisdiction_rules = f"{jurisdiction_rules}, {uncategorised_rules}".strip(", ")

        context_parts = []
        for item in retrieval_payload["documents"]:
            doc_type = item["metadata"].get("type", "general")
            prefix = "" if doc_type in {"typology", "guideline"} else \
                "[WRITING STYLE REFERENCE ONLY — DO NOT COPY FIGURES]\n"
            context_parts.append(f"{prefix}{item['document']}")
        context = "\n\n".join(context_parts)

        txn_lines = [
            "Transaction Details (use ONLY these exact figures):",
            f"- Alert Type            : {td['alert_type']}",
            f"- Account Type          : {td['account_type']}",
            f"- Customer Profile      : {td['customer_profile']}",
            f"- Transaction Count     : {td['transaction_count']}",
            f"- Total Amount          : INR {td['total_amount']}",
            f"- Time Window           : {td['time_window_days']} days",
            f"- Average Txn Amount    : INR {td['average_transaction_amount']}",
            f"- Destination Country   : {td['destination_country']}",
            f"- Transaction Velocity  : {td['txn_per_day']} txn/day (threshold: 5 txn/day)",
        ]
        for k, label in [("min_transaction_amount", "Min Transaction"),
                         ("max_transaction_amount", "Max Transaction"),
                         ("reporting_threshold",    "Reporting Threshold")]:
            if k in td:
                txn_lines.append(f"- {label:<22}: INR {td[k]}")

        fin_lines: list[str] = []
        if financials:
            fin_lines = [
                "Customer Financials (use ONLY these exact figures):",
                f"- Declared Monthly Income      : INR {financials.get('declared_monthly_income', 'NOT PROVIDED')}",
                f"- Avg Monthly Deposits (12m)   : INR {financials.get('avg_monthly_deposits_12m', 'NOT PROVIDED')}",
                f"- Historical Txn Count/Month   : {financials.get('historical_baseline_txn_count', 'NOT PROVIDED')}",
            ]
            if "deviation_from_baseline_pct" in financials:
                fin_lines.append(
                    f"- Deviation from Baseline      : {financials['deviation_from_baseline_pct']}% above historical baseline"
                )

        deviation_str = (
            f"{financials['deviation_from_baseline_pct']}%"
            if financials and "deviation_from_baseline_pct" in financials
            else "a significant percentage"
        )

        system_prompt = f"""You are a senior AML compliance analyst. Write a SAR narrative in plain prose.

CRITICAL FORMAT RULES:
- Write EXACTLY 5 paragraphs.
- Put a BLANK LINE between each paragraph.
- Do NOT number paragraphs or add headings.
- Do NOT output JSON, bullets, or structured text.
- Do NOT add (FACT), (COMPARISON), (REASONING) tags.
- Start with the first sentence of paragraph 1. End with the last sentence of paragraph 5.
- Third person, past tense. All amounts prefixed INR.
- Write "the account holder" — never the customer name or ID.
- Minimum 200 words. Maximum 460 words.

PARAGRAPH 1 — Background (2-3 sentences):
State: filing institution submitting SAR, account type {td['account_type']}, customer profile {td['customer_profile']}, alert type {alert['alert_type']}, monitoring period {td['time_window_days']} days.
Do NOT include: transaction counts, INR amounts, destination country.

PARAGRAPH 2 — Transaction Summary (3-4 sentences):
State: {td['transaction_count']} inbound transfers, aggregate INR {td['total_amount']}, outbound to {td['destination_country']}, residual balance near zero, pass-through mechanism.
Do NOT include: deviation percentages, velocity, rule names.

PARAGRAPH 3 — Typology Analysis (3-5 sentences):
State: {deviation_str} deviation above twelve-month baseline, average INR {td['average_transaction_amount']} below RBI threshold, velocity {td['txn_per_day']} txn/day exceeded threshold of 5.
Then name each rule: {structuring_rules if structuring_rules else "(none)"}.
Do NOT include: destination jurisdiction, filing decision.

PARAGRAPH 4 — Evidence (3-5 sentences):
State: pattern constitutes AML typology of {alert['alert_type']} — use this exact phrase.
{td['destination_country']} is FATF high-risk. Rapid cross-border movement obscures fund origin.
Then name each rule: {jurisdiction_rules if jurisdiction_rules else "(none)"}.
Do NOT include: PMLA, filing decision, enhanced monitoring.

PARAGRAPH 5 — Conclusion (3-5 sentences):
State: activity determined suspicious, SAR filed under PMLA Section 12 and Rule 3 of PMLA (Maintenance of Records) Rules 2005, enhanced monitoring placed, related accounts flagged, FIU escalated, source of funds requested.
Do NOT include: customer name, customer ID, transaction amounts, rule names."""

        user_prompt = "\n".join([
            "Write the SAR narrative. Plain prose only. 5 paragraphs separated by blank lines.",
            "",
            *txn_lines,
            *fin_lines,
            "",
            "Triggered AML Rules:",
            evidence_summary,
            "",
            "Reference (writing style and typology only — never copy figures):",
            context,
            "",
            "Before writing, confirm:",
            f"  Para 1: background only — no amounts, no transaction count, no destination",
            f"  Para 2: {td['transaction_count']} transfers, INR {td['total_amount']}, {td['destination_country']}, pass-through",
            f"  Para 3: {deviation_str} deviation, {td['txn_per_day']} txn/day, rules: {structuring_rules}",
            f"  Para 4: exact phrase '{alert['alert_type']}' as typology name, FATF {td['destination_country']}, rules: {jurisdiction_rules}",
            f"  Para 5: PMLA Section 12, FIU, enhanced monitoring",
            f"  Always 'the account holder' — never the customer name.",
            f"  Blank line between each paragraph.",
        ])

        prompt_sha = hashlib.sha256(f"{system_prompt}\n---\n{user_prompt}".encode()).hexdigest()
        return {
            "prompt_version": PROMPT_VERSION,
            "prompt_sha256": prompt_sha, "prompt_sha": prompt_sha,
            "model_name": self.model_name,
            "model_options": {"num_ctx": 4096, "temperature": 0.2, "top_p": 0.9},
            "system_prompt": system_prompt, "user_prompt": user_prompt,
        }

    def _post_process_narrative(self, text: str, alert: dict[str, Any]) -> str:
        """
        Multi-layer cleaning:
          1. Strip preamble phrases
          2. Extract prose from JSON lines
          3. Strip paragraph number labels (1. / PARAGRAPH 1:)
          4. Strip annotation tags (FACT/REASONING/etc)
          5. Strip enrichment bucket names
          6. Strip evidence markers and placeholders
          7. Hard-strip customer name and ID
          8. Reconstruct paragraph breaks if LLM produced a wall of text
        """
        preamble_phrases = {
            "here is the sar narrative", "here's the sar narrative",
            "here is the narrative", "based on the compliance findings",
            "sar narrative:", "narrative:", "suspicious activity report:",
            "sar report:", "here is the suspicious activity report:",
            "sure, here is", "certainly, here is",
        }

        lines = []
        for line in text.strip().splitlines():
            if line.strip().lower() in preamble_phrases:
                continue
            line = _extract_prose_from_json_line(line)
            if not line:
                continue
            # Strip leading paragraph numbers and PARAGRAPH N: labels
            line = re.sub(r"^\d+[\.\)]\s+", "", line)
            line = re.sub(r"^PARAGRAPH\s+\d+\s*[:\-—]\s*", "", line, flags=re.IGNORECASE)
            lines.append(line)

        cleaned = "\n".join(lines).strip()

        # Strip annotation tags
        cleaned = ANNOTATION_TAGS.sub(" ", cleaned)
        # Strip enrichment bucket names
        cleaned = ENRICHMENT_BUCKET_NAMES.sub("", cleaned)
        # Strip evidence markers
        cleaned = re.sub(r"\[(?:E\d+|TXN:[^\]]+|evidence:[^\]]+)\]", "", cleaned, flags=re.IGNORECASE)

        # Strip square-bracket placeholders
        replacements = {
            "[Filing Institution Name]": "The filing institution",
            "[FILING INSTITUTION NAME]": "The filing institution",
            "[Bank Name]":               "The filing institution",
            "[CUSTOMER NAME]":           "the account holder",
            "[Customer Name]":           "the account holder",
            "[CUSTOMER ID]":             "",
            "[ACCOUNT NUMBER]":          "",
            "[ACCOUNT TYPE]":            alert["account_type"],
            "[ALERT DATE]":              "the monitoring period",
            "[START DATE]":              "the monitoring period",
            "[END DATE]":                "the monitoring period",
            "[APPLICABLE REGULATION]":   "PMLA Section 12",
        }
        for placeholder, replacement in replacements.items():
            cleaned = cleaned.replace(placeholder, replacement)

        # Hard-strip customer name and ID
        customer_name = alert.get("customer_name", "")
        customer_id   = alert.get("customer_id", "")
        if customer_name:
            cleaned = re.sub(re.escape(customer_name), "the account holder",
                             cleaned, flags=re.IGNORECASE)
        if customer_id:
            cleaned = re.sub(re.escape(customer_id), "", cleaned, flags=re.IGNORECASE)

        # Tidy up whitespace artifacts
        cleaned = re.sub(r"  +", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = cleaned.strip()

        # If the LLM wrote no blank lines, reconstruct paragraph structure
        # from content-transition signals
        if "\n\n" not in cleaned:
            cleaned = _reconstruct_paragraphs(cleaned)

        return cleaned

    def _build_sentence_traceability(
        self,
        narrative: str,
        evidence_blocks: list[dict[str, Any]],
        retrieved_documents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rule_keyword_map = _build_rule_keyword_map()
        fired_rule_ids = {b["rule_id"] for b in evidence_blocks}
        traceability: list[dict[str, Any]] = []

        for sentence in split_sentences(narrative):
            lowered = sentence.lower()
            source: dict[str, Any] | None = None

            for rule_id, meta in rule_keyword_map.items():
                if rule_id not in fired_rule_ids:
                    continue
                if any(kw.lower() in lowered for kw in meta["keywords"] if kw):
                    block = next((b for b in evidence_blocks if b["rule_id"] == rule_id), {})
                    source = {
                        "type": "rule", "id": rule_id, "rule_name": meta["rule_name"],
                        "field": meta["field"], "observation": block.get("observation", ""),
                        "why_flagged": block.get("audit_reason", {}).get("why_flagged", ""),
                    }
                    break

            if not source:
                for field, keywords in TXN_KEYWORDS.items():
                    if any(kw.lower() in lowered for kw in keywords):
                        source = {"type": "transaction", "id": "alert_payload", "field": field}
                        break

            if not source:
                best_doc: dict[str, Any] | None = None
                best_overlap = 0
                sentence_tokens = set(lowered.split())
                for doc in retrieved_documents:
                    overlap = len(sentence_tokens & set(doc["document"].lower().split()))
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_doc = doc
                if best_doc and best_overlap > 3:
                    source = {"type": "document", "id": best_doc["id"],
                              "field": best_doc["metadata"].get("type", "general")}

            if not source:
                source = {"type": "unmatched", "id": None, "field": None}

            traceability.append({
                "sentence": sentence, "source": source,
                "flagged_for_review": source["type"] == "unmatched",
            })

        return traceability

    def _validate_narrative(self, alert: dict[str, Any], narrative: str) -> dict[str, Any]:
        paragraphs = split_paragraphs(narrative)
        words = re.findall(r"\b\w+\b", "\n\n".join(paragraphs))
        numbers_in_narrative = normalise_number_tokens(narrative)

        txn = alert["transactions"]
        txn_per_day = round(txn["transaction_count"] / max(txn["time_window_days"], 1), 1)
        avg_amount  = round(txn["total_amount"] / txn["transaction_count"])

        allowed_numbers: set[str] = {"5", "12", "20", "2002"}

        for val in [txn["transaction_count"], txn["total_amount"],
                    txn["time_window_days"], avg_amount, txn_per_day]:
            allowed_numbers |= _normalise_amount_for_allowed_set(val)

        for k in ["reporting_threshold", "min_transaction_amount", "max_transaction_amount"]:
            if k in txn:
                allowed_numbers |= _normalise_amount_for_allowed_set(txn[k])

        # Add deviation from baseline — computed from customer_financials if present
        avg_monthly: float | None = None
        if "customer_financials" in alert:
            for v in alert["customer_financials"].values():
                if v is not None:
                    allowed_numbers |= _normalise_amount_for_allowed_set(v)
            avg_monthly = alert["customer_financials"].get("avg_monthly_deposits_12m")
        if avg_monthly:
            deviation = round(((txn["total_amount"] - avg_monthly) / avg_monthly) * 100, 1)
            allowed_numbers |= _normalise_amount_for_allowed_set(deviation)

        narrative_lower = narrative.lower()
        found_vague = [w for w in VAGUE_WORDS if re.search(rf"\b{w}\b", narrative_lower)]
        has_annotation_tags = bool(ANNOTATION_TAGS.search(narrative))
        has_bucket_names    = bool(ENRICHMENT_BUCKET_NAMES.search(narrative))
        has_json_output     = bool(re.search(r'"\w+":\s*"', narrative))

        checks = [
            {"name": "five_paragraphs",
             "passed": len(paragraphs) == 5,
             "details": f"Found {len(paragraphs)} paragraphs."},
            {"name": "word_count_range",
             "passed": 200 <= len(words) <= 460,
             "details": f"Narrative contains {len(words)} words."},
            {"name": "no_pii_exposed",
             "passed": (alert["customer_name"].lower() not in narrative.lower()
                        and alert["customer_id"].lower() not in narrative.lower()),
             "details": "Customer name and ID absent from narrative."},
            {"name": "no_placeholders",
             "passed": re.search(r"\[[^\]]+\]", narrative) is None,
             "details": "No unresolved placeholders."},
            {"name": "correct_typology_used",
             "passed": alert["alert_type"].lower() in narrative.lower(),
             "details": f"Narrative references typology: {alert['alert_type']}."},
            {"name": "no_bullet_formatting",
             "passed": not re.search(r"(^\s*[\*\-•]\s|\n\s*[\*\-•]\s)", narrative),
             "details": "Narrative is paragraph prose."},
            {"name": "contains_filing_statement",
             "passed": "filing" in narrative_lower and "sar" in narrative_lower,
             "details": "Narrative includes filing decision."},
            {"name": "numbers_are_evidence_bounded",
             "passed": numbers_in_narrative.issubset(allowed_numbers),
             "details": (f"Unexpected: {sorted(numbers_in_narrative - allowed_numbers)}"
                         if not numbers_in_narrative.issubset(allowed_numbers)
                         else "All numbers evidence-bounded.")},
            {"name": "no_vague_words",
             "passed": len(found_vague) == 0,
             "details": f"Vague words: {found_vague}" if found_vague else "None detected."},
            {"name": "no_annotation_tags",
             "passed": not has_annotation_tags,
             "details": "No annotation tags in narrative."},
            {"name": "no_json_output",
             "passed": not has_json_output,
             "details": "Narrative is plain prose."},
            {"name": "no_bucket_names",
             "passed": not has_bucket_names,
             "details": "No enrichment bucket names leaked."},
            {"name": "paragraph_content_isolation",
             "passed": (
                 ("INR" not in paragraphs[0].upper() if len(paragraphs) >= 1 else True)
                 and ("pmla" in paragraphs[4].lower() if len(paragraphs) >= 5 else True)
             ),
             "details": "Para 1 has no INR. Para 5 has PMLA reference."},
        ]

        failed_checks = [c["name"] for c in checks if not c["passed"]]
        return {
            "passed": not failed_checks, "checks": checks,
            "failed_checks": failed_checks, "validated_at": utc_now(),
        }


def export_case_files(result: dict[str, Any], output_dir: str | Path | None = None) -> tuple[Path, Path]:
    destination = Path(output_dir or ROOT_DIR / "rag_pipeline")
    destination.mkdir(parents=True, exist_ok=True)
    final_sar = result["final_sar"]
    alert_id  = final_sar["alert_id"]
    sar_path   = destination / f"final_sar_{alert_id}.json"
    audit_path = destination / f"audit_{alert_id}.json"
    audit_payload = {
        "masked_alert": result["masked_alert"], "risk_score": result["risk_score"],
        "risk_level": result["risk_level"], "evidence_pack": result["evidence_pack"],
        "retrieval_payload": result["retrieval_payload"],
        "prompt_payload": {k: v for k, v in result["prompt_payload"].items()
                           if k not in {"system_prompt", "user_prompt"}},
        "validation_payload": result["validation_payload"],
        "audit_events": result["audit_events"],
    }
    sar_path.write_text(json.dumps(final_sar, indent=2), encoding="utf-8")
    audit_path.write_text(json.dumps(audit_payload, indent=2), encoding="utf-8")
    return sar_path, audit_path