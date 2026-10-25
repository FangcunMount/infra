import json
import unittest
from admin_rotation import prepare,rotate


def original():
    admin=dict(username='admin',password='1'*64)
    return {'broker.conf':'fileReservedTime=48\ninitAuthenticationUser='+json.dumps(admin)+'\ninnerClientAuthenticationCredentials=unchanged\n',
            'proxy.json':json.dumps(dict(initAuthenticationUser=json.dumps(admin),tlsKeyPath='unchanged',other=dict(budget=9))),
            'tools.yml':'accessKey: "admin"\nsecretKey: '+json.dumps(admin['password'])+'\n'}


class RotationTest(unittest.TestCase):
    def test_all_admin_copies_change_without_changing_other_settings(self):
        old,new,changed=prepare(original(),'2'*64)
        self.assertEqual(old['username'],new['username'])
        self.assertIn('innerClientAuthenticationCredentials=unchanged',changed['broker.conf'])
        self.assertIn('fileReservedTime=48',changed['broker.conf'])
        self.assertEqual(json.loads(changed['proxy.json'])['other'],dict(budget=9))
        self.assertEqual(prepare(changed,'3'*64)[0],new)

    def test_conflicting_or_unquoted_source_and_same_password_refused(self):
        for field in ('broker.conf','proxy.json','tools.yml'):
            value=original();value[field]=value[field].replace('1'*64,'4'*64)
            with self.subTest(field=field),self.assertRaises(ValueError):prepare(value,'2'*64)
        with self.assertRaises(ValueError):prepare(original(),'1'*64)

    def test_unknown_update_stops_before_config_write_or_restart(self):
        old,new,changed=prepare(original(),'2'*64);events=[]
        class Admin:
            def users(self):return {'admin':(old['password'],'Super','Enable')}
            def __call__(self,*args,**kwargs):raise TimeoutError()
        with self.assertRaises(TimeoutError):
            rotate(old,new,changed,old_admin=Admin(),new_admin=Admin(),persist=lambda x:events.append('write'),
                   restart=lambda:events.append('restart'),checkpoint=events.append)
        self.assertEqual(events,['original_verified','update_user_attempted'])

    def test_network_error_does_not_count_as_old_credential_rejection(self):
        old,new,changed=prepare(original(),'2'*64)
        class Admin:
            def __init__(self,account):self.account=account
            def users(self):return {'admin':(self.account['password'],'Super','Enable')}
            def __call__(self,*args,**kwargs):pass
            def raw_users(self):return 'RemotingConnectException: unavailable'
        with self.assertRaisesRegex(ValueError,'explicit_no_permission'):
            rotate(old,new,changed,old_admin=Admin(old),new_admin=Admin(new),persist=lambda x:None,
                   restart=lambda:None,checkpoint=lambda x:None)

    def test_actual_uppercase_cli_enums_and_explicit_denial(self):
        old,new,changed=prepare(original(),'2'*64);events=[]
        class Admin:
            def __init__(self,account):self.account=account
            def users(self):return {'admin':(self.account['password'],'SUPER','ENABLE')}
            def __call__(self,*args,**kwargs):events.append('update')
            def raw_users(self):return 'MQBrokerException: CODE: 16 DESC: signature rejected'
        rotate(old,new,changed,old_admin=Admin(old),new_admin=Admin(new),persist=lambda x:events.append('persist'),
               restart=lambda:events.append('restart'),checkpoint=events.append)
        self.assertEqual(events[-1],'new_success_old_denied_new_success')
        self.assertLess(events.index('update'),events.index('persist'))
        self.assertLess(events.index('persist'),events.index('restart'))


if __name__=='__main__':unittest.main()
