"""Read-only actual Proxy route diagnostic; creates no Producer or DB resource."""
import argparse
import asyncio
import hashlib
import ipaddress
import json
import logging
from pathlib import Path


def receipt(response, topic, attempts):
    code=int(response.status.code)
    queues=len(response.message_queues)
    if not 0 <= code <= 99999 or not 0 <= queues <= 1024 or not 1 <= attempts <= 10:
        raise RuntimeError('bounded route response required')
    return dict(code=code,queues=queues,attempts=attempts,
        topic_sha256=hashlib.sha256(topic.encode()).hexdigest(),read_only=True)


def parse_output(output, topic):
    rows=[line.removeprefix('TXPROBE ') for line in output.splitlines() if line.startswith('TXPROBE ')]
    if len(rows)!=1 or len(rows[0])>2048:
        raise RuntimeError('one bounded read-only Proxy route receipt required')
    event=json.loads(rows[0])
    value=json.loads(event['decision'])
    if (event.get('event')!='proxy_route' or set(event)!={'event','id','decision'}
            or not isinstance(value,dict) or set(value)!={'code','queues','attempts','topic_sha256','read_only'}
            or any(type(value[k]) is not int for k in ('code','queues','attempts'))
            or value['code']!=20000 or not 1 <= value['queues'] <= 1024 or not 1 <= value['attempts'] <= 10
            or value['topic_sha256']!=hashlib.sha256(topic.encode()).hexdigest()
            or value['read_only'] is not True):
        raise RuntimeError('actual authenticated Proxy route readiness missing or unsafe')
    return value


async def main(args):
    import grpc
    from rocketmq.grpc_protocol import Code, MessagingServiceStub, QueryRouteRequest, Resource
    from rocketmq.v5.client import ClientConfiguration, Credentials
    from rocketmq.v5.util import Signature
    from rocketmq.v5.log import logger
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.addHandler(logging.NullHandler())
    path=args.config.resolve()
    if path.stat().st_mode & 0o077:
        raise RuntimeError('private route fixture required')
    config=json.loads(path.read_text())
    host,port=config['endpoint'].rsplit(':',1)
    if not ipaddress.ip_address(host).is_loopback or not 1 <= int(port) <= 65535:
        raise RuntimeError('owned loopback route fixture required')
    options=ClientConfiguration(config['endpoint'],Credentials(config['accesskey'],config['secretkey']))
    request=QueryRouteRequest(topic=Resource(name=config['topic']),endpoints=options.rpc_endpoints.endpoints)
    channel=grpc.aio.secure_channel(config['endpoint'],grpc.ssl_channel_credentials(Path(config['ca']).read_bytes()))
    try:
        stub=MessagingServiceStub(channel)
        for attempt in range(1,11):
            response=await stub.QueryRoute(request,metadata=Signature.metadata(options,'m3-readonly-route-probe'),timeout=3)
            value=receipt(response,config['topic'],attempt)
            if response.status.code==Code.OK or response.status.code!=Code.TOPIC_NOT_FOUND:break
            if attempt<10:await asyncio.sleep(2)
        output='TXPROBE '+json.dumps(dict(event='proxy_route',id=args.id,decision=json.dumps(value)))
        if getattr(args,'require_ready',False):
            parse_output(output,config['topic'])
        print(output,flush=True)
    finally:
        await channel.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--mode',choices=['route-read'],required=True)
    parser.add_argument('--id',default='')
    parser.add_argument('--require-ready',action='store_true')
    try:
        asyncio.run(main(parser.parse_args()))
    except Exception:
        print('TXPROBE '+json.dumps(dict(event='failed',decision='readonly_proxy_route_unavailable')),flush=True)
        raise SystemExit(1) from None
