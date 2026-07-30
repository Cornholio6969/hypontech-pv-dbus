#!/usr/bin/env python3
"""
dbus-hypon-pv
Poll Hypon Cloud and expose the inverter as a Victron Venus OS PV inverter.
No third-party HTTP package is required.
"""

import configparser
import json
import logging
import os
import platform
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, Optional, Tuple

from gi.repository import GLib
from dbus.mainloop.glib import DBusGMainLoop

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.ini")

# Locate Victron's velib_python.
for candidate in (
    os.path.join(SCRIPT_DIR, "ext", "velib_python"),
    "/opt/victronenergy/dbus-systemcalc-py/ext/velib_python",
    "/opt/victronenergy/dbus-mqtt/ext/velib_python",
    "/opt/victronenergy/velib_python",
):
    if os.path.isdir(candidate):
        sys.path.insert(0, candidate)
        break

try:
    from vedbus import VeDbusService
except ImportError as exc:
    raise SystemExit(
        "Could not import vedbus. This module must run on Venus OS, or "
        "velib_python must be placed in ext/velib_python."
    ) from exc


VERSION = "1.0.0"


def load_config() -> configparser.ConfigParser:
    if not os.path.exists(CONFIG_FILE):
        raise SystemExit(f"Missing config file: {CONFIG_FILE}")

    config = configparser.ConfigParser(interpolation=None)
    config.read(CONFIG_FILE)

    required = {
        "DEFAULT": ("device_name", "device_instance"),
        "PV": ("max_power", "position"),
        "HYPON": ("username", "password", "system_id"),
    }
    for section, keys in required.items():
        values = config[section]
        for key in keys:
            if not values.get(key, "").strip():
                raise SystemExit(f"Missing [{section}] {key} in config.ini")
    return config


CONFIG = load_config()

level_name = CONFIG["DEFAULT"].get("logging", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, level_name, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
)
LOG = logging.getLogger("dbus-hypon-pv")


def as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def find_value(data: Any, paths: Iterable[str]) -> Any:
    """Return the first value found using dot-separated paths, recursively."""
    for path in paths:
        current = data
        valid = True
        for key in path.split("."):
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                valid = False
                break
        if valid and current is not None:
            return current

    # Private APIs often add/remove wrapper objects. Search recursively by leaf key.
    leafs = {path.split(".")[-1] for path in paths}
    stack = [data]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, value in item.items():
                if key in leafs and value is not None:
                    return value
                stack.append(value)
        elif isinstance(item, list):
            stack.extend(item)
    return None


class HyponApi:
    def __init__(self, config: configparser.SectionProxy):
        self.base_url = config.get("base_url", "https://api.hypon.cloud/v2").rstrip("/")
        self.username = config["username"]
        self.password = config["password"]
        self.system_id = config["system_id"]
        self.login_endpoint = config.get("login_endpoint", "/login")
        self.monitor_endpoint = config.get(
            "monitor_endpoint", "/plant/{system_id}/monitor?refresh=true"
        )
        self.login_method = config.get("login_method", "POST").upper()
        self.monitor_method = config.get("monitor_method", "GET").upper()
        self.username_field = config.get("username_field", "username")
        self.password_field = config.get("password_field", "password")
        self.auth_header = config.get("auth_header", "Authorization")
        self.auth_scheme = config.get("auth_scheme", "Bearer").strip()
        self.static_token = config.get("token", "").strip()
        self.timeout = config.getint("http_timeout", 20)
        self.verify_ssl = config.getboolean("verify_ssl", True)
        self.extra_headers = self._parse_json(config.get("extra_headers_json", "{}"))
        self.login_extra = self._parse_json(config.get("login_extra_json", "{}"))
        self.monitor_body = self._parse_json(config.get("monitor_body_json", "{}"))
        self.token: Optional[str] = self.static_token or None
        self.last_raw: Dict[str, Any] = {}

        self.ssl_context = ssl.create_default_context()
        if not self.verify_ssl:
            self.ssl_context.check_hostname = False
            self.ssl_context.verify_mode = ssl.CERT_NONE

    @staticmethod
    def _parse_json(value: str) -> Dict[str, Any]:
        try:
            parsed = json.loads(value or "{}")
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSON in config.ini: {exc}") from exc

    def _url(self, endpoint: str) -> str:
        endpoint = endpoint.format(system_id=urllib.parse.quote(self.system_id))
        return endpoint if endpoint.startswith("http") else self.base_url + "/" + endpoint.lstrip("/")

    def _request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Dict[str, Any]] = None,
        authenticated: bool = True,
    ) -> Dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": f"dbus-hypon-pv/{VERSION}",
            **self.extra_headers,
        }
        if authenticated and self.token:
            token_value = f"{self.auth_scheme} {self.token}".strip()
            headers[self.auth_header] = token_value

        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self._url(endpoint), data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout, context=self.ssl_context
            ) as response:
                raw = response.read().decode("utf-8", errors="replace")
                if not raw:
                    return {}
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    return {"data": parsed}
                return parsed
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Hypon HTTP {exc.code}: {detail[:500]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Hypon connection error: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Hypon returned invalid JSON: {exc}") from exc

    def login(self) -> None:
        if self.static_token:
            self.token = self.static_token
            return

        payload = {
            self.username_field: self.username,
            self.password_field: self.password,
            **self.login_extra,
        }
        result = self._request(
            self.login_method, self.login_endpoint, payload, authenticated=False
        )

        token_paths = (
            "token",
            "access_token",
            "accessToken",
            "data.token",
            "data.access_token",
            "data.accessToken",
            "result.token",
            "result.access_token",
        )
        token = find_value(result, token_paths)
        if not token:
            raise RuntimeError(
                "Login succeeded but no token was found. Set token manually or "
                "adjust login_endpoint/fields. Response keys: "
                + ", ".join(result.keys())
            )
        self.token = str(token)
        LOG.info("Authenticated with Hypon Cloud")

    def fetch(self) -> Dict[str, Any]:
        if not self.token:
            self.login()

        try:
            payload = self.monitor_body if self.monitor_method != "GET" else None
            result = self._request(
                self.monitor_method, self.monitor_endpoint, payload, authenticated=True
            )
        except RuntimeError as exc:
            if "401" not in str(exc) and "403" not in str(exc) and "50008" not in str(exc):
                raise
            LOG.warning("Hypon token rejected; logging in again")
            self.token = None
            self.login()
            payload = self.monitor_body if self.monitor_method != "GET" else None
            result = self._request(
                self.monitor_method, self.monitor_endpoint, payload, authenticated=True
            )

        self.last_raw = result
        return result


class MeasurementMapper:
    def __init__(self, config: configparser.SectionProxy):
        self.power_keys = self._keys(config, "power_keys", "power_pv,solar_power,pv_power,power")
        self.energy_keys = self._keys(
            config, "energy_keys", "total_generation,total_energy,energy_total,e_total"
        )
        self.today_keys = self._keys(
            config, "today_energy_keys", "today_generation,today_energy,e_day"
        )
        self.voltage_keys = self._keys(
            config, "voltage_keys", "voltage,ac_voltage,vac"
        )
        self.current_keys = self._keys(
            config, "current_keys", "current,ac_current,iac"
        )
        self.frequency_keys = self._keys(
            config, "frequency_keys", "frequency,ac_frequency,freq"
        )
        self.phase_count = config.getint("phase_count", 1)
        self.default_voltage = config.getfloat("default_voltage", 230.0)
        self.default_frequency = config.getfloat("default_frequency", 50.0)
        self.standby_power = config.getfloat("standby_power", 1.0)
        self.energy_multiplier = config.getfloat("energy_multiplier", 1.0)
        self.power_multiplier = config.getfloat("power_multiplier", 1.0)

    @staticmethod
    def _keys(config: configparser.SectionProxy, key: str, default: str) -> Tuple[str, ...]:
        return tuple(x.strip() for x in config.get(key, default).split(",") if x.strip())

    def map(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        raw_power = find_value(raw, self.power_keys)
        power = as_float(raw_power)

        if power is None:
            raise ValueError("Hypon response did not contain a valid PV power value")

        power *= self.power_multiplier
        if abs(power) < self.standby_power:
            power = 0.0

        energy = as_float(find_value(raw, self.energy_keys))
        if energy is not None:
            energy *= self.energy_multiplier

        today_energy = as_float(find_value(raw, self.today_keys))
        voltage = as_float(find_value(raw, self.voltage_keys), self.default_voltage)
        current = as_float(find_value(raw, self.current_keys))
        frequency = as_float(
            find_value(raw, self.frequency_keys), self.default_frequency
        )

        if current is None:
            current = power / voltage if voltage else 0.0

        result: Dict[str, Any] = {
            "power": max(0.0, power),
            "energy": energy,
            "today_energy": today_energy,
            "voltage": voltage,
            "current": max(0.0, current),
            "frequency": frequency,
            "phases": {},
        }

        # Support common explicit phase fields when available.
        phase_power_keys = {
            1: ("power_l1", "power_L1", "l1_power", "phase_a_power", "pac1"),
            2: ("power_l2", "power_L2", "l2_power", "phase_b_power", "pac2"),
            3: ("power_l3", "power_L3", "l3_power", "phase_c_power", "pac3"),
        }
        explicit = False
        for number in range(1, self.phase_count + 1):
            p = as_float(find_value(raw, phase_power_keys[number]))
            if p is not None:
                explicit = True
                result["phases"][number] = {
                    "power": max(0.0, p * self.power_multiplier),
                    "voltage": voltage,
                    "frequency": frequency,
                }

        if not explicit:
            split = result["power"] / self.phase_count
            for number in range(1, self.phase_count + 1):
                result["phases"][number] = {
                    "power": split,
                    "voltage": voltage,
                    "frequency": frequency,
                }

        for phase in result["phases"].values():
            phase["current"] = phase["power"] / phase["voltage"] if phase["voltage"] else 0.0

        return result


def fmt_w(_path: str, value: Any) -> str:
    return "---" if value is None else f"{value:.0f} W"


def fmt_a(_path: str, value: Any) -> str:
    return "---" if value is None else f"{value:.2f} A"


def fmt_v(_path: str, value: Any) -> str:
    return "---" if value is None else f"{value:.1f} V"


def fmt_hz(_path: str, value: Any) -> str:
    return "---" if value is None else f"{value:.2f} Hz"


def fmt_kwh(_path: str, value: Any) -> str:
    return "---" if value is None else f"{value:.2f} kWh"


def fmt_int(_path: str, value: Any) -> str:
    return "---" if value is None else str(int(value))


class HyponPvDbusService:
    def __init__(self):
        self.api = HyponApi(CONFIG["HYPON"])
        self.mapper = MeasurementMapper(CONFIG["MAPPING"])
        self.interval = max(5, CONFIG["HYPON"].getint("refresh_time", 30))
        self.failure_timeout = CONFIG["HYPON"].getint("failure_timeout", 300)
        self.last_success = 0.0
        self.update_index = 0

        instance = CONFIG["DEFAULT"].getint("device_instance")
        service_name = f"com.victronenergy.pvinverter.hypon_{instance}"
        self.service = VeDbusService(service_name, register=False)

        self._add_management_paths(instance)
        self._add_measurement_paths()
        self.service.register()

        # First update shortly after registration, then keep polling.
        GLib.timeout_add(500, self._poll)
        LOG.info("Registered %s on D-Bus", service_name)

    def _add_management_paths(self, instance: int) -> None:
        name = CONFIG["DEFAULT"]["device_name"]
        position = CONFIG["PV"].getint("position")
        max_power = CONFIG["PV"].getint("max_power")

        self.service.add_path("/Mgmt/ProcessName", __file__)
        self.service.add_path(
            "/Mgmt/ProcessVersion",
            f"{VERSION}; Python {platform.python_version()}",
        )
        self.service.add_path("/Mgmt/Connection", "Hypon Cloud REST API")
        self.service.add_path("/DeviceInstance", instance)
        self.service.add_path("/ProductId", 0xFFFF)
        self.service.add_path("/ProductName", "Hypon Cloud PV Inverter")
        self.service.add_path("/CustomName", name)
        self.service.add_path("/FirmwareVersion", VERSION)
        self.service.add_path("/Connected", 0)
        self.service.add_path("/ErrorCode", 0)
        self.service.add_path("/StatusCode", 8)
        self.service.add_path("/Position", position)
        self.service.add_path("/Ac/Position", position, gettextcallback=fmt_int)
        self.service.add_path("/Ac/MaxPower", max_power, gettextcallback=fmt_w)
        self.service.add_path("/UpdateIndex", 0, gettextcallback=fmt_int)

    def _add_measurement_paths(self) -> None:
        self.service.add_path("/Ac/Power", 0.0, gettextcallback=fmt_w)
        self.service.add_path("/Ac/Current", 0.0, gettextcallback=fmt_a)
        self.service.add_path("/Ac/Voltage", 230.0, gettextcallback=fmt_v)
        self.service.add_path("/Ac/Energy/Forward", None, gettextcallback=fmt_kwh)
        self.service.add_path("/Ac/Energy/Today", None, gettextcallback=fmt_kwh)

        for phase in (1, 2, 3):
            prefix = f"/Ac/L{phase}"
            self.service.add_path(prefix + "/Power", None, gettextcallback=fmt_w)
            self.service.add_path(prefix + "/Current", None, gettextcallback=fmt_a)
            self.service.add_path(prefix + "/Voltage", None, gettextcallback=fmt_v)
            self.service.add_path(prefix + "/Frequency", None, gettextcallback=fmt_hz)
            self.service.add_path(prefix + "/Energy/Forward", None, gettextcallback=fmt_kwh)

    def _set_measurements(self, values: Dict[str, Any]) -> None:
        self.service["/Ac/Power"] = round(values["power"], 1)
        self.service["/Ac/Current"] = round(values["current"], 2)
        self.service["/Ac/Voltage"] = round(values["voltage"], 1)
        self.service["/Ac/Energy/Forward"] = (
            None if values["energy"] is None else round(values["energy"], 3)
        )
        self.service["/Ac/Energy/Today"] = (
            None if values["today_energy"] is None else round(values["today_energy"], 3)
        )

        for phase in (1, 2, 3):
            prefix = f"/Ac/L{phase}"
            data = values["phases"].get(phase)
            if data is None:
                self.service[prefix + "/Power"] = None
                self.service[prefix + "/Current"] = None
                self.service[prefix + "/Voltage"] = None
                self.service[prefix + "/Frequency"] = None
                continue
            self.service[prefix + "/Power"] = round(data["power"], 1)
            self.service[prefix + "/Current"] = round(data["current"], 2)
            self.service[prefix + "/Voltage"] = round(data["voltage"], 1)
            self.service[prefix + "/Frequency"] = round(data["frequency"], 2)

        self.service["/Connected"] = 1
        self.service["/ErrorCode"] = 0
        self.service["/StatusCode"] = 7 if values["power"] >= 10 else 8
        self.update_index = (self.update_index + 1) % 256
        self.service["/UpdateIndex"] = self.update_index

    def _poll(self) -> bool:
        try:
            raw = self.api.fetch()
            values = self.mapper.map(raw)
            self._set_measurements(values)
            self.last_success = time.time()
            LOG.info(
                "Hypon PV: %.0f W, total=%s kWh",
                values["power"],
                "unknown" if values["energy"] is None else f"{values['energy']:.3f}",
            )
            if LOG.isEnabledFor(logging.DEBUG):
                LOG.debug("Raw Hypon response: %s", json.dumps(raw, separators=(",", ":")))
        except Exception:
            LOG.exception("Could not update Hypon data")
            if self.last_success == 0 or time.time() - self.last_success > self.failure_timeout:
                self.service["/Connected"] = 0
                self.service["/ErrorCode"] = 1
                self.service["/StatusCode"] = 0

        GLib.timeout_add_seconds(self.interval, self._poll)
        return False


def main() -> None:
    DBusGMainLoop(set_as_default=True)
    HyponPvDbusService()
    LOG.info("Starting GLib main loop")
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
