#!/usr/bin/env python3
"""Generate a netix-simulator ``config.yaml`` for the NETIX demo tenant (org 9999).

The demo tenant's cross-service id contract lives in ``demo_spec.json`` (vendored
byte-identical from the backend). Every demo equipment asset carries a stable
``tag_identifier`` and belongs to a *family*; each family exposes a fixed set of
Haystack point *roles* (``haystack_point_roles``). The platform historises each
point under the tag name ``<tag_identifier>/<role>``.

This generator emits one simulator *template* per family (its points are the
family's roles) and one *instance* per equipment (``name_prefix`` = the
equipment's ``tag_identifier``, ``count`` = 1). The companion republisher config
(produced by ``simulator --emit-republisher-config``) then maps every polled
BACnet point to envelope ``id = <tag_identifier>`` / ``pointName = <role>``, so
the stormbreaker demo worker writes exactly ``<tag_identifier>/<role>`` — the tag
the viz dashboards read. See demo/README.md for the full pipeline.

Usage:
    python3 gen_demo.py [--spec demo_spec.json] [--out config.yaml]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# --- role -> simulator behaviour -------------------------------------------
# (object_type, bacnet_units | None, profile-dict). Units use the ASHRAE 135
# names the simulator understands; roles whose quantity has no ASHRAE unit
# (pH, dB, floor index, boolean status) omit units. Booleans use binary_input
# and are served as BACnet Enumerated 0/1 (numeric on the wire).
ROLE_SIM: dict[str, tuple[str, str | None, dict]] = {
    # --- AHU ---------------------------------------------------------------
    "discharge-air-temp": ("analog_input", "degrees_celsius",
        {"kind": "temp_control", "setpoint": 14.0, "gain": 0.08, "outside_influence": 0.1, "noise": 0.3, "initial": 14.0}),
    "return-air-temp": ("analog_input", "degrees_celsius",
        {"kind": "temp_control", "setpoint": 23.0, "gain": 0.06, "noise": 0.2, "initial": 23.0}),
    "mixed-air-temp": ("analog_input", "degrees_celsius",
        {"kind": "temp_control", "setpoint": 20.0, "gain": 0.06, "outside_influence": 0.2, "noise": 0.3, "initial": 20.0}),
    "cooling-valve-cmd": ("analog_output", "percent",
        {"kind": "occupancy_linked", "base": 10.0, "peak_delta": 70.0, "noise": 5.0}),
    "outside-air-damper-cmd": ("analog_output", "percent",
        {"kind": "occupancy_linked", "base": 15.0, "peak_delta": 25.0, "noise": 3.0}),
    "supply-fan-run-status": ("binary_input", None,
        {"kind": "binary_schedule", "on_when_occupancy_gt": 0.05}),
    "supply-fan-vfd-speed": ("analog_input", "percent",
        {"kind": "occupancy_linked", "base": 30.0, "peak_delta": 55.0, "noise": 4.0}),
    "zone-co2": ("analog_input", "parts_per_million",
        {"kind": "occupancy_linked", "base": 450.0, "peak_delta": 500.0, "noise": 25.0}),
    # --- Meter (active-power first: energy-accumulator integrates it) -------
    "active-power": ("analog_input", "kilowatts",
        {"kind": "occupancy_linked", "base": 40.0, "peak_delta": 260.0, "noise": 15.0}),
    "energy-accumulator": ("analog_input", "kilowatt_hours",
        {"kind": "integrator", "rate_source": "active-power", "scale": 0.000277778}),
    # --- Zone --------------------------------------------------------------
    "zone-air-temp": ("analog_input", "degrees_celsius",
        {"kind": "temp_control", "setpoint": 22.5, "gain": 0.08, "noise": 0.2, "initial": 22.5}),
    "zone-air-rh": ("analog_input", "percent_relative_humidity",
        {"kind": "random_walk", "base": 50.0, "step": 0.5, "min": 35.0, "max": 65.0}),
    "zone-air-co2": ("analog_input", "parts_per_million",
        {"kind": "occupancy_linked", "base": 420.0, "peak_delta": 480.0, "noise": 20.0}),
    # --- Waste bin ---------------------------------------------------------
    "fill-level": ("analog_input", "percent",
        {"kind": "ramp", "start": 0.0, "end": 100.0, "period_secs": 86400.0}),
    "battery-level": ("analog_input", "percent",
        {"kind": "random_walk", "base": 85.0, "step": 0.1, "min": 60.0, "max": 100.0}),
    "tilt-alarm": ("binary_input", None,
        {"kind": "binary_schedule", "on_when_occupancy_gt": 2.0}),
    # --- Weather station ---------------------------------------------------
    "outside-air-temp": ("analog_input", "degrees_celsius",
        {"kind": "sine", "base": 30.0, "amplitude": 6.0, "period_secs": 86400.0}),
    "outside-air-rh": ("analog_input", "percent_relative_humidity",
        {"kind": "sine", "base": 55.0, "amplitude": 15.0, "period_secs": 86400.0, "phase_secs": 43200.0}),
    "wind-speed": ("analog_input", "meters_per_second",
        {"kind": "random_walk", "base": 4.0, "step": 0.3, "min": 0.0, "max": 15.0}),
    "solar-irradiance": ("analog_input", "watts",
        {"kind": "sine", "base": 450.0, "amplitude": 350.0, "period_secs": 86400.0}),
    # --- Lift --------------------------------------------------------------
    "lift-run-status": ("binary_input", None,
        {"kind": "binary_schedule", "on_when_occupancy_gt": 0.05}),
    "lift-car-position": ("analog_input", None,
        {"kind": "random_walk", "base": 5.0, "step": 1.0, "min": 1.0, "max": 20.0}),
    # --- Water tank --------------------------------------------------------
    "tank-level": ("analog_input", "percent",
        {"kind": "random_walk", "base": 70.0, "step": 0.5, "min": 20.0, "max": 100.0}),
    "tank-water-temp": ("analog_input", "degrees_celsius",
        {"kind": "temp_control", "setpoint": 28.0, "gain": 0.02, "outside_influence": 0.1, "noise": 0.1, "initial": 28.0}),
    # --- Odour -------------------------------------------------------------
    "h2s-concentration": ("analog_input", "parts_per_billion",
        {"kind": "random_walk", "base": 5.0, "step": 0.5, "min": 0.0, "max": 50.0}),
    "odour-alarm": ("binary_input", None,
        {"kind": "binary_schedule", "on_when_occupancy_gt": 2.0}),
    # --- Noise -------------------------------------------------------------
    "noise-level": ("analog_input", None,
        {"kind": "occupancy_linked", "base": 45.0, "peak_delta": 30.0, "noise": 3.0}),
    # --- Water quality -----------------------------------------------------
    "water-ph": ("analog_input", None,
        {"kind": "random_walk", "base": 7.2, "step": 0.02, "min": 6.5, "max": 8.5}),
    "water-temp": ("analog_input", "degrees_celsius",
        {"kind": "temp_control", "setpoint": 26.0, "gain": 0.02, "noise": 0.1, "initial": 26.0}),
    "water-chlorine": ("analog_input", "parts_per_million",
        {"kind": "random_walk", "base": 1.5, "step": 0.05, "min": 0.5, "max": 3.0}),
    # --- IAQ ---------------------------------------------------------------
    "iaq-co2": ("analog_input", "parts_per_million",
        {"kind": "occupancy_linked", "base": 450.0, "peak_delta": 500.0, "noise": 25.0}),
    "iaq-temp": ("analog_input", "degrees_celsius",
        {"kind": "temp_control", "setpoint": 23.0, "gain": 0.05, "noise": 0.2, "initial": 23.0}),
    "iaq-rh": ("analog_input", "percent_relative_humidity",
        {"kind": "random_walk", "base": 48.0, "step": 0.4, "min": 35.0, "max": 60.0}),
    # --- CBS ---------------------------------------------------------------
    "cbs-battery-level": ("analog_input", "percent",
        {"kind": "random_walk", "base": 95.0, "step": 0.05, "min": 80.0, "max": 100.0}),
    "cbs-status": ("binary_input", None,
        {"kind": "constant_bool", "value": True}),
    # --- LPG ---------------------------------------------------------------
    "lpg-concentration": ("analog_input", "parts_per_million",
        {"kind": "random_walk", "base": 20.0, "step": 1.0, "min": 0.0, "max": 100.0}),
    "lpg-alarm": ("binary_input", None,
        {"kind": "binary_schedule", "on_when_occupancy_gt": 2.0}),
    # --- Fans (shared roles) ----------------------------------------------
    "fan-run-status": ("binary_input", None,
        {"kind": "binary_schedule", "on_when_occupancy_gt": 0.05}),
    "fan-speed": ("analog_input", "percent",
        {"kind": "occupancy_linked", "base": 20.0, "peak_delta": 60.0, "noise": 4.0}),
    # --- Pumps (shared roles) ---------------------------------------------
    "pump-run-status": ("binary_input", None,
        {"kind": "binary_schedule", "on_when_occupancy_gt": 0.05}),
    "pump-speed": ("analog_input", "percent",
        {"kind": "random_walk", "base": 60.0, "step": 3.0, "min": 0.0, "max": 100.0}),
    # --- Heat exchanger ----------------------------------------------------
    "hex-supply-temp": ("analog_input", "degrees_celsius",
        {"kind": "temp_control", "setpoint": 45.0, "gain": 0.03, "noise": 0.2, "initial": 45.0}),
    "hex-return-temp": ("analog_input", "degrees_celsius",
        {"kind": "temp_control", "setpoint": 38.0, "gain": 0.03, "noise": 0.2, "initial": 38.0}),
    # --- Swimming pool -----------------------------------------------------
    "pool-temp": ("analog_input", "degrees_celsius",
        {"kind": "temp_control", "setpoint": 28.0, "gain": 0.02, "noise": 0.1, "initial": 28.0}),
    "pool-chlorine": ("analog_input", "parts_per_million",
        {"kind": "random_walk", "base": 1.8, "step": 0.03, "min": 1.0, "max": 3.0}),
    "pool-ph": ("analog_input", None,
        {"kind": "random_walk", "base": 7.4, "step": 0.01, "min": 7.0, "max": 7.8}),
    # --- Water consumption -------------------------------------------------
    "consumption-volume": ("analog_input", "cubic_meters",
        {"kind": "ramp", "start": 0.0, "end": 500.0, "period_secs": 86400.0}),

    # --- Systems-sections coverage (spec v3) --------------------------------
    # AHU detailed-widget points (FAHU page matches these display names).
    "outside-air-temperature": ("analog_input", "degrees_celsius",
        {"kind": "sine", "base": 30.0, "amplitude": 6.0, "period_secs": 86400.0}),
    "supply-air-temperature": ("analog_input", "degrees_celsius",
        {"kind": "temp_control", "setpoint": 14.0, "gain": 0.08, "outside_influence": 0.1, "noise": 0.3, "initial": 14.0}),
    "return-air-temperature": ("analog_input", "degrees_celsius",
        {"kind": "temp_control", "setpoint": 23.0, "gain": 0.06, "noise": 0.2, "initial": 23.0}),
    "pre-filter-status": ("binary_input", None,
        {"kind": "constant_bool", "value": False}),
    "bag-filter-status": ("binary_input", None,
        {"kind": "constant_bool", "value": False}),
    "supply-fan-trip-status": ("binary_input", None,
        {"kind": "constant_bool", "value": False}),
    "supply-fan-hoa-status": ("binary_input", None,
        {"kind": "constant_bool", "value": True}),
    "supply-air-damper-command": ("analog_output", "percent",
        {"kind": "occupancy_linked", "base": 20.0, "peak_delta": 60.0, "noise": 4.0}),
    "supply-air-damper-status": ("analog_input", "percent",
        {"kind": "occupancy_linked", "base": 20.0, "peak_delta": 60.0, "noise": 4.0}),
    "valve-command": ("analog_output", "percent",
        {"kind": "occupancy_linked", "base": 15.0, "peak_delta": 65.0, "noise": 5.0}),
    "supply-air-flow-status": ("binary_input", None,
        {"kind": "binary_schedule", "on_when_occupancy_gt": 0.05}),
    # PMU electrical points (Energy page charts/cards).
    "energy": ("analog_input", "kilowatt_hours",
        {"kind": "integrator", "rate_source": "active-power", "scale": 0.000277778}),
    "frequency": ("analog_input", "hertz",
        {"kind": "random_walk", "base": 50.0, "step": 0.02, "min": 49.7, "max": 50.3}),
    "power-factor": ("analog_input", None,
        {"kind": "random_walk", "base": 0.92, "step": 0.005, "min": 0.85, "max": 0.99}),
    "phase-power": ("analog_input", "kilowatts",
        {"kind": "occupancy_linked", "base": 13.0, "peak_delta": 85.0, "noise": 5.0}),
    "voltage": ("analog_input", "volts",
        {"kind": "random_walk", "base": 415.0, "step": 1.0, "min": 400.0, "max": 430.0}),
    "current": ("analog_input", "amperes",
        {"kind": "occupancy_linked", "base": 60.0, "peak_delta": 340.0, "noise": 20.0}),
    # IAQ bare roles (IAQ page matches exact segment names).
    "co2": ("analog_input", "parts_per_million",
        {"kind": "occupancy_linked", "base": 450.0, "peak_delta": 480.0, "noise": 25.0}),
    "temp": ("analog_input", "degrees_celsius",
        {"kind": "temp_control", "setpoint": 23.5, "gain": 0.05, "outside_influence": 0.1, "noise": 0.2, "initial": 23.5}),
    "rh": ("analog_input", "percent_relative_humidity",
        {"kind": "random_walk", "base": 50.0, "step": 0.5, "min": 35.0, "max": 65.0}),
    "pm25": ("analog_input", "micrograms_per_cubic_meter",
        {"kind": "occupancy_linked", "base": 8.0, "peak_delta": 22.0, "noise": 3.0}),
    "pm10": ("analog_input", "micrograms_per_cubic_meter",
        {"kind": "occupancy_linked", "base": 15.0, "peak_delta": 35.0, "noise": 5.0}),
    "tvoc": ("analog_input", "parts_per_billion",
        {"kind": "occupancy_linked", "base": 120.0, "peak_delta": 280.0, "noise": 20.0}),
    # Odour (H2S page matches exact 'h2s').
    "h2s": ("analog_input", "parts_per_million",
        {"kind": "random_walk", "base": 0.05, "step": 0.01, "min": 0.0, "max": 0.4}),
    # Lake / water-quality signals (exact segment names on the lake page).
    "ph": ("analog_input", None,
        {"kind": "random_walk", "base": 7.6, "step": 0.02, "min": 6.8, "max": 8.4}),
    "ph-temperature": ("analog_input", "degrees_celsius",
        {"kind": "sine", "base": 26.0, "amplitude": 3.0, "period_secs": 86400.0}),
    "distance": ("analog_input", "millimeters",
        {"kind": "random_walk", "base": 600.0, "step": 5.0, "min": 300.0, "max": 900.0}),
    "flood": ("binary_input", None,
        {"kind": "constant_bool", "value": False}),
    "battery": ("analog_input", "percent",
        {"kind": "random_walk", "base": 88.0, "step": 0.05, "min": 60.0, "max": 100.0}),
    # Lift detail charts (Power / Fault / Call substring matches).
    "lift-power": ("binary_input", None,
        {"kind": "constant_bool", "value": True}),
    "lift-fault": ("binary_input", None,
        {"kind": "constant_bool", "value": False}),
    "lift-call": ("analog_input", None,
        {"kind": "random_walk", "base": 5.0, "step": 2.0, "min": 0.0, "max": 20.0}),
    # LPG leak-detection chart.
    "lpg-leak-detection": ("binary_input", None,
        {"kind": "constant_bool", "value": False}),
    # Fan-family status points (HVAC subsections).
    "fan-trip-status": ("binary_input", None,
        {"kind": "constant_bool", "value": False}),
    "fan-hoa-status": ("binary_input", None,
        {"kind": "constant_bool", "value": True}),
    # Pump-family cards (Sump / Fire / Booster pumps pages).
    "pump-trip-status": ("binary_input", None,
        {"kind": "constant_bool", "value": False}),
    "pump-system-enable": ("binary_input", None,
        {"kind": "constant_bool", "value": True}),
    "pump-system-reset": ("binary_input", None,
        {"kind": "constant_bool", "value": False}),
    "pump-index": ("analog_input", None,
        {"kind": "random_walk", "base": 1.0, "step": 0.2, "min": 0.0, "max": 3.0}),
    "vfd-speed-feedback": ("analog_input", "percent",
        {"kind": "occupancy_linked", "base": 35.0, "peak_delta": 45.0, "noise": 4.0}),
    # Heat-exchanger detailed widgets (exact display-name matches).
    "hex-system-enable": ("binary_input", None,
        {"kind": "constant_bool", "value": True}),
    "hex-system-reset": ("binary_input", None,
        {"kind": "constant_bool", "value": False}),
    "index-differential-pressure": ("analog_input", "kilopascals",
        {"kind": "random_walk", "base": 45.0, "step": 1.0, "min": 30.0, "max": 60.0}),
    "index-differential-pressure-setpoint": ("analog_input", "kilopascals",
        {"kind": "constant", "value": 45.0}),
    "secondary-side-header-inlet-temperature": ("analog_input", "degrees_celsius",
        {"kind": "temp_control", "setpoint": 12.0, "gain": 0.05, "noise": 0.2, "initial": 12.0}),
    "secondary-side-header-outlet-temperature": ("analog_input", "degrees_celsius",
        {"kind": "temp_control", "setpoint": 17.0, "gain": 0.05, "noise": 0.2, "initial": 17.0}),
    "secondary-side-outlet-temperature": ("analog_input", "degrees_celsius",
        {"kind": "temp_control", "setpoint": 16.5, "gain": 0.05, "noise": 0.2, "initial": 16.5}),
}

# Life-safety / standby equipment sits idle unless called. Override the shared
# run/speed roles for those families so they read OFF at 0%.
STANDBY_FAMILIES = {"staircase_fan", "sef", "lift_fan", "fire_pump"}
STANDBY_OVERRIDES = {
    "fan-run-status": ("binary_input", None, {"kind": "binary_schedule", "on_when_occupancy_gt": 2.0}),
    "fan-speed": ("analog_input", "percent", {"kind": "constant", "value": 0.0}),
    "pump-run-status": ("binary_input", None, {"kind": "binary_schedule", "on_when_occupancy_gt": 2.0}),
    "pump-speed": ("analog_input", "percent", {"kind": "constant", "value": 0.0}),
}

# Templates whose point order must differ from haystack_point_roles order (an
# integrator's rate_source point must be declared first).
POINT_ORDER = {
    "meter": [
        # active-power first: both accumulators integrate it.
        "active-power", "energy-accumulator", "energy",
        "frequency", "power-factor", "phase-power", "voltage", "current",
    ]
}

# The weather station is not in a demo_spec list (it is a single fixed asset in
# the tag-service seed). Its tag_identifier is defined there.
WEATHER_STATION = {"tag_identifier": "demo-weather-station-01", "building": "demo-bldg-tower-a"}


def _fmt_profile(profile: dict) -> str:
    parts = []
    for key, value in profile.items():
        if isinstance(value, bool):
            parts.append(f"{key}: {'true' if value else 'false'}")
        elif isinstance(value, float):
            parts.append(f"{key}: {value!r}")
        else:
            parts.append(f"{key}: {value}")
    return "{ " + ", ".join(parts) + " }"


def _fmt_point(role: str, family: str) -> str:
    obj_type, units, profile = ROLE_SIM[role]
    if family in STANDBY_FAMILIES and role in STANDBY_OVERRIDES:
        obj_type, units, profile = STANDBY_OVERRIDES[role]
    units_frag = f"units: {units}, " if units else ""
    return (
        f'      - {{ label: "{role}", object_type: {obj_type}, {units_frag}'
        f"profile: {_fmt_profile(profile)} }}"
    )


def _equipment_by_family(spec: dict) -> dict[str, list[dict]]:
    """{family -> [equipment...]} in stable spec order. Equipment dicts expose
    at least ``tag_identifier`` and ``building``."""
    fam: dict[str, list[dict]] = {}
    for ahu in spec["ahus"]:
        fam.setdefault("ahu", []).append(ahu)
    for meter in spec["meters"]:
        fam.setdefault("meter", []).append(meter)
    for zone in spec["zones"]:
        fam.setdefault("zone", []).append(zone)
    for wb in spec["waste_bins"]:
        fam.setdefault("waste_bin", []).append(wb)
    fam.setdefault("weather_station", []).append(WEATHER_STATION)
    for sensor in spec["sensors"]:
        fam.setdefault(sensor["family"], []).append(sensor)
    return fam


def build_yaml(spec: dict) -> tuple[str, dict]:
    roles_by_family = spec["haystack_point_roles"]
    classes = spec["asset_classes"]
    equipment = _equipment_by_family(spec)

    # Validate: every family with equipment has roles + every role has a sim.
    for family in equipment:
        if family not in roles_by_family:
            raise SystemExit(f"family {family!r} has equipment but no haystack_point_roles")
        for role in roles_by_family[family]:
            if role not in ROLE_SIM:
                raise SystemExit(f"role {role!r} (family {family}) missing from ROLE_SIM")

    lines: list[str] = []
    lines.append("# GENERATED by demo/gen_demo.py from demo_spec.json — do not edit by hand.")
    lines.append("# NETIX demo tenant (org 9999) simulator model: one template per asset-class")
    lines.append("# family, one instance per equipment (name_prefix = tag_identifier).")
    lines.append("")
    lines.append("building:")
    lines.append('  name: "NETIX Demo - Tower Campus"')
    lines.append('  location: "Bengaluru"')
    lines.append('  timezone: "Asia/Kolkata"')
    lines.append("")
    lines.append("seasonality:")
    lines.append("  weekly_schedule:")
    lines.append("    weekday_occupancy:")
    for time, val in [("00:00", 0.0), ("07:00", 0.2), ("09:00", 1.0), ("18:00", 1.0), ("20:00", 0.2), ("23:59", 0.05)]:
        lines.append(f'      - {{ time: "{time}", value: {val} }}')
    lines.append("    weekend_occupancy:")
    for time, val in [("00:00", 0.0), ("10:00", 0.3), ("20:00", 0.4), ("23:59", 0.05)]:
        lines.append(f'      - {{ time: "{time}", value: {val} }}')
    lines.append("")
    lines.append("id_policy:")
    lines.append("  device_id_base: 10000")
    lines.append("  per_template_block: 100")
    lines.append("")

    # Templates: one per family, in asset_classes order (stable, mirrors spec).
    lines.append("templates:")
    n_points = 0
    for family in classes:
        if family not in equipment:
            continue  # class defined but no equipment seeded
        roles = POINT_ORDER.get(family, roles_by_family[family])
        display = classes[family]["display_name"]
        lines.append(f"  {family}:")
        lines.append(f'    description: "{display}"')
        lines.append("    points:")
        for role in roles:
            lines.append(_fmt_point(role, family))
            n_points += 1
        lines.append("")

    # Instances: one per equipment, name_prefix = tag_identifier, count = 1.
    lines.append("instances:")
    n_instances = 0
    for family in classes:
        for equip in equipment.get(family, []):
            tag_id = equip["tag_identifier"]
            building = equip.get("building", "")
            zone_frag = f', zone: "{building}"' if building else ""
            lines.append(f'  - {{ template: {family}, name_prefix: "{tag_id}", count: 1{zone_frag} }}')
            n_instances += 1
    lines.append("")

    lines.append("protocols:")
    lines.append("  - { id: bacnet, port: 47808 }")
    lines.append("")

    stats = {
        "templates": sum(1 for f in classes if f in equipment),
        "template_points": n_points,
        "instances": n_instances,
        # total served points = sum over instances of its template's point count
        "served_points": sum(
            len(POINT_ORDER.get(f, roles_by_family[f])) * len(equipment.get(f, []))
            for f in classes if f in equipment
        ),
    }
    return "\n".join(lines) + "\n", stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", default=str(HERE / "demo_spec.json"), type=Path)
    ap.add_argument("--out", default=str(HERE / "config.yaml"), type=Path)
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text())
    yaml_text, stats = build_yaml(spec)
    Path(args.out).write_text(yaml_text)
    print(f"wrote {args.out}")
    print(
        f"  templates={stats['templates']}  distinct template points={stats['template_points']}  "
        f"instances={stats['instances']}  served BACnet points={stats['served_points']}"
    )


if __name__ == "__main__":
    main()
