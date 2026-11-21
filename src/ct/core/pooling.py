"""Gamma-Poisson group hazard rate pooling for Charger Truth.

Pure Python and numpy, no Kafka or Condense dependencies.

A connector with sparse local observations borrows statistical strength
from siblings in its site, operator, and firmware groups.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np

from ct.config import Config
from ct.schemas import VehicleSessionEvent, SessionOutcome


@dataclass
class GroupRecord:
    """Running attempt and failure statistics for a group."""
    attempts: float = 0.0
    failures: float = 0.0
    last_update_ts: int = 0


class GroupPooler:
    """Computes empirical Bayes shrinkage hazard multipliers across groups."""
    def __init__(
        self,
        config: Config,
        alpha_prior: float = 2.0,
        beta_prior: float = 2.0,
        baseline_failure_rate: float = 0.28,
    ):
        self.config = config
        self.alpha_prior = alpha_prior
        self.beta_prior = beta_prior
        self.baseline_failure_rate = baseline_failure_rate
        self.groups: Dict[str, GroupRecord] = {}

    def _decay_record(self, record: GroupRecord, now_ts: int) -> None:
        """Apply exponential forgetting to group statistics."""
        if record.last_update_ts > 0 and now_ts > record.last_update_ts:
            dt_sec = (now_ts - record.last_update_ts) / 1000.0
            half_life = self.config.forgetting_half_life_sec
            decay = 0.5 ** (dt_sec / half_life)
            record.attempts *= decay
            record.failures *= decay
        record.last_update_ts = now_ts

    def record_attempt(
        self,
        group_type: str,
        group_key: str,
        is_failure: bool,
        event_ts: int,
    ) -> None:
        """Record an attempt outcome for a given group (site, operator, firmware)."""
        full_key = f"{group_type}:{group_key}"
        if full_key not in self.groups:
            self.groups[full_key] = GroupRecord(last_update_ts=event_ts)

        rec = self.groups[full_key]
        self._decay_record(rec, event_ts)
        rec.attempts += 1.0
        if is_failure:
            rec.failures += 1.0

    def get_hazard_multiplier(
        self,
        group_type: str,
        group_key: str,
        now_ts: int,
    ) -> float:
        """Calculate Gamma-Poisson posterior hazard rate multiplier for a single group."""
        full_key = f"{group_type}:{group_key}"
        if full_key not in self.groups:
            return 1.0

        rec = self.groups[full_key]
        self._decay_record(rec, now_ts)

        # Expected failures under baseline failure rate
        expected_failures = rec.attempts * self.baseline_failure_rate
        # Gamma posterior mean = (alpha + c) / (beta + e)
        # Normalized so that when c == e, multiplier is 1.0
        alpha = self.alpha_prior + rec.failures
        beta = self.beta_prior + expected_failures
        raw_mult = alpha / beta

        # Clip to Config bounds
        clipped = max(
            self.config.pooling_clip_min,
            min(self.config.pooling_clip_max, raw_mult),
        )
        return float(clipped)

    def get_combined_hazard_multiplier(
        self,
        site_id: str,
        operator_id: str,
        firmware_version: str,
        now_ts: int,
    ) -> float:
        """Calculate joint hazard multiplier across site, operator, and firmware."""
        m_site = self.get_hazard_multiplier("site", site_id, now_ts)
        m_op = self.get_hazard_multiplier("operator", operator_id, now_ts)
        m_fw = self.get_hazard_multiplier("firmware", firmware_version, now_ts)

        # Geometric or damped product to avoid extreme double-counting
        combined = (m_site * m_op * m_fw) ** (1.0 / 2.0)
        clipped = max(
            self.config.pooling_clip_min,
            min(self.config.pooling_clip_max, combined),
        )
        return float(clipped)
