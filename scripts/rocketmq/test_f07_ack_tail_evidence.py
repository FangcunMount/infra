import unittest

from f07_ack_tail_evidence import match_ack


class PhysicalAckMatchingTest(unittest.TestCase):
    def test_ack_requires_matching_identity_and_checkpoint_membership(self):
        identity = dict(t='topic', c='group', q=1, so=10, pt=123, bn='broker')
        checkpoint = dict(identity, n=2, d=[0, 3])
        ack = dict(identity, ao=13)
        self.assertEqual(match_ack(checkpoint, ack, 'ack'),
                         match_ack(checkpoint, dict(identity, aol=[10, 13]), 'bAck'))
        for altered in (dict(ack, ao=11), dict(ack, q=2), dict(ack, pt=124)):
            with self.subTest(ack=altered), self.assertRaises(ValueError):
                match_ack(checkpoint, altered, 'ack')
        with self.assertRaises(ValueError):
            match_ack(checkpoint, dict(identity, aol=[13, 13]), 'bAck')

    def test_empty_checkpoint_cannot_cover_a_receipt(self):
        identity = dict(t='topic', c='group', q=1, so=10, pt=123, bn='broker')
        with self.assertRaises(ValueError):
            match_ack(dict(identity, n=0), dict(identity, ao=10), 'ack')
