import json
import re
from typing import Any


def _split_paragraphs(text: str) -> list[str]:
    return [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]


def _split_sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text.strip()) if sentence.strip()]


def _tokenise(text: str) -> set[str]:
    return {token for token in re.findall(r"\b[a-z0-9]+\b", text.lower()) if len(token) > 2}


def validate_narrative(narrative: str, evidence_blocks: list[dict[str, Any]], pii_fields: list[str]) -> dict[str, bool]:
    paragraphs = _split_paragraphs(narrative)
    words = re.findall(r"\b\w+\b", narrative)
    sentences = _split_sentences(narrative)
    narrative_lower = narrative.lower()

    section_keywords = ["background", "transactions", "typology", "evidence", "conclusion"]
    uncertain_terms = ["probably", "maybe", "unclear", "i think"]
    prohibited_patterns = [r"\bTODO\b", r"\bTBD\b", r"xx+", r"lorem ipsum"]

    pii_present = any((field or "").lower() in narrative_lower for field in pii_fields if field)
    placeholders_present = bool(re.search(r"\[[^\]]+\]|<BLANK>", narrative, flags=re.IGNORECASE))
    prohibited_present = any(re.search(pattern, narrative, flags=re.IGNORECASE) for pattern in prohibited_patterns)

    evidence_tokens = set()
    for block in evidence_blocks:
        evidence_tokens |= _tokenise(block.get("rule_name", ""))
        evidence_tokens |= _tokenise(block.get("observation", ""))
        evidence_tokens |= _tokenise((block.get("audit_reason") or {}).get("why_flagged", ""))

    checks = {
        "has_five_paragraphs": len(paragraphs) == 5,
        "word_count_in_range": 150 <= len(words) <= 600,
        "no_pii_in_narrative": not pii_present,
        "no_placeholders": not placeholders_present,
        "has_all_sections": all(keyword in narrative_lower for keyword in section_keywords),
        "no_uncertain_language": not any(term in narrative_lower for term in uncertain_terms),
        "sentence_count_above_minimum": len(sentences) > 5,
        "no_prohibited_patterns": not prohibited_present,
    }

    if evidence_tokens:
        checks["has_all_sections"] = checks["has_all_sections"] or bool(evidence_tokens & _tokenise(narrative))

    return checks


def score_sentences(narrative: str, evidence_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sentence_scores: list[dict[str, Any]] = []
    evidence_lookup: list[tuple[str, set[str]]] = []

    for block in evidence_blocks:
        rule_id = block.get("rule_id", "UNKNOWN")
        block_text = " ".join(
            [
                block.get("rule_name", ""),
                block.get("observation", ""),
                (block.get("audit_reason") or {}).get("why_flagged", ""),
            ]
        )
        evidence_lookup.append((rule_id, _tokenise(block_text)))

    for sentence in _split_sentences(narrative):
        sentence_tokens = _tokenise(sentence)
        best_rule = "UNMATCHED"
        best_score = 0.0

        for rule_id, tokens in evidence_lookup:
            if not sentence_tokens or not tokens:
                overlap_score = 0.0
            else:
                overlap = len(sentence_tokens & tokens)
                overlap_score = overlap / max(len(sentence_tokens), 1)
            if overlap_score > best_score:
                best_score = overlap_score
                best_rule = rule_id

        sentence_scores.append(
            {
                "sentence": sentence,
                "rule_id": best_rule,
                "score": round(min(max(best_score, 0.0), 1.0), 2),
                "flagged": best_score < 0.3,
            }
        )

    return sentence_scores

from pipeline_service import SarRagService, export_case_files, load_alert_from_file


def main() -> None:
    alert = load_alert_from_file()
    service = SarRagService()
    result = service.process_alert(alert)
    sar_path, audit_path = export_case_files(result)

    print("\n" + "=" * 50)
    print("FINAL SAR REPORT")
    print("=" * 50)
    print(json.dumps(result["final_sar"], indent=2))
    print(f"\nFinal SAR saved   -> {sar_path.name}")
    print(f"Audit Trail saved -> {audit_path.name}")


if __name__ == "__main__":
    main()