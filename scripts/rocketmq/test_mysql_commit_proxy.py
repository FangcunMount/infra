import io
import os
import unittest
from unittest.mock import patch

from mysql_commit_proxy import MySQLCommitProxy, ProtocolError, read_packet, query, governance_update


class Stream:
    def __init__(self,raw):self.raw=io.BytesIO(raw)
    def recv(self,n):return self.raw.read(min(n,2))


class CommitWireGuards(unittest.TestCase):
    def test_construction_and_start_refuse_outside_owned_ci_before_binding(self):
        with patch.dict(os.environ,{},clear=True):
            proxy=MySQLCommitProxy(3306)
            self.assertIsNone(proxy.listener)
            with self.assertRaises(ProtocolError):proxy.start()
            self.assertIsNone(proxy.listener)
        for port in (0,-1,65536,True,'3306'):
            with self.assertRaises(ProtocolError):MySQLCommitProxy(port)

    def test_exact_fragmented_wire_preserves_sequence_and_binary_bytes(self):
        body=b'\x03SELECT \0\xff'
        header=len(body).to_bytes(3,'little')+bytes([7])
        self.assertEqual(read_packet(Stream(header+body)),(header,body))
        with self.assertRaises(EOFError):read_packet(Stream(header+body[:-1]))
        with self.assertRaises(ProtocolError):read_packet(Stream((1_048_577).to_bytes(3,'little')+b'\0'))

    def test_only_governance_query_or_prepare_can_arm_the_commit_boundary(self):
        for kind in (3,22):
            self.assertTrue(governance_update(bytes([kind])+b'update messaging_native_limit_notices SET status=?'))
        for raw in (b'\x03SELECT \'UPDATE messaging_native_limit_notices SET\'',b'\x17UPDATE messaging_native_limit_notices SET x=1',b'\x03UPDATE rm_tx_witness SET x=1',b''):
            self.assertFalse(governance_update(raw))
        self.assertEqual(query(b'\x03  commit \n'),b'COMMIT')

    def test_fault_must_be_explicit_and_consumed_before_rearming(self):
        proxy=MySQLCommitProxy(3306)
        with self.assertRaises(ProtocolError):proxy.arm('unknown')
        proxy.arm('before')
        with self.assertRaises(ProtocolError):proxy.arm('after')
        self.assertEqual(proxy.events,[])
        self.assertTrue(proxy.close()['threads_drained'])


if __name__=='__main__':unittest.main()
