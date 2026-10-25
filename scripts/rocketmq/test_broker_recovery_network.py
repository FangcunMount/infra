import copy
import unittest
from broker_recovery_network import freeze,reconnect_arguments,require_attached,require_no_unplanned_restart


class NetworkRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.container=dict(Id='broker-id',Image='image-id',Name='/original-broker-1',
            Config=dict(Labels={'com.docker.compose.project':'original','com.docker.compose.service':'broker'}),
            HostConfig=dict(NetworkMode='original_rocketmq',Memory=1342177280),
            State=dict(Status='exited',Running=False,Restarting=False,OOMKilled=False),
            RestartCount=11,NetworkSettings=dict(Networks={}))
        self.network=dict(Id='network-id',Name='original_rocketmq',Driver='bridge',Scope='local',Internal=False,
            EnableIPv6=False,IPAM={},Options={},Labels={'com.docker.compose.project':'original',
                'com.docker.compose.network':'rocketmq'},Containers={'nameserver-id':{}})
        self.expected=freeze(self.container,self.network,'nameserver-id')

    def test_only_original_stopped_container_and_existing_network_are_selected(self):
        args=reconnect_arguments(self.container,self.network,self.expected)
        self.assertEqual(args[-2:],['network-id','broker-id'])
        self.assertEqual(args[:5],['docker','--host','unix:///var/run/docker.sock','network','connect'])
        for field in ('Id','Image','HostConfig'):
            changed=copy.deepcopy(self.container);changed[field]='other'
            with self.subTest(field=field),self.assertRaises((ValueError,TypeError)):
                reconnect_arguments(changed,self.network,self.expected)
        network=copy.deepcopy(self.network);network['Containers']={}
        with self.assertRaisesRegex(ValueError,'compose_bridge'):
            reconnect_arguments(self.container,network,self.expected)

    def test_missing_endpoint_blocks_start_and_conflicting_attachment_blocks_repair(self):
        with self.assertRaisesRegex(ValueError,'endpoint_required'):
            require_attached(self.container,self.network,self.expected)
        self.container['NetworkSettings']['Networks']={'unexpected':{}}
        with self.assertRaisesRegex(ValueError,'only_missing'):
            reconnect_arguments(self.container,self.network,self.expected)
        self.container['NetworkSettings']['Networks']={'original_rocketmq':
            dict(NetworkID='network-id',Aliases=['broker','original-broker-1'])}
        require_attached(self.container,self.network,self.expected)

    def test_running_true_does_not_hide_automatic_restart(self):
        self.container['State'].update(Status='running',Running=True)
        for count,restarting in ((11,False),(1,False),(0,True)):
            self.container['RestartCount']=count;self.container['State']['Restarting']=restarting
            with self.subTest(count=count,restarting=restarting),self.assertRaises(ValueError):
                require_no_unplanned_restart(self.container)
        self.container['RestartCount']=0;self.container['State']['Restarting']=False
        require_no_unplanned_restart(self.container)


if __name__=='__main__':unittest.main()
