"""Online belief estimation for EV charger connectors.

Pure Python and numpy, no Kafka or Condense dependencies.

Implements:
- Step A: Beta-Bernoulli estimator with exponential forgetting.
- Step B: 4-state Hidden Markov Model forward filter O(1) per event.
- Group pooling integration via GroupPooler.
- Active probing candidate generation.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from ct.config import Config
from ct.core.pooling import GroupPooler
from ct.schemas import (
    ChargerStatusEvent,
    ConnectorBeliefEvent,
    ReportedStatus,
    SessionOutcome,
    TOPIC_CONNECTOR_BELIEF,
    VehicleRequestEvent,
    VehicleSessionEvent,
)


class BaseBeliefEstimator(ABC):
    """Abstract interface for connector belief estimators."""
    @abstractmethod
    def update(self, event: Any) -> None:
        """Process an observable streaming event (ChargerStatusEvent or VehicleSessionEvent)."""
        pass

    @abstractmethod
    def p_start(self, connector_id: str, now: int) -> float:
        """Estimated probability that the next charging session starts successfully."""
        pass

    @abstractmethod
    def state_probs(self, connector_id: str, now: int) -> Dict[str, float]:
        """Posterior probabilities for each hidden state."""
        pass

    @abstractmethod
    def uncertainty(self, connector_id: str, now: int) -> float:
        """Normalized Shannon entropy in [0.0, 1.0]."""
        pass

    @abstractmethod
    def probe_candidates(self, request: VehicleRequestEvent, now: int) -> List[str]:
        """Return list of candidate connectors worth actively probing."""
        pass


@dataclass
class BetaBernoulliRecord:
    """Beta-Bernoulli conjugate distribution state (alpha, beta)."""
    alpha: float = 8.0
    beta: float = 2.0
    last_update_ts: int = 0
    evidence_count: int = 0


class BetaBernoulliEstimator(BaseBeliefEstimator):
    """Step A: Beta-Bernoulli belief per connector with exponential forgetting."""
    def __init__(self, config: Config, alpha_prior: float = 8.0, beta_prior: float = 2.0):
        self.config = config
        self.alpha_prior = alpha_prior
        self.beta_prior = beta_prior
        self.connectors: Dict[str, BetaBernoulliRecord] = {}

    def _get_record(self, connector_id: str, now: int) -> BetaBernoulliRecord:
        if connector_id not in self.connectors:
            self.connectors[connector_id] = BetaBernoulliRecord(
                alpha=self.alpha_prior, beta=self.beta_prior, last_update_ts=now
            )
        rec = self.connectors[connector_id]
        if rec.last_update_ts > 0 and now > rec.last_update_ts:
            dt_sec = (now - rec.last_update_ts) / 1000.0
            decay = 0.5 ** (dt_sec / self.config.forgetting_half_life_sec)
            # Decay towards prior
            rec.alpha = self.alpha_prior + (rec.alpha - self.alpha_prior) * decay
            rec.beta = self.beta_prior + (rec.beta - self.beta_prior) * decay
            rec.last_update_ts = now
        return rec

    def update(self, event: Any) -> None:
        if isinstance(event, VehicleSessionEvent):
            rec = self._get_record(event.connector_id, event.event_ts)
            rec.evidence_count += 1
            if event.outcome == SessionOutcome.STARTED:
                rec.alpha += 1.0
            else:
                rec.beta += 1.0
            rec.last_update_ts = event.event_ts

    def p_start(self, connector_id: str, now: int) -> float:
        rec = self._get_record(connector_id, now)
        scaled_prior = self.config.get_scaled_p_start()["healthy"]
        base_p = rec.alpha / (rec.alpha + rec.beta)
        return float(min(1.0, max(0.0, base_p * (scaled_prior / 0.97))))

    def state_probs(self, connector_id: str, now: int) -> Dict[str, float]:
        p = self.p_start(connector_id, now)
        return {
            "healthy": float(p),
            "degraded": 0.0,
            "deadend": float(1.0 - p),
            "offline": 0.0,
        }

    def uncertainty(self, connector_id: str, now: int) -> float:
        p = self.p_start(connector_id, now)
        p = max(1e-6, min(1.0 - 1e-6, p))
        entropy = -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))
        return float(entropy)

    def probe_candidates(self, request: VehicleRequestEvent, now: int) -> List[str]:
        if (request.current_soc - request.reserve_soc) < 0.10:
            return []
        candidates = []
        for c_id in self.connectors:
            u = self.uncertainty(c_id, now)
            if u > 0.70:
                candidates.append((u, c_id))
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [c_id for _, c_id in candidates[:3]]


@dataclass
class HMMConnectorState:
    """Online state vector and metadata for a single connector."""
    # State probabilities: [Healthy, Degraded, Dead-end, Offline]
    probs: np.ndarray = field(default_factory=lambda: np.array([0.80, 0.10, 0.08, 0.02], dtype=float))
    last_update_ts: int = 0
    evidence_count: int = 0
    site_id: str = ""
    operator_id: str = ""
    firmware_version: str = ""


class HMMBeliefEstimator(BaseBeliefEstimator):
    """Step B: 4-State HMM Online Forward Filter with Group Pooling and Forgetting.
    
    States:
    0: Healthy
    1: Degraded
    2: Dead-end
    3: Offline
    """
    def __init__(
        self,
        config: Config,
        connectors_meta: Optional[Dict[str, Any]] = None,
        pooler: Optional[GroupPooler] = None,
    ):
        self.config = config
        self.pooler = pooler or GroupPooler(config)
        self.connectors: Dict[str, HMMConnectorState] = {}
        self.connectors_meta = connectors_meta or {}

        # Baseline stationary prior: [Healthy, Degraded, Dead-end, Offline]
        self.base_prior = np.array([0.80, 0.10, 0.08, 0.02], dtype=float)

        # Precompute scaled emission vectors
        scaled_p = config.get_scaled_p_start()
        self.p_start_vec = np.array(
            [
                scaled_p["healthy"],
                scaled_p["degraded"],
                scaled_p["deadend"],
                scaled_p["offline"],
            ],
            dtype=float,
        )

        self.p_avail_vec = np.array(
            [
                config.p_avail_healthy,
                config.p_avail_degraded,
                config.p_avail_deadend,
                config.p_avail_offline,
            ],
            dtype=float,
        )

    def _get_or_create(self, connector_id: str, event_ts: int) -> HMMConnectorState:
        if connector_id not in self.connectors:
            meta = self.connectors_meta.get(connector_id)
            site_id = getattr(meta, "site_id", "")
            operator_id = getattr(meta, "operator_id", "")
            fw_version = getattr(meta, "firmware_version", "")
            self.connectors[connector_id] = HMMConnectorState(
                probs=self.base_prior.copy(),
                last_update_ts=event_ts,
                evidence_count=0,
                site_id=site_id,
                operator_id=operator_id,
                firmware_version=fw_version,
            )
        return self.connectors[connector_id]

    def _apply_decay_and_pooling(self, state: HMMConnectorState, now_ts: int) -> None:
        """Apply continuous-time exponential forgetting toward pooled prior."""
        dt_sec = max(0.0, (now_ts - state.last_update_ts) / 1000.0)
        half_life = self.config.forgetting_half_life_sec
        decay = 0.5 ** (dt_sec / half_life)

        # Compute group hazard multiplier
        hazard_mult = self.pooler.get_combined_hazard_multiplier(
            state.site_id, state.operator_id, state.firmware_version, now_ts
        )

        # Prior distribution modified by group hazard multiplier
        target_prior = self.base_prior.copy()
        if hazard_mult != 1.0:
            # Sibling failures raise suspicion of fault states (Degraded, Dead-end)
            target_prior[0] /= hazard_mult
            target_prior[1] *= math.sqrt(hazard_mult)
            target_prior[2] *= hazard_mult
            target_prior[3] *= math.sqrt(hazard_mult)
            target_prior /= target_prior.sum()

        # Continuous exponential relaxation towards target prior
        state.probs = decay * state.probs + (1.0 - decay) * target_prior
        state.probs /= state.probs.sum()
        state.last_update_ts = now_ts

    def update(self, event: Any) -> None:
        """Online forward filter update: O(1) per event."""
        if isinstance(event, VehicleSessionEvent):
            self._update_session(event)
        elif isinstance(event, ChargerStatusEvent):
            self._update_status(event)

    def _update_session(self, event: VehicleSessionEvent) -> None:
        state = self._get_or_create(event.connector_id, event.event_ts)
        self._apply_decay_and_pooling(state, event.event_ts)
        state.evidence_count += 1

        p_veh_fail = self.config.vehicle_failure_rate
        likelihood = np.zeros(4, dtype=float)

        if event.outcome == SessionOutcome.STARTED:
            # P(STARTED | State_i) = (1 - p_veh_fail) * P(start | State_i)
            likelihood = (1.0 - p_veh_fail) * self.p_start_vec

            # Incorporate delivered vs rated power evidence if available
            if event.delivered_kw is not None and event.rated_kw and event.rated_kw > 0:
                power_ratio = event.delivered_kw / event.rated_kw
                # Healthy typically delivers 0.90 to 1.00
                if power_ratio >= self.config.power_ratio_healthy_min:
                    likelihood[0] *= 1.2
                    likelihood[1] *= 0.1
                # Degraded typically delivers 0.20 to 0.60
                elif power_ratio <= self.config.power_ratio_degraded_max:
                    likelihood[0] *= 0.05
                    likelihood[1] *= 1.5

            # Group pooling: successful attempt recorded
            self.pooler.record_attempt("site", state.site_id, False, event.event_ts)
            self.pooler.record_attempt("operator", state.operator_id, False, event.event_ts)
            self.pooler.record_attempt("firmware", state.firmware_version, False, event.event_ts)

        else:
            # Outcome is FAILED or TIMEOUT
            # Effective failure noise includes vehicle-side issues, user aborts, and transient glitches (~12-15%)
            # This ensures a single isolated failure does not prematurely condemn a healthy connector
            p_veh_noise = max(0.15, self.config.vehicle_failure_rate)
            fail_prob = 1.0 - self.p_start_vec
            likelihood = p_veh_noise + (1.0 - p_veh_noise) * fail_prob

            if event.outcome == SessionOutcome.TIMEOUT:
                # Dead-end chargers specifically manifest as handshake timeouts (~97%)
                likelihood[2] *= 1.3
            elif event.outcome == SessionOutcome.FAILED:
                # Hardware/offline faults manifest as immediate failure
                likelihood[3] *= 1.3

            # Group pooling: failed attempt recorded
            self.pooler.record_attempt("site", state.site_id, True, event.event_ts)
            self.pooler.record_attempt("operator", state.operator_id, True, event.event_ts)
            self.pooler.record_attempt("firmware", state.firmware_version, True, event.event_ts)

        # Bayes update: posterior proportional to prior * likelihood
        new_probs = state.probs * likelihood
        denom = new_probs.sum()
        if denom > 1e-12:
            state.probs = new_probs / denom
        else:
            state.probs = self.base_prior.copy()

    def _update_status(self, event: ChargerStatusEvent) -> None:
        state = self._get_or_create(event.connector_id, event.event_ts)
        self._apply_decay_and_pooling(state, event.event_ts)

        likelihood = np.zeros(4, dtype=float)
        if event.reported_status == ReportedStatus.AVAILABLE:
            likelihood = self.p_avail_vec
        elif event.reported_status in (ReportedStatus.FAULTED, ReportedStatus.OFFLINE):
            likelihood = 1.0 - self.p_avail_vec
            likelihood[3] *= 2.0  # Offline most likely to report faulted/offline
        else:
            # CHARGING / in-use carries weak signal
            likelihood = np.array([0.9, 0.9, 0.1, 0.05], dtype=float)

        new_probs = state.probs * likelihood
        denom = new_probs.sum()
        if denom > 1e-12:
            state.probs = new_probs / denom
        else:
            state.probs = self.base_prior.copy()

    def p_start(self, connector_id: str, now: int) -> float:
        """Compute expected probability of next session starting."""
        state = self._get_or_create(connector_id, now)
        self._apply_decay_and_pooling(state, now)
        p_veh_fail = self.config.vehicle_failure_rate
        # Marginal start probability
        prob = float(np.dot(state.probs, self.p_start_vec) * (1.0 - p_veh_fail))
        return max(0.0, min(1.0, prob))

    def state_probs(self, connector_id: str, now: int) -> Dict[str, float]:
        state = self._get_or_create(connector_id, now)
        self._apply_decay_and_pooling(state, now)
        return {
            "healthy": float(state.probs[0]),
            "degraded": float(state.probs[1]),
            "deadend": float(state.probs[2]),
            "offline": float(state.probs[3]),
        }

    def uncertainty(self, connector_id: str, now: int) -> float:
        """Shannon entropy normalized to [0.0, 1.0]."""
        state = self._get_or_create(connector_id, now)
        self._apply_decay_and_pooling(state, now)
        p = state.probs + 1e-12
        entropy = -np.sum(p * np.log2(p)) / np.log2(4.0)
        return float(max(0.0, min(1.0, entropy)))

    def to_belief_event(self, connector_id: str, now: int) -> ConnectorBeliefEvent:
        """Generate a connector.belief streaming event."""
        state = self._get_or_create(connector_id, now)
        probs = self.state_probs(connector_id, now)
        p_start_val = self.p_start(connector_id, now)
        u_val = self.uncertainty(connector_id, now)

        return ConnectorBeliefEvent(
            event_ts=now,
            connector_id=connector_id,
            p_healthy=probs["healthy"],
            p_degraded=probs["degraded"],
            p_deadend=probs["deadend"],
            p_offline=probs["offline"],
            p_start=p_start_val,
            uncertainty=u_val,
            evidence_count=state.evidence_count,
            last_evidence_ts=state.last_update_ts,
        )

    def probe_candidates(self, request: VehicleRequestEvent, now: int) -> List[str]:
        """Identify high-entropy connectors safe to probe for vehicles with slack."""
        # Only vehicles with slack range/time (SoC well above reserve)
        slack = request.current_soc - request.reserve_soc
        if slack < 0.12:
            return []

        candidates: List[Tuple[float, str]] = []
        for c_id in self.connectors:
            u = self.uncertainty(c_id, now)
            # High uncertainty (entropy > 0.45)
            if u > 0.45:
                candidates.append((u, c_id))

        # Sort descending by uncertainty
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [c_id for _, c_id in candidates[:3]]
