import asyncio
import socket
import time
import unittest
import typing
from unittest import mock
from lbry.testcase import AsyncioTestCase, AdvanceTimeTestCase
from tests import dht_mocks
from lbry.conf import Config
from lbry.dht import constants
from lbry.dht.node import Node
from lbry.dht.peer import PeerManager, make_kademlia_peer
from lbry.extras.daemon.storage import SQLiteStorage


class TestBootstrapDNS(AdvanceTimeTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.loop.set_debug(False)

    def make_node(self, address, urls=None):
        node = Node(self.loop, PeerManager(self.loop), constants.generate_id(),
                    4444, 4444, 3333, address)
        self.addCleanup(node.stop)
        node.start(address, urls)
        return node

    async def test_failed_hostname_does_not_block_other_seeds(self):
        for failed_position in range(3):
            with self.subTest(failed_position=failed_position), dht_mocks.mock_network_loop(self.loop):
                seeds = [self.make_node('1.2.3.1'), self.make_node('1.2.3.2')]
                await self.advance(1)
                node = None
                try:
                    urls = [('first.example', 4444), ('second.example', 4444)]
                    answers = ['1.2.3.1', '1.2.3.2']
                    urls.insert(failed_position, ('unavailable.example', 4444))
                    answers.insert(failed_position, socket.gaierror('hostname unavailable'))
                    with mock.patch('lbry.dht.node.resolve_host', side_effect=answers) as resolve:
                        node = self.make_node('1.2.3.3', urls)
                        await self.advance(0)
                        # Routing-table updates are batched every 100 ms.
                        await self.advance(0.1)
                        await self.advance(1)

                        self.assertTrue(node.joined.is_set())
                        self.assertEqual(
                            {seed.protocol.node_id for seed in seeds},
                            {peer.node_id for peer in node.protocol.routing_table.get_peers()}
                        )
                        self.assertEqual(
                            [mock.call(host, port, 'udp') for host, port in urls], resolve.await_args_list
                        )
                finally:
                    if node is not None:
                        node.stop()
                    for seed in seeds:
                        seed.stop()
                    await self.advance(0)

    async def test_retries_after_all_seed_hostnames_fail(self):
        with dht_mocks.mock_network_loop(self.loop):
            seeds = [self.make_node('1.2.3.1'), self.make_node('1.2.3.2')]
            await self.advance(0)
            answers = [socket.gaierror('hostname unavailable'), socket.gaierror('hostname unavailable'),
                       '1.2.3.1', '1.2.3.2']
            with mock.patch('lbry.dht.node.resolve_host', side_effect=answers) as resolve:
                node = self.make_node('1.2.3.3', [('first.example', 4444), ('second.example', 4444)])
                try:
                    await self.advance(0)
                    self.assertFalse(node.joined.is_set())
                    self.assertEqual(2, resolve.await_count)
                    await self.advance(29)
                    self.assertEqual(2, resolve.await_count)
                    await self.advance(1)
                    await self.advance(1)
                    self.assertEqual(4, resolve.await_count)
                    self.assertTrue(node.joined.is_set())
                finally:
                    node.stop()
                    for seed in seeds:
                        seed.stop()
                    await self.advance(0)


class TestBootstrapNode(AsyncioTestCase):
    TIMEOUT = 10.0  # do not increase. Hitting a timeout is a real failure

    async def test_bootstrap_node_adds_all_peers(self):
        loop = asyncio.get_event_loop()
        loop.set_debug(False)

        with dht_mocks.mock_network_loop(loop):
            advance = dht_mocks.get_time_accelerator(loop)
            self.bootstrap_node = Node(self.loop, PeerManager(loop), constants.generate_id(),
                                       4444, 4444, 3333, '1.2.3.4', is_bootstrap_node=True)
            self.bootstrap_node.start('1.2.3.4', [])
            self.bootstrap_node.protocol.ping_queue._default_delay = 0
            self.addCleanup(self.bootstrap_node.stop)

            # start the nodes
            nodes = {}
            futs = []
            for i in range(100):
                nodes[i] = Node(loop, PeerManager(loop), constants.generate_id(i), 4444, 4444, 3333, f'1.3.3.{i}')
                nodes[i].start(f'1.3.3.{i}', [('1.2.3.4', 4444)])
                self.addCleanup(nodes[i].stop)
                futs.append(nodes[i].joined.wait())
            await asyncio.gather(*futs)
            # Ping completion queues routing-table updates; it does not wait
            # for the routing task to finish inserting those peers.
            while len(self.bootstrap_node.protocol.routing_table.get_peers()) < len(nodes):
                await advance(1)
            self.assertEqual(100, len(self.bootstrap_node.protocol.routing_table.get_peers()))


class TestNodePingQueueDiscover(AsyncioTestCase):
    async def test_ping_queue_discover(self):
        loop = asyncio.get_event_loop()
        loop.set_debug(False)

        peer_addresses = [
            (constants.generate_id(1), '1.2.3.1'),
            (constants.generate_id(2), '1.2.3.2'),
            (constants.generate_id(3), '1.2.3.3'),
            (constants.generate_id(4), '1.2.3.4'),
            (constants.generate_id(5), '1.2.3.5'),
            (constants.generate_id(6), '1.2.3.6'),
            (constants.generate_id(7), '1.2.3.7'),
            (constants.generate_id(8), '1.2.3.8'),
            (constants.generate_id(9), '1.2.3.9'),
        ]
        with dht_mocks.mock_network_loop(loop):
            advance = dht_mocks.get_time_accelerator(loop)
            # start the nodes
            nodes: typing.Dict[int, Node] = {
                i: Node(loop, PeerManager(loop), node_id, 4444, 4444, 3333, address)
                for i, (node_id, address) in enumerate(peer_addresses)
            }
            for i, n in nodes.items():
                n.start(peer_addresses[i][1], [])

            await advance(1)

            node_1 = nodes[0]

            # ping 8 nodes from node_1, this will result in a delayed return ping
            futs = []
            for i in range(1, len(peer_addresses)):
                node = nodes[i]
                assert node.protocol.node_id != node_1.protocol.node_id
                peer = make_kademlia_peer(
                    node.protocol.node_id, node.protocol.external_ip, udp_port=node.protocol.udp_port
                )
                futs.append(node_1.protocol.get_rpc_peer(peer).ping())
            await advance(3)
            replies = await asyncio.gather(*tuple(futs))
            self.assertTrue(all(map(lambda reply: reply == b"pong", replies)))

            # run for long enough for the delayed pings to have been sent by node 1
            await advance(1000)

            # verify all of the previously pinged peers have node_1 in their routing tables
            for n in nodes.values():
                peers = n.protocol.routing_table.get_peers()
                if n is node_1:
                    self.assertEqual(8, len(peers))
                # TODO: figure out why this breaks
                # else:
                #     self.assertEqual(1, len(peers))
                #     self.assertEqual((peers[0].node_id, peers[0].address, peers[0].udp_port),
                #                      (node_1.protocol.node_id, node_1.protocol.external_ip, node_1.protocol.udp_port))

            # run long enough for the refresh loop to run
            await advance(3600)

            # verify all the nodes know about each other
            for n in nodes.values():
                if n is node_1:
                    continue
                peers = n.protocol.routing_table.get_peers()
                self.assertEqual(8, len(peers))
                self.assertSetEqual(
                    {n_id[0] for n_id in peer_addresses if n_id[0] != n.protocol.node_id},
                    {c.node_id for c in peers}
                )
                self.assertSetEqual(
                    {n_addr[1] for n_addr in peer_addresses if n_addr[1] != n.protocol.external_ip},
                    {c.address for c in peers}
                )

            # teardown
            for n in nodes.values():
                n.stop()


class TestTemporarilyLosingConnection(AsyncioTestCase):
    @unittest.SkipTest
    async def test_losing_connection(self):
        async def wait_for(check_ok, insist, timeout=20):
            start = time.time()
            while time.time() - start < timeout:
                if check_ok():
                    break
                await asyncio.sleep(0)
            else:
                insist()

        loop = self.loop
        loop.set_debug(False)

        peer_addresses = [
            ('1.2.3.4', 40000+i) for i in range(10)
        ]
        node_ids = [constants.generate_id(i) for i in range(10)]

        nodes = [
            Node(
                loop, PeerManager(loop), node_id, udp_port, udp_port, 3333, address,
                storage=SQLiteStorage(Config(), ":memory:", self.loop, self.loop.time)
            )
            for node_id, (address, udp_port) in zip(node_ids, peer_addresses)
        ]
        dht_network = {peer_addresses[i]: node.protocol for i, node in enumerate(nodes)}
        num_seeds = 3

        with dht_mocks.mock_network_loop(loop, dht_network):
            for i, n in enumerate(nodes):
                await n._storage.open()
                self.addCleanup(n.stop)
                n.start(peer_addresses[i][0], peer_addresses[:num_seeds])
            await asyncio.gather(*[n.joined.wait() for n in nodes])

            node = nodes[-1]
            advance = dht_mocks.get_time_accelerator(loop)
            await advance(500)

            # Join the network, assert that at least the known peers are in RT
            self.assertTrue(node.joined.is_set())
            self.assertTrue(len(node.protocol.routing_table.get_peers()) >= num_seeds)

            # Refresh, so that the peers are persisted
            self.assertFalse(len(await node._storage.get_persisted_kademlia_peers()) > num_seeds)
            await advance(4000)
            self.assertTrue(len(await node._storage.get_persisted_kademlia_peers()) > num_seeds)

            # We lost internet connection - all the peers stop responding
            dht_network.pop((node.protocol.external_ip, node.protocol.udp_port))

            # The peers are cleared on refresh from RT and storage
            await advance(4000)
            self.assertListEqual([], await node._storage.get_persisted_kademlia_peers())
            await wait_for(
                lambda: len(node.protocol.routing_table.get_peers()) == 0,
                lambda: self.assertListEqual(node.protocol.routing_table.get_peers(), [])
            )

            # Reconnect
            dht_network[(node.protocol.external_ip, node.protocol.udp_port)] = node.protocol

            # Check that node reconnects at least to them
            await advance(1000)
            await wait_for(
                lambda: len(node.protocol.routing_table.get_peers()) >= num_seeds,
                lambda: self.assertGreaterEqual(len(node.protocol.routing_table.get_peers()), num_seeds)
            )
