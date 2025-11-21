import asyncio
import socket
import struct
import typing
import logging
from lbry.dht.peer import make_kademlia_peer

log = logging.getLogger(__name__)


class _LANProtocol(asyncio.DatagramProtocol):
    def __init__(self, on_packet: typing.Callable[[bytes, typing.Tuple[str, int]], None]):
        self.on_packet = on_packet

    def datagram_received(self, data: bytes, addr: typing.Tuple[str, int]):
        try:
            self.on_packet(data, addr)
        except Exception:
            log.exception("LAN discovery handler failed")


class LANDiscovery:
    def __init__(self, loop: asyncio.AbstractEventLoop, dht_node, conf):
        self.loop = loop  # Keep for compatibility but prefer get_running_loop()
        self.node = dht_node
        self.conf = conf
        self.group = getattr(conf, 'lan_discovery_group', '239.255.42.42')
        self.port = getattr(conf, 'lan_discovery_port', 54915)
        self.interval = getattr(conf, 'lan_discovery_interval', 30)
        self.transport: typing.Optional[asyncio.DatagramTransport] = None
        self._task: typing.Optional[asyncio.Task] = None
        self.sent_count = 0
        self.recv_count = 0
        self.known_peers: typing.Set[typing.Tuple[str, int]] = set()

    async def start(self):
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except OSError:
            pass
        try:
            sock.bind(('', self.port))
        except OSError as e:
            log.warning("LAN discovery bind failed on %s:%d: %s", self.group, self.port, e)
            sock.close()
            return
        mreq = struct.pack('4s4s', socket.inet_aton(self.group), socket.inet_aton('0.0.0.0'))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: _LANProtocol(self._on_packet), sock=sock
        )
        self._task = loop.create_task(self._sender())
        log.info("LAN discovery enabled on %s:%d", self.group, self.port)

    async def stop(self):
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
        self._task = None
        if self.transport:
            self.transport.close()
            self.transport = None

    async def _sender(self):
        while True:
            try:
                self._broadcast()
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                return
            except Exception:
                log.exception("LAN discovery sender error")

    def _broadcast(self):
        if not self.transport:
            return
        # message format: b"LBRYLAN v=1 udp=<udp_port> tcp=<peer_port> id=<hex8>\n"
        node_id = self.node.protocol.node_id.hex()[:8]
        msg = f"LBRYLAN v=1 udp={self.node.protocol.udp_port} tcp={self.node.protocol.peer_port} id={node_id}\n"
        try:
            self.transport.sendto(msg.encode('ascii'), (self.group, self.port))
            self.sent_count += 1
        except Exception as e:
            log.debug("LAN discovery send failed: %s", e)

    def _on_packet(self, data: bytes, addr: typing.Tuple[str, int]):
        try:
            text = data.decode('ascii', errors='ignore')
        except Exception:
            return
        if not text.startswith('LBRYLAN'):
            return
        # Extract fields; minimal: udp=<port>
        udp_port = None
        tcp_port = None
        for part in text.split():
            if part.startswith('udp='):
                try:
                    udp_port = int(part.split('=', 1)[1])
                except Exception:
                    pass
            if part.startswith('tcp='):
                try:
                    tcp_port = int(part.split('=', 1)[1])
                except Exception:
                    pass
        if not udp_port:
            return
        address = addr[0]
        if (address, udp_port) == (self.node.protocol.external_ip, self.node.protocol.udp_port):
            return  # ignore our own
        key = (address, udp_port)
        if key not in self.known_peers:
            self.known_peers.add(key)
            self.recv_count += 1
            try:
                peer = make_kademlia_peer(None, address, udp_port)
                if tcp_port:
                    peer.update_tcp_port(tcp_port)
                # enqueue a ping to validate and populate routing table
                self.node.protocol.ping_queue.enqueue_maybe_ping(peer, delay=0.0)
                log.debug("LAN discovered %s:%d (tcp:%s)", address, udp_port, tcp_port)
            except Exception:
                pass
