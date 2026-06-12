"""Explainable delivery models (Phase 4B)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ImpactLevel = Literal["none", "low", "medium", "high"]


@dataclass(frozen=True)
class EvidenceItem:
    source: str
    summary: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"source": self.source, "summary": self.summary}
        if self.detail:
            payload["detail"] = self.detail
        return payload


@dataclass(frozen=True)
class FileDecision:
    path: str
    why: list[str] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    confidence: float = 0.0
    rejected_alternatives: list[str] = field(default_factory=list)
    role: str = "implementation"

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "why": self.why,
            "evidence": [item.to_dict() for item in self.evidence],
            "confidence": round(self.confidence, 1),
            "rejectedAlternatives": self.rejected_alternatives,
            "role": self.role,
        }


@dataclass(frozen=True)
class RiskAssessment:
    database_impact: ImpactLevel = "none"
    api_impact: ImpactLevel = "none"
    ui_impact: ImpactLevel = "none"
    summary: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "databaseImpact": self.database_impact,
            "apiImpact": self.api_impact,
            "uiImpact": self.ui_impact,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class DecisionTrace:
    reasoning_summary: str
    overall_confidence: float
    file_decisions: list[FileDecision] = field(default_factory=list)
    rejected_alternatives: list[str] = field(default_factory=list)
    risk_assessment: RiskAssessment = field(default_factory=RiskAssessment)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reasoningSummary": self.reasoning_summary,
            "overallConfidence": round(self.overall_confidence, 1),
            "fileDecisions": [item.to_dict() for item in self.file_decisions],
            "rejectedAlternatives": self.rejected_alternatives,
            "riskAssessment": self.risk_assessment.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DecisionTrace:
        risk_payload = payload.get("riskAssessment") or {}
        file_decisions = []
        for item in payload.get("fileDecisions") or []:
            evidence = [
                EvidenceItem(
                    source=str(ev.get("source") or ""),
                    summary=str(ev.get("summary") or ""),
                    detail=str(ev.get("detail") or ""),
                )
                for ev in item.get("evidence") or []
            ]
            file_decisions.append(
                FileDecision(
                    path=str(item.get("path") or ""),
                    why=[str(line) for line in item.get("why") or []],
                    evidence=evidence,
                    confidence=float(item.get("confidence") or 0),
                    rejected_alternatives=[str(path) for path in item.get("rejectedAlternatives") or []],
                    role=str(item.get("role") or "implementation"),
                )
            )
        return cls(
            reasoning_summary=str(payload.get("reasoningSummary") or ""),
            overall_confidence=float(payload.get("overallConfidence") or 0),
            file_decisions=file_decisions,
            rejected_alternatives=[str(path) for path in payload.get("rejectedAlternatives") or []],
            risk_assessment=RiskAssessment(
                database_impact=str(risk_payload.get("databaseImpact") or "none"),  # type: ignore[arg-type]
                api_impact=str(risk_payload.get("apiImpact") or "none"),  # type: ignore[arg-type]
                ui_impact=str(risk_payload.get("uiImpact") or "none"),  # type: ignore[arg-type]
                summary=[str(line) for line in risk_payload.get("summary") or []],
            ),
        )
