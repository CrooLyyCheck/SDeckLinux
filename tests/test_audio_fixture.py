"""Actual pactl schema regression and cleanup ownership, without host audio."""

import unittest
from unittest.mock import AsyncMock, patch

from tools.audio_smoke import unload_owned_module


class FixtureCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_module_json_without_index_is_joined_to_its_owned_sink(self):
        with patch(
            "tools.audio_smoke.command",
            new_callable=AsyncMock,
            side_effect=[
                {"cookie": "epoch"},
                [{"name": "module-null-sink", "argument": "sink_name=deckbridge_test_owned"}],
                [{"name": "deckbridge_test_owned", "owner_module": 536870916}],
                None,
            ],
        ) as command:
            await unload_owned_module(536870916, "deckbridge_test_owned", "epoch")
        self.assertEqual(
            command.await_args_list[-1].args,
            ("/usr/bin/pactl", "unload-module", "536870916"),
        )

    async def test_reused_module_id_never_unloads_another_sink(self):
        with patch(
            "tools.audio_smoke.command",
            new_callable=AsyncMock,
            side_effect=[
                {"cookie": "epoch"},
                [{"name": "module-null-sink", "argument": "sink_name=somebody_else"}],
                [{"name": "somebody_else", "owner_module": 536870916}],
            ],
        ) as command:
            with self.assertRaisesRegex(RuntimeError, "ownership changed"):
                await unload_owned_module(536870916, "deckbridge_test_owned", "epoch")
        self.assertEqual(command.await_count, 3)
