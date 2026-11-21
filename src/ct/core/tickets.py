"""Demand-weighted repair queue ticketing for Charger Truth.

Pure Python, no Kafka or Condense dependencies.

Priority formula:
priority = (1 - p) * local_demand_rate

When a cluster alert fires, produces ONE grouped ticket with a heuristic
first-check hint, preventing ticket storms.
"""
from __future__ import annotations

from typing import Dict, List, Optional
from ct.config import Config
from ct.schemas import (
    ClusterAlertEvent,
    GroupType,
    OpsTicketEvent,
    TargetType,
    TicketStatus,
)


class TicketManager:
    """Manages maintenance repair tickets and ranks the repair queue."""
    def __init__(self, config: Config):
        self.config = config
        self.tickets: Dict[str, OpsTicketEvent] = {}
        self.ticket_counter = 1

    def create_connector_ticket(
        self,
        connector_id: str,
        site_id: str,
        p_start: float,
        local_demand_rate: float,
        event_ts: int,
        primary_symptom: str = "timeout",
    ) -> OpsTicketEvent:
        """Create or update single connector repair ticket ranked by (1 - p) * demand."""
        priority = round((1.0 - p_start) * local_demand_rate, 2)

        if primary_symptom == "timeout":
            hint = (
                "[Heuristic] Dead-end behavior: reports Available but triggers repeated "
                "handshake timeouts. Check pilot contactors, cable isolation, and RFID/app auth."
            )
        elif primary_symptom == "power":
            hint = (
                "[Heuristic] Power degradation: delivers <60% of nameplate rating. "
                "Check rectifier modules, power cabinet cooling, and cable temp sensors."
            )
        else:
            hint = (
                "[Heuristic] Unreachable connector: check local site controller, cellular modem, "
                "and AC breaker supply."
            )

        ticket_id = f"tkt_conn_{connector_id}"
        ticket = OpsTicketEvent(
            event_ts=event_ts,
            ticket_id=ticket_id,
            target_type=TargetType.CONNECTOR,
            target_id=connector_id,
            site_id=site_id,
            priority=priority,
            demand_rate=round(local_demand_rate, 2),
            p_start=round(p_start, 3),
            heuristic_hint=hint,
            cluster_alert_id=None,
            status=TicketStatus.OPEN,
        )
        self.tickets[ticket_id] = ticket
        return ticket

    def create_cluster_ticket(
        self,
        alert: ClusterAlertEvent,
        average_local_demand: float = 4.0,
    ) -> OpsTicketEvent:
        """Create ONE grouped repair ticket for a correlated failure cluster."""
        num_members = len(alert.member_connector_ids)
        # Cluster priority scales with number of affected connectors and observed failure severity
        failure_fraction = alert.observed_failures / max(1, alert.observed_failures + 2)
        total_demand = num_members * average_local_demand
        priority = round(failure_fraction * total_demand, 2)

        if alert.group_type == GroupType.OPERATOR:
            hint = (
                f"[Heuristic] Correlated operator outage across multiple sites for operator {alert.group_key}. "
                "Investigate central OCPP message gateway, cloud API availability, and authentication backend."
            )
        elif alert.group_type == GroupType.FIRMWARE:
            hint = (
                f"[Heuristic] Correlated failure burst across chargers running firmware {alert.group_key}. "
                "Investigate recent firmware rollout for memory leaks, CAN bus timing bugs, or state machine hangs."
            )
        elif alert.group_type == GroupType.OPERATOR_X_FIRMWARE:
            hint = (
                f"[Heuristic] Protocol incompatibility on {alert.group_key}. "
                "Check OCPP 1.6J/2.0.1 schema validation and TLS certificate chain expiration."
            )
        elif alert.group_type == GroupType.SITE:
            hint = (
                f"[Heuristic] Multi-connector simultaneous failure at site {alert.group_key}. "
                "Check local substation transformer, main AC breaker trip, or site network switch."
            )
        else:
            hint = "[Heuristic] Multi-connector cluster fault. Check common power and comms infrastructure."

        ticket_id = f"tkt_cluster_{alert.group_type.value}_{alert.group_key}"
        ticket = OpsTicketEvent(
            event_ts=alert.event_ts,
            ticket_id=ticket_id,
            target_type=TargetType.CLUSTER,
            target_id=alert.group_key,
            site_id=alert.group_key if alert.group_type == GroupType.SITE else None,
            priority=priority,
            demand_rate=round(total_demand, 2),
            p_start=round(1.0 - failure_fraction, 3),
            heuristic_hint=hint,
            cluster_alert_id=alert.alert_id,
            status=TicketStatus.OPEN,
        )
        self.tickets[ticket_id] = ticket
        return ticket

    def get_ranked_repair_queue(self) -> List[OpsTicketEvent]:
        """Return open and in-progress tickets sorted by descending priority."""
        open_tickets = [
            t for t in self.tickets.values()
            if t.status in (TicketStatus.OPEN, TicketStatus.IN_PROGRESS)
        ]
        open_tickets.sort(key=lambda t: t.priority, reverse=True)
        return open_tickets
