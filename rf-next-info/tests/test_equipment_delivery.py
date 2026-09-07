import tempfile
import unittest
from pathlib import Path

from core.web_agent import AgentOutbox, WebAgentBridge, WebEventProjector
from tests.test_web_agent import decoded_event, drain_outbox


class EquipmentDeliveryTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.projector = WebEventProjector('test', b'x' * 32, decoder_version='test')
        self.outbox = AgentOutbox(Path(folder.name) / 'outbox.sqlite3', 'test')
        self.addCleanup(self.outbox.close)
        self.bridge = WebAgentBridge(self.projector, self.outbox)
        self.addCleanup(self.bridge.close)
        self.bridge.start_session('session')
        self.offset = 0

    def send(self, kind, fields, port=50000):
        self.offset += 1
        self.bridge.submit(decoded_event(kind, {'fields': fields}, offset=self.offset,
            flow=f'10.0.0.1:{port} -> 10.0.0.2:12020'))
        self.bridge.wait_until_idle()

    def identity(self, uid, port=50000):
        self.send('world_info_prefix', {'character_uid': uid, 'character_name': 'Test'}, port)

    def profile(self, item_uid, port=50000):
        self.send('player_profile_info', {'items': [{'inventory_slot': 7,
            'item_uid': item_uid, 'item_index': 1000078, 'count': 1,
            'enchant_level': 6, 'lock': False}]}, port)

    def appearance(self, uid, item_uid):
        self.send('appear_player_prefix', {'character_uid': uid, 'character_name': 'Test',
            'equipment_refs': [{'equip_part_type': 1, 'item_uid': item_uid}]}, 51000)

    def equipment(self):
        return [e for e in drain_outbox(self.outbox) if e['type'] == 'inventory.snapshot']

    def test_two_clients_both_packet_orders_and_duplicate_appearance(self):
        self.identity(123456789)
        self.identity(223456789, 50001)
        self.profile(987654)
        self.appearance(223456789, 987655)
        self.assertEqual(self.equipment(), [])
        self.profile(987655, 50001)
        self.appearance(123456789, 987654)
        events = self.equipment()
        self.assertEqual(len(events), 2)
        self.assertEqual(len({e['client_ref'] for e in events}), 2)
        self.assertEqual({e['payload']['character_uid'] for e in events}, {123456789, 223456789})
        self.assertTrue(all(e['payload']['inventory_items'][0]['equipped'] for e in events))
        self.assertEqual(self.bridge.metrics()['errors'], 0)
        self.assertFalse(self.projector._pending_equipment_profiles)
        self.appearance(123456789, 987654)
        self.assertEqual(self.equipment(), [])

    def test_unconfirmed_profile_is_not_exported(self):
        self.profile(987654)
        self.appearance(123456789, 987654)
        self.assertEqual(self.equipment(), [])

    def test_partial_decoder_correlation_is_retried_with_complete_appearance(self):
        self.identity(123456789)
        self.send('player_profile_info', {'items': [{'inventory_slot': 7,
            'item_uid': 987654, 'item_index': 1000078, 'count': 1,
            'enchant_level': 6, 'lock': False}], 'active_equipment': {
                'character_uid': 123456789, 'complete': False, 'slots': []}})
        self.assertEqual(self.equipment(), [])
        self.appearance(123456789, 987654)
        events = self.equipment()
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]['payload']['inventory_items'][0]['equipped'])

    def test_ended_session_cannot_replay_pending_profile(self):
        self.identity(123456789)
        self.profile(987654)
        self.bridge.finish_session('session')
        self.bridge.wait_until_idle()
        self.assertFalse(self.projector._pending_equipment_profiles)
        self.bridge.start_session('new-session')
        self.appearance(123456789, 987654)
        self.assertEqual(self.equipment(), [])

    def test_partial_profile_does_not_erase_confirmed_equipment(self):
        self.identity(123456789)
        self.profile(987654)
        self.appearance(123456789, 987654)
        self.assertTrue(self.equipment()[0]['payload']['inventory_items'][0]['equipped'])
        # A partial decoder result is not an authoritative replacement.
        self.send('player_profile_info', {'items': [{'inventory_slot': 8,
            'item_uid': 987655, 'item_index': 1000079, 'count': 1}],
            'active_equipment': {'character_uid': 123456789,
                'complete': False, 'slots': []}})
        self.assertEqual(self.equipment(), [])
        self.send('inventory_delta', {})  # does not change the equipment state
        equipped = list(self.projector._connection_equipped_item_uids.values())
        self.assertEqual(equipped, [{987654}])

    def test_equipment_diagnostics_distinguish_blockers_without_private_data(self):
        self.profile(987654)
        self.identity(123456789)
        self.send('appear_player_prefix', {'character_uid': 123456789,
            'character_name': 'PRIVATE_NAME', 'remaining_payload_length': 1004})
        self.appearance(123456789, 111111)
        self.send('appear_player_prefix', {'character_uid': 123456789,
            'character_name': 'PRIVATE_NAME', 'equipment_refs': []})
        self.appearance(123456789, 987654)
        diagnostic = self.bridge.metrics()['equipment_diagnostics']
        for reason in ('unconfirmed_character', 'missing_appearance',
                       'appearances_without_refs', 'no_matching_item_uids',
                       'empty_equipment_refs', 'projected_snapshots'):
            self.assertGreater(diagnostic['counts'][reason], 0)
        self.assertEqual(diagnostic['pending_profiles'], 0)
        self.assertEqual(diagnostic['last']['appearance_tail_bytes'], 1004)
        self.assertEqual(diagnostic['last']['matched_item_count'], 1)
        for private in ('PRIVATE_NAME', '123456789', '987654', '10.0.0.1'):
            self.assertNotIn(private, str(diagnostic))

    def test_outbox_durable_mode_and_sequence_survive_reopen(self):
        self.assertEqual(self.outbox.conn.execute('PRAGMA synchronous').fetchone()[0], 2)
        self.identity(123456789)
        self.profile(987654)
        self.appearance(123456789, 987654)
        drain_outbox(self.outbox)
        watermark = self.outbox.conn.execute("SELECT seq FROM sqlite_sequence WHERE name='outbox_events'").fetchone()[0]
        reopened = AgentOutbox(self.outbox.path, 'test')
        try:
            self.assertEqual(reopened.conn.execute('PRAGMA synchronous').fetchone()[0], 2)
            reopened.enqueue(self.projector.project_heartbeat(capture_state='active', outbox_pending=0, client_count=2))
            self.assertGreater(reopened.next_batch()['first_sequence'], watermark)
        finally:
            reopened.close()
