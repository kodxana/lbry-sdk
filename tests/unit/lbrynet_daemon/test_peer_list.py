from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from lbry.extras.daemon.components import DHT_COMPONENT, TRACKER_ANNOUNCER_COMPONENT
from lbry.extras.daemon.daemon import Daemon
from lbry.testcase_async import AsyncioTestCase


class PeerListTests(AsyncioTestCase):
    async def test_combines_tracker_and_dht_peers(self):
        blob_hash = 'ab' * 48
        first = SimpleNamespace(node_id=None, address='1.2.3.4', udp_port=4444, tcp_port=3333)
        second = SimpleNamespace(node_id=b'\x01' * 48, address='1.2.3.5', udp_port=4444, tcp_port=3333)
        tracker = Mock(get_kademlia_peer_list=AsyncMock(return_value=[first]))

        async def dht_peers(value, queue):
            self.assertEqual(value, blob_hash)
            queue.put_nowait([first, second])

        manager = Mock()
        manager.has_component.side_effect = lambda component: component in (
            DHT_COMPONENT, TRACKER_ANNOUNCER_COMPONENT
        )
        manager.get_component.return_value = tracker
        daemon = Mock(component_manager=manager, dht_node=Mock(_peers_for_value_producer=dht_peers))
        result = await Daemon.jsonrpc_peer_list(daemon, blob_hash, page_size=1)
        self.assertEqual(result['total_items'], 2)
        self.assertEqual(result['total_pages'], 2)
        self.assertEqual(result['items'], [{
            'node_id': None, 'address': first.address, 'udp_port': 4444, 'tcp_port': 3333
        }])
        tracker.get_kademlia_peer_list.assert_awaited_once_with(bytes.fromhex(blob_hash))
