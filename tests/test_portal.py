"""PermissionStore contract, including preservation of always-ask and other apps."""

import unittest
from unittest.mock import patch

from deckbridge.compat.sdeck.oauth.portal import (
    HANDLER,
    LEGACY,
    legacy_choices,
    read_permissions,
    set_permission,
)
from deckbridge.protocol import BridgeError


class PortalTests(unittest.TestCase):
    def test_absent_entry_is_not_created(self):
        with patch(
            "deckbridge.compat.sdeck.oauth.portal.call", return_value={"type": "as", "data": [[]]}
        ) as call:
            self.assertEqual(read_permissions(), {})
            self.assertEqual(call.call_count, 1)

    def test_exact_observed_contract(self):
        replies = [
            {"type": "as", "data": [["x-scheme-handler/streamdeck"]]},
            {
                "type": "a{sas}v",
                "data": [
                    {"": [LEGACY, "2", "3"]},
                    {"type": "a{sv}", "data": {"always-ask": {"type": "b", "data": True}}},
                ],
            },
        ]
        with patch("deckbridge.compat.sdeck.oauth.portal.call", side_effect=replies):
            self.assertEqual(read_permissions(), {"": [LEGACY, "2", "3"]})
        planned = legacy_choices({"": [LEGACY, "2", "3"], "other": ["editor", "1", "3"]})
        self.assertEqual(planned, {"": [HANDLER, "2", "3"]})

    def test_mutation_targets_one_key_and_keeps_opaque_data_untouched(self):
        with (
            patch("deckbridge.compat.sdeck.oauth.portal.call") as call,
            patch(
                "deckbridge.compat.sdeck.oauth.portal.read_permissions",
                return_value={"": [HANDLER, "2", "3"]},
            ),
        ):
            set_permission("", [HANDLER, "2", "3"])
        call.assert_called_once_with(
            "SetPermission",
            "sbssas",
            "desktop-used-apps",
            "false",
            "x-scheme-handler/streamdeck",
            "",
            "3",
            HANDLER,
            "2",
            "3",
        )

    def test_unknown_schema_is_not_overwritten(self):
        with self.assertRaisesRegex(BridgeError, "portal_choice_unrecognized"):
            legacy_choices({"": [LEGACY, "invalid-counter"]})
        with patch(
            "deckbridge.compat.sdeck.oauth.portal.call", return_value={"type": "wrong", "data": []}
        ):
            with self.assertRaisesRegex(BridgeError, "portal_invalid_response"):
                read_permissions()
