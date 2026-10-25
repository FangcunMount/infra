import types
import unittest
from admin_audit import parse_existing_acl,read_existing_acl
from provision_v2 import parse_acl

HEADER='#Subject #Policy #Resource #Actions #SourceIPs #Decision\n'


class ExistingACLTest(unittest.TestCase):
    def test_restricted_deny_and_repeated_resource_are_preserved(self):
        raw=HEADER+'User:app Default Topic:one [Pub] [127.0.0.1] Deny\nUser:app Custom Topic:one [Get, Sub] [] Allow\n'
        result=parse_existing_acl(raw,'User:app')
        self.assertEqual(len(result['rows']),2)
        self.assertIn(['User:app','Default','Topic:one','[Pub]','[127.0.0.1]','Deny'],result['rows'])
        with self.assertRaises(RuntimeError):parse_acl(raw,'User:app')

    def test_wrong_subject_headerless_and_malformed_rows_refused(self):
        for raw in ('',HEADER+'User:other Custom Topic:one [Pub] [] Allow',HEADER+'broken'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):parse_existing_acl(raw,'User:app')

    def test_only_authoritative_absence_code_is_absent(self):
        class Admin:
            def __init__(self,text):self.text=text
            def docker(self,*args,**kwargs):return types.SimpleNamespace(stdout='',stderr=self.text,returncode=0)
        self.assertEqual(read_existing_acl(Admin('MQBrokerException: CODE: 3002 DESC: no policy'),'app')['kind'],'absent')
        for text in ('RemotingConnectException: timeout','MQBrokerException: CODE: 16 DESC: denied'):
            with self.assertRaises(RuntimeError):read_existing_acl(Admin(text),'app')


if __name__=='__main__':unittest.main()
