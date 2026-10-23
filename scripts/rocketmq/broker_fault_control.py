"""Own one isolated Compose Broker process failure; no arbitrary host targets."""
import json
import re
import time


class OwnedBrokerFault:
    def __init__(self, command, broker, project, read_parameters, expected_parameters):
        if not re.fullmatch(r'rocketmq-m2-[a-z0-9-]+', project) or broker != project + '-broker-1':
            raise RuntimeError('exact isolated Broker identity required')
        self.command, self.broker, self.project = command, broker, project
        self.read_parameters, self.expected_parameters = read_parameters, dict(expected_parameters)
        self._id = self._pid = None
        self._killed = False

    def inspect(self):
        rows = json.loads(self.command(['docker', 'inspect', self.broker], timeout=15).stdout)
        if not isinstance(rows, list) or len(rows) != 1:
            raise RuntimeError('one exact owned Broker container required')
        row = rows[0]
        labels = row.get('Config', {}).get('Labels', {})
        if (row.get('Name') != '/' + self.broker or labels.get('com.docker.compose.project') != self.project
                or labels.get('com.docker.compose.service') != 'broker'
                or row.get('HostConfig', {}).get('RestartPolicy', {}).get('Name') != 'no'
                or not re.fullmatch('[0-9a-f]{64}', row.get('Id', ''))
                or (self._id is not None and row['Id'] != self._id)):
            raise RuntimeError('Broker container ownership or immutable identity mismatch')
        return row

    def kill(self):
        before = self.inspect()
        if self._killed or before.get('State', {}).get('Running') is not True:
            raise RuntimeError('owned Broker must be running before SIGKILL')
        self._id, self._pid = before['Id'], before['State']['Pid']
        if type(self._pid) is not int or self._pid <= 0:
            raise RuntimeError('actual owned Broker PID required')
        self.command(['docker', 'kill', '--signal', 'SIGKILL', self.broker], timeout=20)
        deadline = time.monotonic() + 5
        while True:
            state = self.inspect()['State']
            if state.get('Running') is False:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('owned Broker did not stop after SIGKILL')
            time.sleep(0.1)
        if state.get('ExitCode') != 137 or state.get('OOMKilled') is not False:
            raise RuntimeError('actual SIGKILL exit137 without OOM required')
        self._killed = True
        return dict(signal='SIGKILL', exit_code=137, automatic_restart_disabled=True,
                    immutable_container_verified=True, oom_killed=False)

    def start(self):
        if not self._killed:
            raise RuntimeError('verified owned Broker SIGKILL required before restart')
        self.inspect()
        self.command(['docker', 'start', self.broker], timeout=30)
        deadline = time.monotonic() + 100
        while True:
            state = self.inspect()['State']
            if state.get('Running') is True and state.get('Health', {}).get('Status') == 'healthy':
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('owned Broker health did not recover')
            time.sleep(0.25)
        pid = state.get('Pid')
        if type(pid) is not int or pid <= 0 or pid == self._pid:
            raise RuntimeError('same container must have an actual new Broker PID')
        actual = self.read_parameters()
        if actual != self.expected_parameters:
            raise RuntimeError('restarted Broker effective transaction parameters changed')
        return dict(same_container=True, pid_changed=True, healthy=True,
                    effective_parameters=actual)

    def wait_topic_routes(self, topics, *, timeout=90):
        """Read persisted routes from NameServer; never recreate missing topics."""
        if (not self._killed or not 0 < timeout <= 90
                or not topics or len(topics)>16 or len(set(topics))!=len(topics)
                or any(not isinstance(t,str) or not re.fullmatch('[A-Za-z0-9_-]{1,255}',t) for t in topics)):
            raise RuntimeError('exact bounded owned topic routes required')
        state=self.inspect()["State"]
        if state.get("Running") is not True or state.get("Pid")==self._pid:
            raise RuntimeError("restarted owned Broker required for route readback")
        remaining=set(topics)
        deadline=time.monotonic()+timeout
        while remaining and time.monotonic()<deadline:
            for topic in tuple(remaining):
                budget=deadline-time.monotonic()
                if budget<=0:break
                result=self.command(['docker','exec',self.broker,'java','-Xms32m','-Xmx128m',
                    '-XX:MaxDirectMemorySize=32m','-cp','/opt/rocketmq/conf:/opt/rocketmq/lib/*',
                    'org.apache.rocketmq.tools.command.MQAdminStartup','topicRoute',
                    '-n','nameserver:9876','-t',topic],required=False,timeout=min(20,budget))
                try:
                    payload=result.stdout[result.stdout.index('{'):]
                    payload=re.sub(r'(?m)^(\s*)([0-9]+):',r'\1"\2":',payload)
                    route=json.loads(payload)
                    if result.returncode==0 and route.get('brokerDatas') and route.get('queueDatas'):
                        remaining.remove(topic)
                except (ValueError,TypeError,AttributeError):
                    pass
            if remaining:time.sleep(min(2,max(0,deadline-time.monotonic())))
        if remaining:
            raise RuntimeError('persisted topic routes not registered after Broker restart')
        return dict(topic_count=len(topics),nameserver_routes_ready=True,read_only=True)

    def topic_metadata(self, topics):
        """Count exact fixture topics in live Broker metadata, not NameServer cache."""
        import secrets
        from provision_v2 import Admin
        self.inspect()
        if not topics or len(topics)>16 or any(not re.fullmatch('[A-Za-z0-9_-]{1,255}',t) for t in topics):
            raise RuntimeError('bounded exact fixture topics required')
        reader=Admin(self.broker)
        directory='/tmp/m3-topic-read-'+secrets.token_hex(8)
        reader.docker('mkdir','-m','700',directory)
        try:
            rows=reader.metadata(directory)['topicConfigTable']
            selected=[rows.get(topic,{}) for topic in topics]
            return dict(expected=len(topics),present=sum(bool(r) for r in selected),
                transaction_type=sum(r.get('attributes',{}).get('message.type')=='TRANSACTION' for r in selected),
                read_only=True)
        finally:
            reader.docker('rm','-f','--',directory+'/topic.json',directory+'/subscriptionGroup.json')
            reader.docker('rmdir',directory)
