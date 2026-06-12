"""Delivery Runtime API dependency injection."""

from __future__ import annotations

from dataclasses import dataclass

from delivery_runtime.events.store import EventStore
from delivery_runtime.gates.service import GateService
from delivery_runtime.mr_drafts.service import MrDraftService
from delivery_runtime.orchestration.engine import OrchestrationEngine
from delivery_runtime.pm_inbox.service import PmInboxService
from delivery_runtime.readiness.service import ReadinessService
from delivery_runtime.work_orders.service import WorkOrderService


@dataclass(frozen=True)
class DeliveryServices:
    readiness: ReadinessService
    work_orders: WorkOrderService
    events: EventStore
    gates: GateService
    orchestrator: OrchestrationEngine
    agent_bridge: object
    mr_drafts: MrDraftService
    pm_inbox: PmInboxService
    queue_consumer: object


_services: DeliveryServices | None = None


def configure(services: DeliveryServices) -> None:
    global _services
    _services = services


def get_services() -> DeliveryServices:
    if _services is None:
        raise RuntimeError("LivingColor Server is not bootstrapped")
    return _services
