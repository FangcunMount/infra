"""CI-only bounded MySQL wire fault, scoped to the governance UPDATE's COMMIT.

It never exports SQL, authentication, packets, reference or business bodies.
Construction is inert. Startup is restricted to GitHub-hosted Linux and one
explicit loopback target; no TLS interception or production operation exists.
"""
import os
import socket
import threading


class ProtocolError(RuntimeError):
    pass


def read_packet(stream):
    def exact(size):
        parts=[]
        while size:
            chunk=stream.recv(size)
            if not chunk:
                raise EOFError('owned MySQL stream ended')
            parts.append(chunk);size-=len(chunk)
        return b''.join(parts)
    header=exact(4)
    size=int.from_bytes(header[:3],'little')
    if size>1_048_576:
        raise ProtocolError('bounded owned packet required')
    return header,exact(size)


def query(packet):
    if packet and packet[0] in (3,22):  # COM_QUERY or COM_STMT_PREPARE
        return packet[1:].strip().upper()
    return b''


def governance_update(packet):
    return query(packet).startswith(b'UPDATE MESSAGING_NATIVE_LIMIT_NOTICES SET ')


class MySQLCommitProxy:
    def __init__(self,port):
        if type(port) is not int or not 1<=port<=65535:
            raise ProtocolError('explicit owned loopback target required')
        self.target=('127.0.0.1',port)
        self.listener=None
        self.lock=threading.Lock()
        self.stopped=threading.Event()
        self.threads=[]
        self.sockets=set()
        self.events=[]
        self.mode=None
        self.active=0
        self.peak=0
        self.rejected=0
        self.acceptor=None
        self.errors=0

    def start(self):
        if (os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('RUNNER_OS')!='Linux'
                or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted'
                or os.environ.get('GITHUB_REPOSITORY')!='FangcunMount/infra'
                or self.listener is not None):
            raise ProtocolError('isolated GitHub-hosted wire fault required')
        self.listener=socket.socket()
        self.listener.bind(('127.0.0.1',0));self.listener.listen(8);self.listener.settimeout(.2)
        self.port=self.listener.getsockname()[1]
        self.acceptor=threading.Thread(target=self._accept,name='owned-mysql-accept')
        self.acceptor.start()
        return self

    def arm(self,mode):
        if mode not in ('before','after'):
            raise ProtocolError('explicit commit fault boundary required')
        with self.lock:
            if self.mode is not None:
                raise ProtocolError('previous owned fault not consumed')
            self.mode=mode

    def _accept(self):
        while not self.stopped.is_set():
            try:client,_=self.listener.accept()
            except socket.timeout:continue
            except OSError:
                if not self.stopped.is_set():self.errors+=1
                break
            with self.lock:
                if self.active>=8 or len(self.threads)>=128:
                    self.rejected+=1;client.close();continue
                self.active+=1;self.peak=max(self.peak,self.active);self.sockets.add(client)
                thread=threading.Thread(target=self._connection,args=(client,),name='owned-mysql-connection')
                self.threads.append(thread)
            thread.start()

    def _connection(self,client):
        server=None
        reply=None
        state=dict(governance=False,mode=None)
        guard=threading.Lock()
        closed=threading.Event()
        def close_pair():
            if closed.is_set():return
            closed.set()
            for stream in (client,server):
                if stream is not None:
                    try:stream.shutdown(socket.SHUT_RDWR)
                    except OSError:pass
                    stream.close()
        try:
            if self.stopped.is_set():return
            server=socket.create_connection(self.target,timeout=2);server.settimeout(None)
            with self.lock:self.sockets.add(server)
            if self.stopped.is_set():return
            def upstream():
                try:
                    while not closed.is_set():
                        header,data=read_packet(server)
                        with guard:drop=state['mode']=='after'
                        if drop:
                            with self.lock:self.events.append(dict(mode='after',commit_forwarded=True,server_ok=bool(data and data[0]==0 and header[3]==1),reply_dropped=True))
                            close_pair();return
                        client.sendall(header+data)
                except (EOFError,OSError,ProtocolError):close_pair()
            reply=threading.Thread(target=upstream,name='owned-mysql-reply')
            reply.start()
            while not closed.is_set():
                header,data=read_packet(client)
                sql=query(data)
                with guard:
                    if sql in (b'BEGIN',b'START TRANSACTION',b'ROLLBACK'):
                        state['governance']=False
                    if governance_update(data):state['governance']=True
                    if sql==b'COMMIT' and data[0]==3 and state['governance']:
                        with self.lock:
                            mode=self.mode;self.mode=None
                        state['mode']=mode
                        if mode=='before':
                            with self.lock:self.events.append(dict(mode='before',commit_forwarded=False,server_ok=False,reply_dropped=True))
                            close_pair();return
                server.sendall(header+data)
        except (EOFError,OSError,ProtocolError):
            pass
        finally:
            close_pair()
            if reply is not None:
                reply.join(timeout=2)
                if reply.is_alive():self.errors+=1
            with self.lock:
                self.sockets.discard(client);self.sockets.discard(server);self.active-=1

    def close(self):
        self.stopped.set()
        if self.listener is not None:self.listener.close()
        with self.lock:streams=list(self.sockets)
        for stream in streams:
            try:stream.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            stream.close()
        if self.acceptor is not None:self.acceptor.join(timeout=2)
        for thread in self.threads:thread.join(timeout=2)
        with self.lock:
            drained=self.active==0 and not self.sockets and all(not t.is_alive() for t in self.threads)
        if (self.acceptor is not None and self.acceptor.is_alive()) or not drained or self.errors or self.rejected:
            raise ProtocolError('owned wire fault resources not drained')
        return dict(active=0,peak=self.peak,rejected=self.rejected,errors=self.errors,threads_drained=True)
