"""Tests for Configuration dataclass, YAML override, and prior_scale."""
import pytest
from ct.config import Config


def test_config_defaults():
    cfg = Config()
    assert cfg.p_start_healthy == 0.97
    assert cfg.p_start_degraded == 0.90
    assert cfg.p_start_deadend == 0.03
    assert cfg.p_start_offline == 0.00

    assert cfg.p_avail_healthy == 0.95
    assert cfg.p_avail_degraded == 0.95
    assert cfg.p_avail_deadend == 0.90
    assert cfg.p_avail_offline == 0.15

    assert cfg.power_ratio_healthy_min == 0.90
    assert cfg.power_ratio_healthy_max == 1.00
    assert cfg.power_ratio_degraded_min == 0.20
    assert cfg.power_ratio_degraded_max == 0.60

    assert cfg.prior_scale == 1.0
    assert cfg.vehicle_failure_rate == 0.03
    assert cfg.timeout_cost_sec == 120.0
    assert cfg.forgetting_half_life_sec == 3600.0
    assert cfg.pooling_clip_min == 0.20
    assert cfg.pooling_clip_max == 5.00
    assert cfg.probe_rate == 0.05

    assert cfg.scan_windows_min == (15, 30, 60, 120)
    assert cfg.scan_persistence == 2
    assert cfg.false_alarm_budget_per_week == 1.0

    assert cfg.num_connectors == 200
    assert cfg.num_sites == 60
    assert cfg.num_operators == 4
    assert cfg.num_models == 5
    assert cfg.num_firmwares == 3
    assert cfg.target_first_attempt_success == 0.71

    assert cfg.lat_min == 12.85
    assert cfg.lat_max == 13.20
    assert cfg.lon_min == 80.10
    assert cfg.lon_max == 80.35

    assert len(cfg.dev_seeds) == 10
    assert cfg.dev_seeds[0] == 0
    assert cfg.dev_seeds[-1] == 9
    assert len(cfg.eval_seeds) == 20
    assert cfg.eval_seeds[0] == 100
    assert cfg.eval_seeds[-1] == 119


def test_config_frozen():
    cfg = Config()
    with pytest.raises(Exception):
        cfg.probe_rate = 0.10  # Frozen dataclass should reject mutations


def test_config_with_overrides():
    cfg = Config()
    modified = cfg.with_overrides(probe_rate=0.10, prior_scale=0.7)
    assert modified.probe_rate == 0.10
    assert modified.prior_scale == 0.7
    assert cfg.probe_rate == 0.05  # Original unaffected


def test_config_yaml_override(tmp_path):
    yaml_content = """
probe_rate: 0.12
prior_scale: 1.3
target_first_attempt_success: 0.75
scan_windows_min: [10, 20, 40]
"""
    yaml_file = tmp_path / "test_config.yaml"
    yaml_file.write_text(yaml_content, encoding="utf-8")

    cfg = Config.from_yaml(yaml_file)
    assert cfg.probe_rate == 0.12
    assert cfg.prior_scale == 1.3
    assert cfg.target_first_attempt_success == 0.75
    assert cfg.scan_windows_min == (10, 20, 40)
    # Check that untouched parameters retain default values
    assert cfg.num_connectors == 200
    assert cfg.vehicle_failure_rate == 0.03


def test_prior_scale_applies():
    cfg_nominal = Config(prior_scale=1.0)
    nominal_p = cfg_nominal.get_scaled_p_start()
    assert nominal_p["healthy"] == 0.97
    assert nominal_p["degraded"] == 0.90
    assert nominal_p["deadend"] == 0.03
    assert nominal_p["offline"] == 0.00

    cfg_low = Config(prior_scale=0.7)
    low_p = cfg_low.get_scaled_p_start()
    assert pytest.approx(low_p["healthy"]) == 0.97 * 0.7
    assert pytest.approx(low_p["degraded"]) == 0.90 * 0.7
    assert pytest.approx(low_p["deadend"]) == 0.03 * 0.7
    assert low_p["offline"] == 0.00

    cfg_high = Config(prior_scale=1.3)
    high_p = cfg_high.get_scaled_p_start()
    # 0.97 * 1.3 = 1.261 -> clipped to 1.0
    assert high_p["healthy"] == 1.0
    assert high_p["degraded"] == 1.0
    assert pytest.approx(high_p["deadend"]) == 0.03 * 1.3
    assert high_p["offline"] == 0.00
