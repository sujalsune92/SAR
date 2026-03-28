# from __future__ import annotations

# from datetime import datetime, timezone
# from io import BytesIO
# import re
# from typing import Any
# from uuid import uuid4

# from dotenv import load_dotenv
# from fastapi import Depends, FastAPI, Header, HTTPException
# from fastapi.encoders import jsonable_encoder
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import StreamingResponse
# from jose import JWTError, jwt
# from pydantic import BaseModel
# from reportlab.lib import colors
# from reportlab.lib.pagesizes import A4
# from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
# from reportlab.lib.units import cm
# from reportlab.pdfgen import canvas
# from reportlab.platypus import Frame, HRFlowable, PageBreak, PageTemplate, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# load_dotenv()

# from rag_pipeline.pipeline_service import SarRagService, build_text_diff, mask_alert

# from .database import append_audit_event, create_case, get_audit_events, get_case, init_db, list_cases, update_case
# from .schemas import AlertPayload, ReplayResponse, ReviewRequest

# app = FastAPI(title="SAR Narrative Generator API", version="1.0.0")

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://localhost:8080", "http://127.0.0.1:8080", "http://localhost:3000"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# service = SarRagService()

# JWT_SECRET_KEY = "sar-narrative-secret"
# JWT_ALGORITHM = "HS256"
# USERS = {
#     "analyst": {"password": "password123", "role": "analyst"},
#     "manager": {"password": "password123", "role": "manager"},
#     "admin": {"password": "password123", "role": "admin"},
# }


# def utc_now() -> str:
#     return datetime.now(timezone.utc).isoformat()


# def serialise(payload: Any) -> Any:
#     return jsonable_encoder(payload)


# def build_case_response(case_record: dict[str, Any]) -> dict[str, Any]:
#     response = serialise(case_record)
#     response["audit_events"] = serialise(get_audit_events(str(case_record["case_id"])))
#     return response


# class LoginRequest(BaseModel):
#     username: str
#     password: str


# def get_current_user(authorization: str = Header(default="")) -> dict[str, str]:
#     if not authorization or not authorization.startswith("Bearer "):
#         raise HTTPException(status_code=401, detail="Missing Bearer token")

#     token = authorization.replace("Bearer ", "", 1)
#     try:
#         payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
#     except JWTError as exc:
#         raise HTTPException(status_code=401, detail="Invalid token") from exc

#     username = payload.get("username")
#     role = payload.get("role")
#     if not username or not role:
#         raise HTTPException(status_code=401, detail="Invalid token payload")
#     return {"username": username, "role": role}


# def enrich_narrative_with_pii(narrative: str, alert_payload: dict[str, Any]) -> str:
#     customer_name = str(alert_payload.get("customer_name") or "N/A")
#     account_type = str(alert_payload.get("account_type") or "N/A")
#     customer_profile = str(alert_payload.get("customer_profile") or "N/A")

#     replacements = [
#         (r"\bthe\s+subject\b", customer_name),
#         (r"\bthe\s+account\s+holder\b", customer_name),
#         (r"\bthe\s+customer\b", customer_name),
#         (r"\ba\s+savings\s+account\b", f"{account_type} account"),
#         (r"\ba\s+student\b", customer_profile),
#     ]

#     enriched = narrative or ""
#     for pattern, replacement in replacements:
#         enriched = re.sub(pattern, replacement, enriched, flags=re.IGNORECASE)
#     return enriched


# class NumberedCanvas(canvas.Canvas):
#     def __init__(self, *args: Any, **kwargs: Any) -> None:
#         super().__init__(*args, **kwargs)
#         self._saved_page_states: list[dict[str, Any]] = []

#     def showPage(self) -> None:
#         self._saved_page_states.append(dict(self.__dict__))
#         self._startPage()

#     def save(self) -> None:
#         page_count = len(self._saved_page_states)
#         for state in self._saved_page_states:
#             self.__dict__.update(state)
#             self._draw_page_number(page_count)
#             super().showPage()
#         super().save()

#     def _draw_page_number(self, page_count: int) -> None:
#         self.saveState()
#         self.setFillColor(colors.HexColor("#6C757D"))
#         self.setFont("Helvetica", 8)
#         self.drawRightString(A4[0] - (2 * cm), 1.1 * cm, f"Page {self._pageNumber} of {page_count}")
#         self.restoreState()


# def _safe_value(value: Any) -> str:
#     if value is None:
#         return "N/A"
#     text = str(value).strip()
#     return text if text else "N/A"


# def _section_bar(title: str) -> Table:
#     bar = Table([[title]], colWidths=[A4[0] - (4 * cm)])
#     bar.setStyle(
#         TableStyle(
#             [
#                 ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#003366")),
#                 ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
#                 ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
#                 ("FONTSIZE", (0, 0), (-1, -1), 10),
#                 ("LEFTPADDING", (0, 0), (-1, -1), 4),
#                 ("RIGHTPADDING", (0, 0), (-1, -1), 4),
#                 ("TOPPADDING", (0, 0), (-1, -1), 4),
#                 ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
#             ]
#         )
#     )
#     return bar


# def _risk_color(risk_level: str) -> colors.Color:
#     level = (risk_level or "N/A").upper()
#     if level == "HIGH":
#         return colors.HexColor("#DC3545")
#     if level == "MEDIUM":
#         return colors.HexColor("#FD7E14")
#     if level == "LOW":
#         return colors.HexColor("#28A745")
#     return colors.black


# def _draw_footer(canvas_obj: canvas.Canvas, _: Any) -> None:
#     canvas_obj.saveState()
#     footer_gray = colors.HexColor("#6C757D")
#     y_line = 1.7 * cm

#     canvas_obj.setStrokeColor(footer_gray)
#     canvas_obj.setLineWidth(0.5)
#     canvas_obj.line(2 * cm, y_line, A4[0] - (2 * cm), y_line)

#     canvas_obj.setFillColor(footer_gray)
#     canvas_obj.setFont("Helvetica", 8)
#     canvas_obj.drawString(2 * cm, 1.15 * cm, "CONFIDENTIAL - NOT FOR DISTRIBUTION")
#     canvas_obj.drawCentredString(A4[0] / 2, 1.15 * cm, "SAR Narrative Generator - Barclays Hack-O-Hire 2026")
#     canvas_obj.restoreState()


# def _extract_narrative_sections(final_sar: dict[str, Any], alert_payload: dict[str, Any]) -> list[tuple[str, str]]:
#     narrative = final_sar.get("narrative", "")
#     default_titles = ["Background", "Transaction Summary", "Typology", "Evidence", "Conclusion"]

#     if isinstance(narrative, dict):
#         sections: list[tuple[str, str]] = []
#         for key, value in narrative.items():
#             section_heading = _safe_value(key)
#             section_text = enrich_narrative_with_pii(_safe_value(value), alert_payload)
#             sections.append((section_heading, section_text))
#         return sections

#     paragraphs = [p.strip() for p in str(narrative).split("\n\n") if p.strip()]
#     while len(paragraphs) < 5:
#         paragraphs.append("N/A")

#     return [
#         (title, enrich_narrative_with_pii(paragraphs[idx], alert_payload))
#         for idx, title in enumerate(default_titles)
#     ]


# def _build_pdf(case_record: dict[str, Any]) -> bytes:
#     final_sar = case_record.get("final_sar") or {}
#     alert_payload = case_record.get("alert_payload") or {}
#     evidence_pack = case_record.get("evidence_pack") or {}
#     validation_payload = case_record.get("validation_payload") or {}
#     analyst_review = case_record.get("analyst_review") or {}
#     prompt_payload = case_record.get("prompt_payload") or {}
#     retrieval_payload = case_record.get("retrieval_payload") or {}

#     customer_name = _safe_value(alert_payload.get("customer_name"))
#     customer_id = _safe_value(alert_payload.get("customer_id"))
#     account_type = _safe_value(alert_payload.get("account_type"))
#     alert_id = _safe_value(alert_payload.get("alert_id") or case_record.get("alert_id"))
#     alert_type = _safe_value(alert_payload.get("alert_type") or final_sar.get("alert_type"))
#     customer_profile = _safe_value(alert_payload.get("customer_profile"))

#     transactions = alert_payload.get("transactions") or {}
#     total_amount = _safe_value(transactions.get("total_amount"))
#     transaction_count = _safe_value(transactions.get("transaction_count"))
#     time_window_days = _safe_value(transactions.get("time_window_days"))
#     destination_country = _safe_value(transactions.get("destination_country"))

#     risk_level = _safe_value(case_record.get("risk_level") or final_sar.get("risk_level"))
#     risk_score = case_record.get("risk_score")
#     try:
#         risk_score_pct = f"{round(float(risk_score) * 100)}%"
#     except Exception:
#         risk_score_pct = "N/A"

#     generated_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

#     styles = getSampleStyleSheet()
#     body_style = ParagraphStyle("BodyHelvetica", parent=styles["BodyText"], fontName="Helvetica", fontSize=10, leading=14)
#     normal_9 = ParagraphStyle("Normal9", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=12)
#     bold_9 = ParagraphStyle("Bold9", parent=normal_9, fontName="Helvetica-Bold")
#     italic_8_gray = ParagraphStyle("Italic8Gray", parent=styles["Italic"], fontName="Helvetica-Oblique", fontSize=8, textColor=colors.HexColor("#6C757D"))

#     buffer = BytesIO()
#     doc = SimpleDocTemplate(
#         buffer,
#         pagesize=A4,
#         leftMargin=2 * cm,
#         rightMargin=2 * cm,
#         topMargin=2 * cm,
#         bottomMargin=2 * cm,
#     )

#     frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="content")
#     doc.addPageTemplates([PageTemplate(id="with-footer", frames=[frame], onPage=_draw_footer)])

#     flow: list[Any] = []

#     # PAGE 1 - HEADER
#     header = Table(
#         [[Paragraph("SUSPICIOUS ACTIVITY REPORT", ParagraphStyle("HeaderTitle", fontName="Helvetica-Bold", fontSize=16, textColor=colors.white)),
#           Paragraph("CONFIDENTIAL", ParagraphStyle("HeaderConf", fontName="Helvetica-Bold", fontSize=11, textColor=colors.HexColor("#DC3545"), alignment=2))]],
#         colWidths=[doc.width * 0.75, doc.width * 0.25],
#     )
#     header.setStyle(
#         TableStyle(
#             [
#                 ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#003366")),
#                 ("LEFTPADDING", (0, 0), (-1, -1), 6),
#                 ("RIGHTPADDING", (0, 0), (-1, -1), 6),
#                 ("TOPPADDING", (0, 0), (-1, -1), 8),
#                 ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
#             ]
#         )
#     )
#     flow.append(header)
#     flow.append(Spacer(1, 8))

#     risk_color = _risk_color(risk_level)
#     risk_color_text = "#28A745"
#     if risk_level.upper() == "HIGH":
#         risk_color_text = "#DC3545"
#     elif risk_level.upper() == "MEDIUM":
#         risk_color_text = "#FD7E14"
#     meta_left = Paragraph(f"<b>Case ID:</b> {_safe_value(case_record.get('case_id'))}<br/><b>Alert ID:</b> {alert_id}", normal_9)
#     meta_right = Paragraph(
#         f"<b>Generated:</b> {generated_date}<br/><b>Risk Level:</b> <font color='{risk_color_text}'>"
#         f"{risk_level}</font>",
#         normal_9,
#     )
#     meta_table = Table([[meta_left, meta_right]], colWidths=[doc.width * 0.5, doc.width * 0.5])
#     meta_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
#     flow.append(meta_table)
#     flow.append(Spacer(1, 6))
#     flow.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#003366")))
#     flow.append(Spacer(1, 12))

#     # PII NOTICE BOX
#     flow.append(_section_bar("Identity Verification Notice"))
#     pii_body = Paragraph(
#         "<b>Identity Verification Notice</b><br/>"
#         "PII fields were excluded from AI processing to prevent model exposure. "
#         "Personal details have been reinserted at export time from the original verified alert record only.",
#         normal_9,
#     )
#     pii_data = [
#         [Paragraph("Customer Name", bold_9), Paragraph("Customer ID", bold_9), Paragraph("Account Type", bold_9)],
#         [Paragraph(customer_name, normal_9), Paragraph(customer_id, normal_9), Paragraph(account_type, normal_9)],
#     ]
#     pii_inner = Table(pii_data, colWidths=[doc.width / 3, doc.width / 3, doc.width / 3])
#     pii_inner.setStyle(
#         TableStyle(
#             [
#                 ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#D4AF37")),
#                 ("LINEAFTER", (0, 0), (0, -1), 0.5, colors.HexColor("#D4AF37")),
#                 ("LINEAFTER", (1, 0), (1, -1), 0.5, colors.HexColor("#D4AF37")),
#                 ("LEFTPADDING", (0, 0), (-1, -1), 4),
#                 ("RIGHTPADDING", (0, 0), (-1, -1), 4),
#                 ("TOPPADDING", (0, 0), (-1, -1), 4),
#                 ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
#             ]
#         )
#     )
#     pii_outer = Table([[[pii_body, Spacer(1, 6), pii_inner]]], colWidths=[doc.width])
#     pii_outer.setStyle(
#         TableStyle(
#             [
#                 ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFFBE6")),
#                 ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E6C800")),
#                 ("LEFTPADDING", (0, 0), (-1, -1), 8),
#                 ("RIGHTPADDING", (0, 0), (-1, -1), 8),
#                 ("TOPPADDING", (0, 0), (-1, -1), 8),
#                 ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
#             ]
#         )
#     )
#     flow.append(pii_outer)
#     flow.append(Spacer(1, 12))

#     # SUBJECT & ACTIVITY SUMMARY
#     flow.append(_section_bar("Subject & Activity Summary"))
#     left_summary = (
#         f"<b>Alert Type:</b> {alert_type}<br/>"
#         f"<b>Customer Profile:</b> {customer_profile}<br/>"
#         f"<b>Account Type:</b> {account_type}"
#     )
#     right_summary = (
#         f"<b>Total Amount:</b> INR {total_amount}<br/>"
#         f"<b>Transaction Count:</b> {transaction_count}<br/>"
#         f"<b>Time Window:</b> {time_window_days} days<br/>"
#         f"<b>Destination:</b> {destination_country}"
#     )
#     summary_table = Table([[Paragraph(left_summary, normal_9), Paragraph(right_summary, normal_9)]], colWidths=[doc.width / 2, doc.width / 2])
#     summary_table.setStyle(
#         TableStyle(
#             [
#                 ("LEFTPADDING", (0, 0), (-1, -1), 0),
#                 ("RIGHTPADDING", (0, 0), (-1, -1), 0),
#                 ("TOPPADDING", (0, 0), (-1, -1), 4),
#                 ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
#             ]
#         )
#     )
#     flow.append(summary_table)
#     flow.append(Spacer(1, 12))

#     # TRIGGERED RULES TABLE
#     flow.append(_section_bar("Triggered AML Rules"))
#     rules = evidence_pack.get("rule_summary") or []
#     rules_data: list[list[Any]] = [["Rule ID", "Rule Name", "Confidence", "Contribution"]]
#     for rule in rules:
#         confidence_value = rule.get("confidence")
#         try:
#             confidence_pct = f"{round(float(confidence_value) * 100)}%"
#         except Exception:
#             confidence_pct = "N/A"
#         contribution = rule.get("contribution") or confidence_pct
#         rules_data.append([
#             _safe_value(rule.get("rule_id")),
#             _safe_value(rule.get("rule_name")),
#             confidence_pct,
#             _safe_value(contribution),
#         ])

#     rules_data.append(["Aggregate Risk Score", "", risk_score_pct, risk_level])
#     rules_table = Table(rules_data, colWidths=[70, 180, 80, 80])

#     rule_style = [
#         ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
#         ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE7F0")),
#         ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#C7CED6")),
#         ("ALIGN", (2, 1), (3, -1), "CENTER"),
#         ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
#     ]
#     for row_index in range(1, max(len(rules_data) - 1, 1)):
#         if row_index % 2 == 0:
#             rule_style.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#F5F5F5")))

#     aggregate_row = len(rules_data) - 1
#     rule_style.extend(
#         [
#             ("FONTNAME", (0, aggregate_row), (-1, aggregate_row), "Helvetica-Bold"),
#             ("BACKGROUND", (3, aggregate_row), (3, aggregate_row), _risk_color(risk_level)),
#             ("TEXTCOLOR", (3, aggregate_row), (3, aggregate_row), colors.white if risk_level.upper() != "MEDIUM" else colors.HexColor("#1F2937")),
#         ]
#     )
#     rules_table.setStyle(TableStyle(rule_style))
#     flow.append(rules_table)
#     flow.append(PageBreak())

#     # PAGE 2+ - PII REMINDER
#     flow.append(
#         Paragraph(
#             "Note: Narrative below contains reinserted identity fields not processed by the AI model.",
#             italic_8_gray,
#         )
#     )
#     flow.append(Spacer(1, 12))

#     # NARRATIVE SECTIONS
#     for title, section_text in _extract_narrative_sections(final_sar, alert_payload):
#         flow.append(_section_bar(title))
#         flow.append(Paragraph(_safe_value(section_text), body_style))
#         flow.append(Spacer(1, 12))

#     # ANALYST REVIEW BOX
#     flow.append(_section_bar("Analyst Review"))
#     decision = _safe_value(analyst_review.get("decision") or "PENDING")
#     if decision.upper() == "APPROVE":
#         decision_label = "APPROVED"
#         decision_color = colors.HexColor("#28A745")
#     elif decision.upper() == "REJECT":
#         decision_label = "REJECTED"
#         decision_color = colors.HexColor("#DC3545")
#     else:
#         decision_label = "PENDING REVIEW"
#         decision_color = colors.HexColor("#6C757D")

#     decision_box = Table([[decision_label]], colWidths=[doc.width])
#     decision_box.setStyle(
#         TableStyle(
#             [
#                 ("BACKGROUND", (0, 0), (-1, -1), decision_color),
#                 ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
#                 ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
#                 ("FONTSIZE", (0, 0), (-1, -1), 10),
#                 ("LEFTPADDING", (0, 0), (-1, -1), 6),
#                 ("TOPPADDING", (0, 0), (-1, -1), 4),
#                 ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
#             ]
#         )
#     )
#     flow.append(decision_box)
#     flow.append(Spacer(1, 6))

#     if analyst_review:
#         comment = _safe_value(analyst_review.get("comment"))
#         analyst_username = _safe_value(analyst_review.get("analyst_id"))
#         review_timestamp = _safe_value(analyst_review.get("submitted_at"))
#         flow.append(Paragraph(f"<b>Comment:</b> {comment}", normal_9))
#         flow.append(Paragraph(f"<b>Reviewed by:</b> {analyst_username}", normal_9))
#         flow.append(Paragraph(f"<b>Timestamp:</b> {review_timestamp}", normal_9))
#     else:
#         flow.append(Paragraph("Awaiting analyst review", italic_8_gray))
#     flow.append(Spacer(1, 12))

#     # AUDIT REFERENCE
#     flow.append(_section_bar("Audit & Reproducibility Reference"))
#     prompt_sha256 = _safe_value(prompt_payload.get("prompt_sha256") or prompt_payload.get("prompt_sha"))
#     corpus_snapshot = retrieval_payload.get("corpus_snapshot") if isinstance(retrieval_payload, dict) else {}
#     corpus_snapshot_id = _safe_value((corpus_snapshot or {}).get("snapshot_id"))
#     model_name = _safe_value(prompt_payload.get("model_name"))
#     temperature = _safe_value((prompt_payload.get("model_options") or {}).get("temperature"))
#     pipeline_version = _safe_value(case_record.get("pipeline_version") or prompt_payload.get("pipeline_version") or "1.0.0")

#     mono_style = ParagraphStyle("Mono8", parent=normal_9, fontName="Courier", fontSize=8, leading=10)
#     audit_rows = [
#         [Paragraph("Prompt SHA256:", bold_9), Paragraph(prompt_sha256, mono_style)],
#         [Paragraph("Corpus Snapshot:", bold_9), Paragraph(corpus_snapshot_id, normal_9)],
#         [Paragraph("Model:", bold_9), Paragraph(model_name, normal_9)],
#         [Paragraph("Temperature:", bold_9), Paragraph(temperature, normal_9)],
#         [Paragraph("Pipeline Version:", bold_9), Paragraph(pipeline_version, normal_9)],
#     ]
#     audit_table = Table(audit_rows, colWidths=[doc.width * 0.28, doc.width * 0.72])
#     audit_table.setStyle(
#         TableStyle(
#             [
#                 ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D0D7DE")),
#                 ("VALIGN", (0, 0), (-1, -1), "TOP"),
#                 ("LEFTPADDING", (0, 0), (-1, -1), 4),
#                 ("RIGHTPADDING", (0, 0), (-1, -1), 4),
#             ]
#         )
#     )
#     flow.append(audit_table)
#     flow.append(Spacer(1, 8))
#     flow.append(
#         Paragraph(
#             "This report was generated by an AI-assisted pipeline. The narrative was reviewed and approved by a qualified "
#             "compliance analyst. The full immutable audit trail is available by referencing the Case ID above.",
#             italic_8_gray,
#         )
#     )

#     doc.build(flow, canvasmaker=NumberedCanvas)
#     pdf_bytes = buffer.getvalue()
#     buffer.close()
#     return pdf_bytes


# @app.on_event("startup")
# def on_startup() -> None:
#     init_db()


# @app.get("/health")
# def health() -> dict[str, Any]:
#     return {
#         "status": "ok",
#         "service": "sar-narrative-generator",
#         "timestamp": utc_now(),
#     }


# @app.post("/login")
# def login(request: LoginRequest) -> dict[str, Any]:
#     user = USERS.get(request.username)
#     if not user or user["password"] != request.password:
#         raise HTTPException(status_code=401, detail="Invalid credentials")

#     payload = {
#         "username": request.username,
#         "role": user["role"],
#         "iat": int(datetime.now(timezone.utc).timestamp()),
#     }
#     token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
#     return {"access_token": token, "token_type": "bearer", "username": request.username, "role": user["role"]}


# @app.get("/cases")
# def get_cases(_: dict[str, str] = Depends(get_current_user)) -> list[dict[str, Any]]:
#     return serialise(list_cases())


# @app.post("/cases")
# def create_new_case(alert: AlertPayload, _: dict[str, str] = Depends(get_current_user)) -> dict[str, Any]:
#     alert_payload = serialise(alert)
#     case_id = str(uuid4())
#     masked_alert_payload = mask_alert(alert_payload)
#     create_case(case_id, alert_payload, masked_alert_payload)

#     try:
#         result = service.process_alert(alert_payload)
#     except Exception as exc:
#         update_case(case_id, status="FAILED")
#         append_audit_event(case_id, "CASE_FAILED", {"error": str(exc), "failed_at": utc_now()})
#         raise HTTPException(status_code=500, detail=f"Case processing failed: {exc}") from exc

#     update_case(
#         case_id,
#         alert_id=alert_payload["alert_id"],
#         status=result["status"],
#         risk_score=result["risk_score"],
#         risk_level=result["risk_level"],
#         masked_alert_payload=result["masked_alert"],
#         evidence_pack=result["evidence_pack"],
#         retrieval_payload=result["retrieval_payload"],
#         prompt_payload=result["prompt_payload"],
#         validation_payload=result["validation_payload"],
#         final_sar=result["final_sar"],
#     )
#     for event in result["audit_events"]:
#         append_audit_event(case_id, event["event_type"], serialise(event["payload"]))

#     case_record = get_case(case_id)
#     if case_record is None:
#         raise HTTPException(status_code=500, detail="Case was created but could not be reloaded.")
#     return build_case_response(case_record)


# @app.get("/cases/{case_id}")
# def get_case_detail(case_id: str, _: dict[str, str] = Depends(get_current_user)) -> dict[str, Any]:
#     case_record = get_case(case_id)
#     if case_record is None:
#         raise HTTPException(status_code=404, detail="Case not found.")
#     return build_case_response(case_record)


# @app.get("/cases/{case_id}/audit")
# def get_case_audit(case_id: str, _: dict[str, str] = Depends(get_current_user)) -> list[dict[str, Any]]:
#     case_record = get_case(case_id)
#     if case_record is None:
#         raise HTTPException(status_code=404, detail="Case not found.")
#     return serialise(get_audit_events(case_id))


# @app.post("/cases/{case_id}/review")
# def submit_review(case_id: str, request: ReviewRequest, _: dict[str, str] = Depends(get_current_user)) -> dict[str, Any]:
#     case_record = get_case(case_id)
#     if case_record is None:
#         raise HTTPException(status_code=404, detail="Case not found.")

#     final_sar = case_record.get("final_sar") or {}
#     original_narrative = final_sar.get("narrative", "")
#     updated_narrative = request.edited_narrative or original_narrative
#     review_status = "APPROVED" if request.decision == "APPROVE" else "REJECTED"
#     review_timestamp = utc_now()
#     edit_diff = build_text_diff(original_narrative, updated_narrative)

#     analyst_review = {
#         "analyst_id": request.analyst_id,
#         "decision": request.decision,
#         "comment": request.comment,
#         "submitted_at": review_timestamp,
#         "edit_diff": edit_diff,
#         "edited": updated_narrative != original_narrative,
#     }
#     final_sar["narrative"] = updated_narrative
#     final_sar["status"] = review_status
#     final_sar["reviewed_at"] = review_timestamp

#     update_case(case_id, status=review_status, analyst_review=analyst_review, final_sar=final_sar)
#     append_audit_event(case_id, "ANALYST_REVIEW_SUBMITTED", analyst_review)
#     if request.decision == "APPROVE":
#         append_audit_event(
#             case_id,
#             "EXPORT_TRIGGERED",
#             {
#                 "status": "LOCAL_EXPORT_READY",
#                 "comment": "Case approved in local workflow and ready for downstream export.",
#                 "triggered_at": review_timestamp,
#             },
#         )

#     refreshed_case = get_case(case_id)
#     if refreshed_case is None:
#         raise HTTPException(status_code=500, detail="Reviewed case could not be reloaded.")
#     return build_case_response(refreshed_case)


# @app.post("/cases/{case_id}/replay", response_model=ReplayResponse)
# def replay_case(case_id: str, _: dict[str, str] = Depends(get_current_user)) -> ReplayResponse:
#     case_record = get_case(case_id)
#     if case_record is None:
#         raise HTTPException(status_code=404, detail="Case not found.")

#     replay_payload = service.replay_case(serialise(case_record))
#     update_case(case_id, replay_payload=replay_payload)
#     append_audit_event(case_id, "CASE_REPLAYED", serialise(replay_payload))
#     return ReplayResponse(**serialise(replay_payload))


# @app.get("/cases/{case_id}/export/pdf")
# def export_case_pdf(case_id: str, _: dict[str, str] = Depends(get_current_user)) -> StreamingResponse:
#     case_record = get_case(case_id)
#     if case_record is None:
#         raise HTTPException(status_code=404, detail="Case not found.")

#     pdf_bytes = _build_pdf(case_record)
#     stream = BytesIO(pdf_bytes)
#     return StreamingResponse(
#         stream,
#         media_type="application/pdf",
#         headers={"Content-Disposition": f"attachment; filename=SAR_{case_id}.pdf"},
#     )
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
import re
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Frame, HRFlowable, PageBreak, PageTemplate,
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

load_dotenv()

from rag_pipeline.pipeline_service import SarRagService, build_text_diff, mask_alert

from .database import (
    append_audit_event, create_case, get_audit_events,
    get_case, init_db, list_cases, update_case,
)
from .schemas import AlertPayload, ReplayResponse, ReviewRequest

app = FastAPI(title="SAR Narrative Generator API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = SarRagService()

JWT_SECRET_KEY = "sar-narrative-secret"
JWT_ALGORITHM  = "HS256"
USERS = {
    "analyst": {"password": "password123", "role": "analyst"},
    "manager": {"password": "password123", "role": "manager"},
    "admin":   {"password": "password123", "role": "admin"},
}

# Annotation tags to strip before PDF rendering
_PDF_ANNOTATION_RE = re.compile(
    r"\s*\((FACT|COMPARISON|REASONING|EVIDENCE|ANALYSIS|NOTE)\)\s*",
    re.IGNORECASE,
)
# Enrichment bucket names to strip from PDF
_PDF_BUCKET_RE = re.compile(
    r"\b(high_velocity_txns|uae_transfers|uea_transfers|structuring_txns"
    r"|evidence\s*:\s*[\w_]+)\b",
    re.IGNORECASE,
)
# Evidence markers to strip from PDF
_PDF_EVIDENCE_MARKER_RE = re.compile(
    r"\[(?:E\d+|TXN:[^\]]+|evidence:[^\]]+)\]",
    re.IGNORECASE,
)
# ISO timestamp pattern → analyst-friendly date
_ISO_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)?"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialise(payload: Any) -> Any:
    return jsonable_encoder(payload)


def build_case_response(case_record: dict[str, Any]) -> dict[str, Any]:
    response = serialise(case_record)
    response["audit_events"] = serialise(get_audit_events(str(case_record["case_id"])))
    return response


class LoginRequest(BaseModel):
    username: str
    password: str


def get_current_user(authorization: str = Header(default="")) -> dict[str, str]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.replace("Bearer ", "", 1)
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    username = payload.get("username")
    role     = payload.get("role")
    if not username or not role:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return {"username": username, "role": role}


def _sanitise_for_pdf(text: str, alert_payload: dict[str, Any]) -> str:
    """
    Defence-in-depth sanitisation before any text enters the PDF renderer.

    Strips:
      - (FACT) / (COMPARISON) / (REASONING) annotation tags
      - enrichment bucket names (high_velocity_txns, uae_transfers, etc.)
      - evidence markers ([E1], [TXN:xxx])
      - raw customer name and ID
      - JSON structure (extracts prose if a paragraph is a JSON object)

    Converts:
      - ISO timestamps → analyst-friendly "DD Mon YYYY HH:MM UTC"
    """
    if not text:
        return text

    # Strip annotation tags
    text = _PDF_ANNOTATION_RE.sub(" ", text)

    # Strip enrichment bucket names
    text = _PDF_BUCKET_RE.sub("", text)

    # Strip evidence markers
    text = _PDF_EVIDENCE_MARKER_RE.sub("", text)

    # Strip customer name and ID
    customer_name = str(alert_payload.get("customer_name") or "")
    customer_id   = str(alert_payload.get("customer_id") or "")
    if customer_name and customer_name != "N/A":
        text = re.sub(re.escape(customer_name), "the account holder", text, flags=re.IGNORECASE)
    if customer_id and customer_id != "N/A":
        text = re.sub(re.escape(customer_id), "", text, flags=re.IGNORECASE)

    # Extract prose from JSON if whole paragraph was serialised as JSON
    if text.strip().startswith("{"):
        try:
            obj = json.loads(text.strip())
            for key in ("sentence", "text", "content", "narrative"):
                if key in obj and isinstance(obj[key], str):
                    text = obj[key]
                    break
        except (json.JSONDecodeError, ValueError):
            pass

    # Convert ISO timestamps to analyst-friendly format
    def _fmt_ts(m: re.Match) -> str:
        try:
            dt = datetime.fromisoformat(m.group(0).replace("Z", "+00:00"))
            return dt.strftime("%d %b %Y %H:%M UTC")
        except ValueError:
            return m.group(0)

    text = _ISO_TIMESTAMP_RE.sub(_fmt_ts, text)

    # Tidy up double spaces
    text = re.sub(r"  +", " ", text).strip()
    return text


def enrich_narrative_with_pii(narrative: str, alert_payload: dict[str, Any]) -> str:
    """
    Re-insert customer name at export time ONLY for the PDF.
    The narrative was processed with 'the account holder' throughout.
    We replace that placeholder with the real name for the final document.
    """
    customer_name    = str(alert_payload.get("customer_name") or "N/A")
    account_type     = str(alert_payload.get("account_type") or "N/A")
    customer_profile = str(alert_payload.get("customer_profile") or "N/A")

    replacements = [
        (r"\bthe\s+account\s+holder\b", customer_name),
        (r"\bthe\s+subject\b",           customer_name),
        (r"\bthe\s+customer\b",          customer_name),
        (r"\ba\s+savings\s+account\b",   f"{account_type} account"),
        (r"\ba\s+student\b",             customer_profile),
    ]

    enriched = narrative or ""
    for pattern, replacement in replacements:
        enriched = re.sub(pattern, replacement, enriched, flags=re.IGNORECASE)
    return enriched


def _extract_narrative_sections(
    final_sar: dict[str, Any],
    alert_payload: dict[str, Any],
) -> list[tuple[str, str]]:
    """
    Extract (title, prose) tuples for PDF rendering.
    Handles plain-prose narrative, dict narrative, and JSON-line narrative.
    Applies _sanitise_for_pdf then enrich_narrative_with_pii on each section.
    """
    narrative = final_sar.get("narrative", "")
    default_titles = ["Background", "Transaction Summary", "Typology", "Evidence", "Conclusion"]

    # Case 1: narrative is already a dict keyed by section name
    if isinstance(narrative, dict):
        sections: list[tuple[str, str]] = []
        for key, value in narrative.items():
            raw = _safe_value(value)
            clean = _sanitise_for_pdf(raw, alert_payload)
            enriched = enrich_narrative_with_pii(clean, alert_payload)
            sections.append((_safe_value(key), enriched))
        return sections

    # Case 2: string narrative — may be plain prose, JSON lines, or numbered
    narrative_str = str(narrative)

    # Try to split into 5 paragraphs
    # Reuse the same logic as pipeline_service.split_paragraphs
    paragraphs: list[str] = []

    # Try blank-line split first
    by_blank = [p.strip() for p in narrative_str.split("\n\n") if p.strip()]
    if len(by_blank) == 5:
        paragraphs = by_blank
    else:
        # Try numbered split
        numbered_split = re.split(r"\n(?=\d+[\.\)]\s)", narrative_str.strip())
        by_number = [re.sub(r"^\d+[\.\)]\s*", "", p).strip()
                     for p in numbered_split if p.strip()]
        if len(by_number) == 5:
            paragraphs = by_number
        else:
            # Use whatever we have, pad to 5
            paragraphs = by_blank if len(by_blank) >= len(by_number) else by_number

    while len(paragraphs) < 5:
        paragraphs.append("N/A")

    result: list[tuple[str, str]] = []
    for idx, title in enumerate(default_titles):
        raw   = paragraphs[idx] if idx < len(paragraphs) else "N/A"
        clean = _sanitise_for_pdf(raw, alert_payload)
        enriched = enrich_narrative_with_pii(clean, alert_payload)
        result.append((title, enriched))
    return result


# ─── PDF helpers (unchanged from original) ───────────────────────────────────

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_number(page_count)
            super().showPage()
        super().save()

    def _draw_page_number(self, page_count: int) -> None:
        self.saveState()
        self.setFillColor(colors.HexColor("#6C757D"))
        self.setFont("Helvetica", 8)
        self.drawRightString(A4[0] - (2 * cm), 1.1 * cm, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


def _safe_value(value: Any) -> str:
    if value is None:
        return "N/A"
    text = str(value).strip()
    return text if text else "N/A"


def _section_bar(title: str) -> Table:
    bar = Table([[title]], colWidths=[A4[0] - (4 * cm)])
    bar.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#003366")),
        ("TEXTCOLOR",     (0, 0), (-1, -1), colors.white),
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return bar


def _risk_color(risk_level: str) -> colors.Color:
    level = (risk_level or "N/A").upper()
    if level == "HIGH":   return colors.HexColor("#DC3545")
    if level == "MEDIUM": return colors.HexColor("#FD7E14")
    if level == "LOW":    return colors.HexColor("#28A745")
    return colors.black


def _draw_footer(canvas_obj: canvas.Canvas, _: Any) -> None:
    canvas_obj.saveState()
    footer_gray = colors.HexColor("#6C757D")
    y_line = 1.7 * cm
    canvas_obj.setStrokeColor(footer_gray)
    canvas_obj.setLineWidth(0.5)
    canvas_obj.line(2 * cm, y_line, A4[0] - (2 * cm), y_line)
    canvas_obj.setFillColor(footer_gray)
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.drawString(2 * cm, 1.15 * cm, "CONFIDENTIAL - NOT FOR DISTRIBUTION")
    canvas_obj.drawCentredString(A4[0] / 2, 1.15 * cm, "SAR Narrative Generator - Barclays Hack-O-Hire 2026")
    canvas_obj.restoreState()


def _build_pdf(case_record: dict[str, Any]) -> bytes:
    final_sar        = case_record.get("final_sar") or {}
    alert_payload    = case_record.get("alert_payload") or {}
    evidence_pack    = case_record.get("evidence_pack") or {}
    analyst_review   = case_record.get("analyst_review") or {}
    prompt_payload   = case_record.get("prompt_payload") or {}
    retrieval_payload = case_record.get("retrieval_payload") or {}

    customer_name    = _safe_value(alert_payload.get("customer_name"))
    customer_id      = _safe_value(alert_payload.get("customer_id"))
    account_type     = _safe_value(alert_payload.get("account_type"))
    alert_id         = _safe_value(alert_payload.get("alert_id") or case_record.get("alert_id"))
    alert_type       = _safe_value(alert_payload.get("alert_type") or final_sar.get("alert_type"))
    customer_profile = _safe_value(alert_payload.get("customer_profile"))

    transactions      = alert_payload.get("transactions") or {}
    total_amount      = _safe_value(transactions.get("total_amount"))
    transaction_count = _safe_value(transactions.get("transaction_count"))
    time_window_days  = _safe_value(transactions.get("time_window_days"))
    destination_country = _safe_value(transactions.get("destination_country"))

    risk_level = _safe_value(case_record.get("risk_level") or final_sar.get("risk_level"))
    risk_score = case_record.get("risk_score")
    try:
        risk_score_pct = f"{round(float(risk_score) * 100)}%"
    except Exception:
        risk_score_pct = "N/A"

    generated_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    styles    = getSampleStyleSheet()
    body_style = ParagraphStyle("BodyHelvetica", parent=styles["BodyText"],
                                fontName="Helvetica", fontSize=10, leading=14)
    normal_9   = ParagraphStyle("Normal9", parent=styles["Normal"],
                                fontName="Helvetica", fontSize=9, leading=12)
    bold_9     = ParagraphStyle("Bold9", parent=normal_9, fontName="Helvetica-Bold")
    italic_8_gray = ParagraphStyle("Italic8Gray", parent=styles["Italic"],
                                   fontName="Helvetica-Oblique", fontSize=8,
                                   textColor=colors.HexColor("#6C757D"))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm,  bottomMargin=2*cm,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="content")
    doc.addPageTemplates([PageTemplate(id="with-footer", frames=[frame], onPage=_draw_footer)])

    flow: list[Any] = []

    # Header
    header = Table(
        [[Paragraph("SUSPICIOUS ACTIVITY REPORT",
                    ParagraphStyle("HeaderTitle", fontName="Helvetica-Bold",
                                   fontSize=16, textColor=colors.white)),
          Paragraph("CONFIDENTIAL",
                    ParagraphStyle("HeaderConf", fontName="Helvetica-Bold",
                                   fontSize=11, textColor=colors.HexColor("#DC3545"),
                                   alignment=2))]],
        colWidths=[doc.width * 0.75, doc.width * 0.25],
    )
    header.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#003366")),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    flow.append(header)
    flow.append(Spacer(1, 8))

    risk_color_text = "#28A745"
    if risk_level.upper() == "HIGH":   risk_color_text = "#DC3545"
    elif risk_level.upper() == "MEDIUM": risk_color_text = "#FD7E14"

    meta_left  = Paragraph(f"<b>Case ID:</b> {_safe_value(case_record.get('case_id'))}<br/>"
                           f"<b>Alert ID:</b> {alert_id}", normal_9)
    meta_right = Paragraph(f"<b>Generated:</b> {generated_date}<br/>"
                           f"<b>Risk Level:</b> <font color='{risk_color_text}'>{risk_level}</font>",
                           normal_9)
    meta_table = Table([[meta_left, meta_right]], colWidths=[doc.width*0.5, doc.width*0.5])
    meta_table.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    flow.append(meta_table)
    flow.append(Spacer(1, 6))
    flow.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#003366")))
    flow.append(Spacer(1, 12))

    # PII notice
    flow.append(_section_bar("Identity Verification Notice"))
    pii_body = Paragraph(
        "<b>Identity Verification Notice</b><br/>"
        "PII fields were excluded from AI processing to prevent model exposure. "
        "Personal details have been reinserted at export time from the original verified alert record only.",
        normal_9,
    )
    pii_data = [
        [Paragraph("Customer Name", bold_9), Paragraph("Customer ID", bold_9), Paragraph("Account Type", bold_9)],
        [Paragraph(customer_name, normal_9), Paragraph(customer_id, normal_9), Paragraph(account_type, normal_9)],
    ]
    pii_inner = Table(pii_data, colWidths=[doc.width/3]*3)
    pii_inner.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#D4AF37")),
        ("LINEAFTER", (0, 0), (0, -1), 0.5, colors.HexColor("#D4AF37")),
        ("LINEAFTER", (1, 0), (1, -1), 0.5, colors.HexColor("#D4AF37")),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    pii_outer = Table([[[pii_body, Spacer(1, 6), pii_inner]]], colWidths=[doc.width])
    pii_outer.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#FFFBE6")),
        ("BOX",           (0, 0), (-1, -1), 0.5, colors.HexColor("#E6C800")),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    flow.append(pii_outer)
    flow.append(Spacer(1, 12))

    # Activity summary
    flow.append(_section_bar("Subject & Activity Summary"))
    left_summary = (f"<b>Alert Type:</b> {alert_type}<br/>"
                    f"<b>Customer Profile:</b> {customer_profile}<br/>"
                    f"<b>Account Type:</b> {account_type}")
    right_summary = (f"<b>Total Amount:</b> INR {total_amount}<br/>"
                     f"<b>Transaction Count:</b> {transaction_count}<br/>"
                     f"<b>Time Window:</b> {time_window_days} days<br/>"
                     f"<b>Destination:</b> {destination_country}")
    summary_table = Table([[Paragraph(left_summary, normal_9), Paragraph(right_summary, normal_9)]],
                          colWidths=[doc.width/2]*2)
    summary_table.setStyle(TableStyle([
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    flow.append(summary_table)
    flow.append(Spacer(1, 12))

    # Rules table
    flow.append(_section_bar("Triggered AML Rules"))
    rules = evidence_pack.get("rule_summary") or []
    rules_data: list[list[Any]] = [["Rule ID", "Rule Name", "Confidence", "Contribution"]]
    for rule in rules:
        cv = rule.get("confidence")
        try:
            cpct = f"{round(float(cv) * 100)}%"
        except Exception:
            cpct = "N/A"
        rules_data.append([
            _safe_value(rule.get("rule_id")),
            _safe_value(rule.get("rule_name")),
            cpct,
            _safe_value(rule.get("contribution") or cpct),
        ])
    rules_data.append(["Aggregate Risk Score", "", risk_score_pct, risk_level])
    rules_table = Table(rules_data, colWidths=[70, 180, 80, 80])
    rule_style = [
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND",  (0, 0), (-1, 0), colors.HexColor("#DDE7F0")),
        ("GRID",        (0, 0), (-1, -1), 0.5, colors.HexColor("#C7CED6")),
        ("ALIGN",       (2, 1), (3, -1), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i in range(1, max(len(rules_data) - 1, 1)):
        if i % 2 == 0:
            rule_style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F5F5F5")))
    agg = len(rules_data) - 1
    rule_style.extend([
        ("FONTNAME",    (0, agg), (-1, agg), "Helvetica-Bold"),
        ("BACKGROUND",  (3, agg), (3, agg), _risk_color(risk_level)),
        ("TEXTCOLOR",   (3, agg), (3, agg),
         colors.white if risk_level.upper() != "MEDIUM" else colors.HexColor("#1F2937")),
    ])
    rules_table.setStyle(TableStyle(rule_style))
    flow.append(rules_table)
    flow.append(PageBreak())

    # Narrative sections
    flow.append(Paragraph(
        "Note: Narrative below contains reinserted identity fields not processed by the AI model.",
        italic_8_gray,
    ))
    flow.append(Spacer(1, 12))

    for title, section_text in _extract_narrative_sections(final_sar, alert_payload):
        flow.append(_section_bar(title))
        flow.append(Paragraph(_safe_value(section_text), body_style))
        flow.append(Spacer(1, 12))

    # Analyst review — dynamic label based on actual decision
    flow.append(_section_bar("Analyst Review"))
    decision = _safe_value(analyst_review.get("decision") or "PENDING")
    if decision.upper() == "APPROVE":
        decision_label, decision_color = "APPROVED", colors.HexColor("#28A745")
    elif decision.upper() == "REJECT":
        decision_label, decision_color = "REJECTED", colors.HexColor("#DC3545")
    else:
        decision_label, decision_color = "PENDING REVIEW", colors.HexColor("#6C757D")

    decision_box = Table([[decision_label]], colWidths=[doc.width])
    decision_box.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), decision_color),
        ("TEXTCOLOR",     (0, 0), (-1, -1), colors.white),
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    flow.append(decision_box)
    flow.append(Spacer(1, 6))

    if analyst_review:
        flow.append(Paragraph(f"<b>Comment:</b> {_safe_value(analyst_review.get('comment'))}", normal_9))
        flow.append(Paragraph(f"<b>Reviewed by:</b> {_safe_value(analyst_review.get('analyst_id'))}", normal_9))
        flow.append(Paragraph(f"<b>Timestamp:</b> {_safe_value(analyst_review.get('submitted_at'))}", normal_9))
    else:
        flow.append(Paragraph("Awaiting analyst review", italic_8_gray))
    flow.append(Spacer(1, 12))

    # Audit reference
    flow.append(_section_bar("Audit & Reproducibility Reference"))
    prompt_sha256    = _safe_value(prompt_payload.get("prompt_sha256") or prompt_payload.get("prompt_sha"))
    corpus_snapshot  = retrieval_payload.get("corpus_snapshot") if isinstance(retrieval_payload, dict) else {}
    corpus_snapshot_id = _safe_value((corpus_snapshot or {}).get("snapshot_id"))
    model_name       = _safe_value(prompt_payload.get("model_name"))
    temperature      = _safe_value((prompt_payload.get("model_options") or {}).get("temperature"))
    pipeline_version = _safe_value(case_record.get("pipeline_version") or
                                   prompt_payload.get("pipeline_version") or "1.0.0")

    mono_style = ParagraphStyle("Mono8", parent=normal_9, fontName="Courier", fontSize=8, leading=10)
    audit_rows = [
        [Paragraph("Prompt SHA256:",     bold_9), Paragraph(prompt_sha256,      mono_style)],
        [Paragraph("Corpus Snapshot:",   bold_9), Paragraph(corpus_snapshot_id, normal_9)],
        [Paragraph("Model:",             bold_9), Paragraph(model_name,         normal_9)],
        [Paragraph("Temperature:",       bold_9), Paragraph(temperature,        normal_9)],
        [Paragraph("Pipeline Version:",  bold_9), Paragraph(pipeline_version,   normal_9)],
    ]
    audit_table = Table(audit_rows, colWidths=[doc.width * 0.28, doc.width * 0.72])
    audit_table.setStyle(TableStyle([
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#D0D7DE")),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
    ]))
    flow.append(audit_table)
    flow.append(Spacer(1, 8))
    flow.append(Paragraph(
        "This report was generated by an AI-assisted pipeline. "
        "The narrative was reviewed and approved by a qualified compliance analyst. "
        "The full immutable audit trail is available by referencing the Case ID above.",
        italic_8_gray,
    ))

    doc.build(flow, canvasmaker=NumberedCanvas)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


# ─── API routes ───────────────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "sar-narrative-generator", "timestamp": utc_now()}


@app.post("/login")
def login(request: LoginRequest) -> dict[str, Any]:
    user = USERS.get(request.username)
    if not user or user["password"] != request.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    payload = {
        "username": request.username,
        "role": user["role"],
        "iat": int(datetime.now(timezone.utc).timestamp()),
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return {"access_token": token, "token_type": "bearer",
            "username": request.username, "role": user["role"]}


@app.get("/cases")
def get_cases(_: dict[str, str] = Depends(get_current_user)) -> list[dict[str, Any]]:
    return serialise(list_cases())


@app.post("/cases")
def create_new_case(alert: AlertPayload, _: dict[str, str] = Depends(get_current_user)) -> dict[str, Any]:
    alert_payload = serialise(alert)
    case_id = str(uuid4())
    masked_alert_payload = mask_alert(alert_payload)
    create_case(case_id, alert_payload, masked_alert_payload)

    try:
        result = service.process_alert(alert_payload)
    except Exception as exc:
        update_case(case_id, status="FAILED")
        append_audit_event(case_id, "CASE_FAILED", {"error": str(exc), "failed_at": utc_now()})
        raise HTTPException(status_code=500, detail=f"Case processing failed: {exc}") from exc

    update_case(
        case_id,
        alert_id=alert_payload["alert_id"],
        status=result["status"],
        risk_score=result["risk_score"],
        risk_level=result["risk_level"],
        masked_alert_payload=result["masked_alert"],
        evidence_pack=result["evidence_pack"],
        retrieval_payload=result["retrieval_payload"],
        prompt_payload=result["prompt_payload"],
        validation_payload=result["validation_payload"],
        final_sar=result["final_sar"],
    )
    for event in result["audit_events"]:
        append_audit_event(case_id, event["event_type"], serialise(event["payload"]))

    case_record = get_case(case_id)
    if case_record is None:
        raise HTTPException(status_code=500, detail="Case was created but could not be reloaded.")
    return build_case_response(case_record)


@app.get("/cases/{case_id}")
def get_case_detail(case_id: str, _: dict[str, str] = Depends(get_current_user)) -> dict[str, Any]:
    case_record = get_case(case_id)
    if case_record is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    return build_case_response(case_record)


@app.get("/cases/{case_id}/audit")
def get_case_audit(case_id: str, _: dict[str, str] = Depends(get_current_user)) -> list[dict[str, Any]]:
    case_record = get_case(case_id)
    if case_record is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    return serialise(get_audit_events(case_id))


@app.post("/cases/{case_id}/review")
def submit_review(
    case_id: str,
    request: ReviewRequest,
    _: dict[str, str] = Depends(get_current_user),
) -> dict[str, Any]:
    case_record = get_case(case_id)
    if case_record is None:
        raise HTTPException(status_code=404, detail="Case not found.")

    final_sar = case_record.get("final_sar") or {}
    original_narrative = final_sar.get("narrative", "")
    updated_narrative  = request.edited_narrative or original_narrative
    review_status      = "APPROVED" if request.decision == "APPROVE" else "REJECTED"
    review_timestamp   = utc_now()
    edit_diff          = build_text_diff(original_narrative, updated_narrative)

    analyst_review = {
        "analyst_id":  request.analyst_id,
        "decision":    request.decision,
        "comment":     request.comment,
        "submitted_at": review_timestamp,
        "edit_diff":   edit_diff,
        "edited":      updated_narrative != original_narrative,
    }
    final_sar["narrative"]    = updated_narrative
    final_sar["status"]       = review_status
    final_sar["reviewed_at"]  = review_timestamp

    update_case(case_id, status=review_status, analyst_review=analyst_review, final_sar=final_sar)
    append_audit_event(case_id, "ANALYST_REVIEW_SUBMITTED", analyst_review)
    if request.decision == "APPROVE":
        append_audit_event(case_id, "EXPORT_TRIGGERED", {
            "status": "LOCAL_EXPORT_READY",
            "comment": "Case approved and ready for downstream export.",
            "triggered_at": review_timestamp,
        })

    refreshed_case = get_case(case_id)
    if refreshed_case is None:
        raise HTTPException(status_code=500, detail="Reviewed case could not be reloaded.")
    return build_case_response(refreshed_case)


@app.post("/cases/{case_id}/replay", response_model=ReplayResponse)
def replay_case(case_id: str, _: dict[str, str] = Depends(get_current_user)) -> ReplayResponse:
    case_record = get_case(case_id)
    if case_record is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    replay_payload = service.replay_case(serialise(case_record))
    update_case(case_id, replay_payload=replay_payload)
    append_audit_event(case_id, "CASE_REPLAYED", serialise(replay_payload))
    return ReplayResponse(**serialise(replay_payload))


@app.get("/cases/{case_id}/export/pdf")
def export_case_pdf(case_id: str, _: dict[str, str] = Depends(get_current_user)) -> StreamingResponse:
    case_record = get_case(case_id)
    if case_record is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    pdf_bytes = _build_pdf(case_record)
    stream = BytesIO(pdf_bytes)
    return StreamingResponse(
        stream,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=SAR_{case_id}.pdf"},
    )