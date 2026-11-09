import unittest

from m5_window_broker_observe import broker_permission


SAMPLE = 'rocketmq_broker_permission{cluster="FangcunMount",node_type="broker",node_id="fixture"} 6.0'


class BrokerPermissionTest(unittest.TestCase):
    def test_uses_only_fixed_metric(self):
        self.assertEqual(broker_permission(SAMPLE + '\nrocketmq_consumer_ready_messages 8\n'), 6)
        self.assertEqual(broker_permission(SAMPLE.replace('6.0', '4')), 4)

    def test_refuses_missing_duplicate_malformed_or_wrong_broker(self):
        for raw in ('', SAMPLE + '\n' + SAMPLE, SAMPLE.replace('6.0', 'NaN'),
                    SAMPLE.replace('6.0', '6.5'), SAMPLE.replace('FangcunMount', 'other'),
                    SAMPLE.replace('node_type="broker"', 'node_type="broker",node_type="other"')):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                broker_permission(raw)
