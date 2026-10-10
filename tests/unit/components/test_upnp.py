import asyncio
from unittest.mock import AsyncMock, Mock, call

from lbry.conf import Config
from lbry.extras.daemon.components import UPnPComponent
from lbry.testcase_async import AsyncioTestCase


class UPnPComponentTests(AsyncioTestCase):
    async def test_stop_waits_for_all_port_mappings(self):
        component = UPnPComponent(Mock(conf=Config()))
        component.upnp_redirects = {'TCP': 3333, 'UDP': 4444}
        completed = []

        async def delete(port, protocol):
            await asyncio.sleep(0)
            completed.append((port, protocol))

        component.upnp = Mock(delete_port_mapping=AsyncMock(side_effect=delete))
        await component.stop()
        self.assertCountEqual(completed, [(3333, 'TCP'), (4444, 'UDP')])
        component.upnp.delete_port_mapping.assert_has_awaits([call(3333, 'TCP'), call(4444, 'UDP')])
