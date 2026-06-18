#!/usr/bin/env python3
import asyncio
import glob
import json
import os
import platform
import time
from pathlib import Path

import serial


BAUD = 115200
DEFAULT_PORT = "/dev/cu.usbmodem42CEA4F10A401"
DEFAULT_BLE_NAME = "CodexFace"
DEFAULT_TIMEOUT = 8.0
DEFAULT_TRANSPORT = "auto"
DEFAULT_BLE_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
DEFAULT_BLE_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
CONFIG_PATH = Path.home() / ".codex-face.json"
CACHE_PATH = Path.home() / ".codex-face.cache.json"
BLE_CONNECT_SETTLE_SECONDS = 0.2
BLE_POST_WRITE_SECONDS = 0.25
BLE_RETRY_DELAYS = (0.0, 1.0, 2.0)


class ConfigError(RuntimeError):
    pass


def load_config() -> dict:
    config = {}
    if CONFIG_PATH.exists():
        try:
            config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid config file {CONFIG_PATH}: {exc}") from exc
    cache = {}
    if CACHE_PATH.exists():
        try:
            cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cache = {}

    serial_port = (
        os.environ.get("CODEX_FACE_PORT")
        or os.environ.get("MAGICLICK_PORT")
        or config.get("serial_port")
    )

    return {
        "transport": (os.environ.get("CODEX_FACE_TRANSPORT") or config.get("transport") or DEFAULT_TRANSPORT).lower(),
        "serial_port": serial_port,
        "ble_name": os.environ.get("CODEX_FACE_BLE_NAME") or config.get("ble_name") or DEFAULT_BLE_NAME,
        "ble_address": os.environ.get("CODEX_FACE_BLE_ADDRESS") or config.get("ble_address") or cache.get("ble_address"),
        "ble_service_uuid": (
            os.environ.get("CODEX_FACE_BLE_SERVICE_UUID")
            or config.get("ble_service_uuid")
            or DEFAULT_BLE_SERVICE_UUID
        ).lower(),
        "ble_rx_uuid": (
            os.environ.get("CODEX_FACE_BLE_RX_UUID")
            or config.get("ble_rx_uuid")
            or DEFAULT_BLE_RX_UUID
        ).lower(),
        "ble_timeout": float(os.environ.get("CODEX_FACE_BLE_TIMEOUT") or config.get("ble_timeout") or DEFAULT_TIMEOUT),
    }


def save_ble_cache(address: str) -> None:
    if not address:
        return
    try:
        CACHE_PATH.write_text(json.dumps({"ble_address": address}) + "\n", encoding="utf-8")
    except Exception:
        pass


def find_serial_port(config: dict) -> str:
    configured = config.get("serial_port")
    if configured:
        return configured

    if os.path.exists(DEFAULT_PORT):
        return DEFAULT_PORT

    ports = sorted(glob.glob("/dev/cu.usbmodem*"))
    if ports:
        return ports[0]

    raise FileNotFoundError("No MagiClick serial port found")


def send_serial(command: str, config: dict) -> str:
    port = find_serial_port(config)
    with serial.Serial(port, BAUD, timeout=0.5, write_timeout=0.5) as ser:
        time.sleep(0.25)
        ser.write((command + "\n").encode("utf-8"))
        ser.flush()
    return f"serial:{port}"


def _is_windows() -> bool:
    return platform.system() == "Windows"


async def _find_ble_device(config: dict, BleakScanner, timeout: float):
    ble_address = config.get("ble_address")
    ble_name = (config.get("ble_name") or "").strip()

    if ble_address:
        device = await asyncio.wait_for(
            BleakScanner.find_device_by_address(ble_address, timeout=timeout),
            timeout=timeout + 2,
        )
        if device is not None:
            return device

    if ble_name:
        def match_name(device, advertisement_data):
            local_name = (advertisement_data.local_name or "").strip()
            name = (device.name or "").strip()
            return ble_name in {local_name, name}

        return await asyncio.wait_for(
            BleakScanner.find_device_by_filter(match_name, timeout=timeout),
            timeout=timeout + 2,
        )

    return None


def _build_ble_client(BleakClient, device, timeout: float, service_uuid: str):
    kwargs = {"timeout": timeout}
    if not _is_windows():
        kwargs["services"] = [service_uuid]
    return BleakClient(device, **kwargs)


async def _send_ble_once(command: str, config: dict, BleakClient, BleakScanner) -> str:
    timeout = config["ble_timeout"]
    service_uuid = config["ble_service_uuid"]
    rx_uuid = config["ble_rx_uuid"]
    device = await _find_ble_device(config, BleakScanner, timeout)
    if device is None:
        target = config.get("ble_address") or config.get("ble_name") or "unknown"
        raise RuntimeError(f"Could not find BLE device: {target}")

    client = _build_ble_client(BleakClient, device, timeout, service_uuid)
    await asyncio.wait_for(client.connect(), timeout=timeout + 2)
    try:
        await asyncio.sleep(BLE_CONNECT_SETTLE_SECONDS)
        payload = (command + "\n").encode("utf-8")
        await client.write_gatt_char(rx_uuid, payload, response=True)
        await asyncio.sleep(BLE_POST_WRITE_SECONDS)
    finally:
        if client.is_connected:
            await client.disconnect()
    save_ble_cache(device.address)
    return f"ble:{device.address}"


async def _send_ble_async(command: str, config: dict) -> str:
    try:
        from bleak import BleakClient, BleakScanner
    except ImportError as exc:
        raise RuntimeError(
            "BLE transport requires bleak. Install requirements with a Python environment that supports CoreBluetooth."
        ) from exc

    last_exc = None
    for attempt, delay in enumerate(BLE_RETRY_DELAYS, start=1):
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            return await _send_ble_once(command, config, BleakClient, BleakScanner)
        except Exception as exc:
            last_exc = exc
    raise RuntimeError(f"BLE send failed after {len(BLE_RETRY_DELAYS)} attempts: {last_exc}") from last_exc


def send_ble(command: str, config: dict) -> str:
    return asyncio.run(_send_ble_async(command, config))


def send_command(command: str) -> str:
    config = load_config()
    transport = config["transport"]

    if transport == "serial":
        return send_serial(command, config)
    if transport == "ble":
        return send_ble(command, config)
    if transport != "auto":
        raise ConfigError(f"Unsupported transport: {transport}")

    serial_error = None
    try:
        return send_serial(command, config)
    except Exception as exc:
        serial_error = exc

    try:
        return send_ble(command, config)
    except Exception as ble_exc:
        raise RuntimeError(f"Serial failed: {serial_error}; BLE failed: {ble_exc}") from ble_exc
