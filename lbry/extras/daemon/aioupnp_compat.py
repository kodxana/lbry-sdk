"""
Compatibility helpers for aioupnp when running on modern asyncio versions.

The upstream aioupnp 0.0.18 release still passes the deprecated ``loop=``
keyword argument to a number of ``asyncio`` APIs. Python 3.10+ removed that
argument which causes runtime ``TypeError`` exceptions during UPnP discovery.
This module patches the relevant aioupnp components at import time so that
the SDK can continue using the dependency without crashes.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

log = logging.getLogger(__name__)

_PATCHED = False


def _ensure_loop(loop: Optional[asyncio.AbstractEventLoop]) -> asyncio.AbstractEventLoop:
    """
    Return a running loop if possible, otherwise fall back to retrieving the
    current policy loop. aioupnp frequently stores a loop reference and reuses
    it later, so we preserve that behaviour while avoiding deprecated APIs.
    """
    if loop is not None:
        return loop
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.get_event_loop()


def apply_asyncio_compatibility_patch() -> None:
    """
    Patch aioupnp modules so that deprecated ``loop=`` keyword arguments are
    no longer used with modern ``asyncio`` primitives.
    """
    global _PATCHED
    if _PATCHED:
        return

    try:
        from aioupnp.protocols import ssdp as ssdp_module
        from aioupnp.protocols import scpd as scpd_module
        from aioupnp import gateway as gateway_module
    except ImportError:  # pragma: no cover - dependency is optional during tests
        log.debug("aioupnp not available; skipping compatibility patch")
        return

    if getattr(ssdp_module, "_lbry_asyncio_patch_applied", False):
        _PATCHED = True
        return

    _patch_ssdp_module(ssdp_module)
    _patch_scpd_module(scpd_module)
    _patch_gateway_module(gateway_module)

    ssdp_module._lbry_asyncio_patch_applied = True  # type: ignore[attr-defined]
    _PATCHED = True
    log.info("Applied aioupnp asyncio compatibility patch")


def _patch_ssdp_module(ssdp_module) -> None:
    SSDPProtocol = ssdp_module.SSDPProtocol
    SSDPDatagram = ssdp_module.SSDPDatagram

    def patched_init(self, multicast_address, lan_address, loop=None):
        super(SSDPProtocol, self).__init__(multicast_address, lan_address)
        self.loop = _ensure_loop(loop)
        self.transport = None
        self._pending_searches = []
        self.notifications = []
        # asyncio.Event/Queue now automatically bind to the current loop.
        # The protocol factory runs inside the target loop so we can safely
        # instantiate them without the deprecated keyword argument.
        self.connected = asyncio.Event()
        self.devices = asyncio.Queue()

    async def patched_m_search(self, address, timeout, datagrams):
        fut = self.send_m_searches(address, datagrams)
        return await asyncio.wait_for(fut, timeout)

    async def patched_listen_ssdp(lan_address, gateway_address, loop=None):
        loop_obj = _ensure_loop(loop)
        try:
            sock = SSDPProtocol.create_multicast_socket(lan_address)
            transport, protocol = await loop_obj.create_datagram_endpoint(
                lambda: SSDPProtocol(ssdp_module.SSDP_IP_ADDRESS, lan_address, loop=loop_obj),
                sock=sock
            )
            assert protocol is not None  # keep mypy happy in downstream usage
        except Exception as err:  # pragma: no cover - propagated to callers
            raise ssdp_module.UPnPError(err)
        else:
            protocol.join_group(protocol.multicast_address, protocol.bind_address)
            protocol.set_ttl(1)
        return protocol, gateway_address, lan_address

    async def patched_multi_m_search(lan_address, gateway_address, timeout=3, loop=None):
        loop_obj = _ensure_loop(loop)
        protocol, gateway_address, lan_address = await ssdp_module.listen_ssdp(
            lan_address, gateway_address, loop_obj
        )
        fut = protocol.send_m_searches(
            address=gateway_address, datagrams=list(ssdp_module.packet_generator())
        )
        loop_obj.call_later(timeout, lambda: None if not fut or fut.done() else fut.cancel())
        return protocol

    SSDPProtocol.__init__ = patched_init  # type: ignore[assignment]
    SSDPProtocol.m_search = patched_m_search  # type: ignore[assignment]
    ssdp_module.listen_ssdp = patched_listen_ssdp  # type: ignore[assignment]
    ssdp_module.multi_m_search = patched_multi_m_search  # type: ignore[assignment]

    # Relax strict header requirements so gateways missing the `SERVER` header
    # don't get discarded, and apply a sensible default for downstream logs.
    required_fields = dict(SSDPDatagram._required_fields)  # type: ignore[attr-defined]
    modified = False
    for packet_type in (SSDPDatagram._OK, SSDPDatagram._NOTIFY):  # type: ignore[attr-defined]
        fields = list(required_fields.get(packet_type, []))
        if "server" in fields:
            fields.remove("server")
            required_fields[packet_type] = fields
            modified = True
    if modified:
        SSDPDatagram._required_fields = required_fields  # type: ignore[attr-defined]

    original_datagram_init = SSDPDatagram.__init__

    def patched_datagram_init(self, packet_type, kwargs=None):
        original_datagram_init(self, packet_type, kwargs)
        if getattr(self, "server", None) is None:
            self.server = "UNKNOWN"

    SSDPDatagram.__init__ = patched_datagram_init  # type: ignore[assignment]


def _patch_scpd_module(scpd_module) -> None:
    async def patched_scpd_get(control_url, address, port, loop=None):
        loop_obj = _ensure_loop(loop)
        packet = scpd_module.serialize_scpd_get(control_url, address)
        finished = loop_obj.create_future()
        proto_factory = lambda: scpd_module.SCPDHTTPClientProtocol(packet, finished)
        try:
            transport, protocol = await loop_obj.create_connection(proto_factory, address, port)
        except ConnectionError as err:
            return {}, b'', scpd_module.UPnPError(f"{err.__class__.__name__}({str(err)})")
        assert protocol is not None

        error = None
        wait_task = asyncio.wait_for(finished, 1.0)
        body = b''
        raw_response = b''
        try:
            raw_response, body, response_code, response_msg = await wait_task
        except asyncio.TimeoutError:
            error = scpd_module.UPnPError("get request timed out")
        except scpd_module.UPnPError as err:
            error = err
            raw_response = protocol.response_buff
        finally:
            transport.close()
        if not error:
            try:
                return scpd_module.deserialize_scpd_get_response(body), raw_response, None
            except Exception as err:  # pragma: no cover - fed to callers
                error = scpd_module.UPnPError(err)

        return {}, raw_response, error

    async def patched_scpd_post(control_url, address, port, method, param_names,
                                service_id, loop=None, **kwargs):
        loop_obj = _ensure_loop(loop)
        finished = loop_obj.create_future()
        packet = scpd_module.serialize_soap_post(
            method, param_names, service_id, address.encode(), control_url.encode(), **kwargs
        )
        proto_factory = lambda: scpd_module.SCPDHTTPClientProtocol(
            packet, finished, soap_method=method, soap_service_id=service_id.decode()
        )
        try:
            transport, protocol = await loop_obj.create_connection(proto_factory, address, port)
        except ConnectionError as err:
            return {}, b'', scpd_module.UPnPError(f"{err.__class__.__name__}({str(err)})")

        try:
            raw_response, body, response_code, response_msg = await asyncio.wait_for(finished, 1.0)
        except asyncio.TimeoutError:
            return {}, b'', scpd_module.UPnPError("Timeout")
        except scpd_module.UPnPError as err:
            return {}, protocol.response_buff, err
        finally:
            transport.close()
        try:
            return (
                scpd_module.deserialize_soap_post_response(body, method, service_id.decode()),
                raw_response,
                None
            )
        except Exception as err:  # pragma: no cover
            return {}, raw_response, scpd_module.UPnPError(err)

    scpd_module.scpd_get = patched_scpd_get  # type: ignore[assignment]
    scpd_module.scpd_post = patched_scpd_post  # type: ignore[assignment]


def _patch_gateway_module(gateway_module) -> None:
    Gateway = gateway_module.Gateway

    @classmethod
    async def patched_discover_gateway(cls, lan_address, gateway_address, timeout=3,
                                       igd_args=None, loop=None):
        loop_obj = _ensure_loop(loop)
        if igd_args:
            return await cls._gateway_from_igd_args(
                lan_address, gateway_address, igd_args, timeout, loop_obj
            )
        try:
            return await asyncio.wait_for(loop_obj.create_task(
                cls._discover_gateway(lan_address, gateway_address, timeout, loop_obj)
            ), timeout)
        except asyncio.TimeoutError:
            raise gateway_module.UPnPError(f"M-SEARCH for {gateway_address}:1900 timed out")

    Gateway.discover_gateway = patched_discover_gateway  # type: ignore[assignment]
