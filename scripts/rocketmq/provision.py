#!/usr/bin/env python3
"""Provision only explicit NORMAL topics, groups and least-privilege app ACLs."""
import argparse
import json
import re
import subprocess
from pathlib import Path
from routes import validate, physical_topic, consumer_group


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--container",required=True)
    p.add_argument("--project",required=True)
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--credentials",type=Path,required=True)
    args=p.parse_args()
    if not re.fullmatch(r"[a-z0-9-]{1,80}",args.container): p.error("invalid container")
    manifest=json.loads(args.manifest.read_text()); validate(manifest)
    if args.credentials.stat().st_mode & 0o077: p.error("private credential file required")
    accounts=json.loads(args.credentials.read_text())
    label=subprocess.check_output(["docker","inspect","--format",'{{index .Config.Labels "com.docker.compose.project"}}',args.container],text=True).strip()
    if label!=args.project: p.error("Compose project mismatch")
    operations=0

    def run(operation, *params):
        nonlocal operations
        cmd=["docker","exec",args.container,"java","-Xms32m","-Xmx128m","-XX:MaxDirectMemorySize=32m","-cp","/opt/rocketmq/conf:/opt/rocketmq/lib/*","org.apache.rocketmq.tools.command.MQAdminStartup",operation,"-b","127.0.0.1:10911",*params]
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
        # MQAdminStartup may return0 even after command failure. Require its
        # positive completion marker, never infer success from exit status alone.
        if result.returncode or " success." not in result.stdout:
            raise RuntimeError(operation+" did not report completion; credentials omitted")
        operations+=1

    for topic in sorted({r["physical_topic"] for r in manifest["routes"]}):
        run("updateTopic","-t",topic,"-r","4","-w","4","-a","+message.type=NORMAL")
    for group in sorted({r["consumer_group"] for r in manifest["routes"] if r.get("consumer_group")}):
        run("updateSubGroup","-g",group,"-r","128")
    for name, grants in manifest.get("accounts",{}).items():
        account=accounts[name]
        if len(account["password"])<32 or name in ("admin","inner"):
            raise ValueError("separate application credentials required")
        lookup = subprocess.run(["docker","exec",args.container,"java","-Xms32m","-Xmx128m","-XX:MaxDirectMemorySize=32m","-cp","/opt/rocketmq/conf:/opt/rocketmq/lib/*","org.apache.rocketmq.tools.command.MQAdminStartup","getUser","-b","127.0.0.1:10911","-u",account["username"]],capture_output=True,text=True,timeout=45)
        existing = [line.split() for line in lookup.stdout.splitlines() if line.split() and line.split()[0] == account["username"]]
        if existing:
            if len(existing)!=1 or len(existing[0])!=4 or existing[0][1]!=account["password"] or existing[0][2].lower()!="normal" or existing[0][3].lower()!="enable":
                raise RuntimeError("existing application principal differs; refuse implicit credential rotation")
        else:
            run("createUser","-u",account["username"],"-p",account["password"],"-t","Normal")
        # Per-resource actions avoid granting publish on a consume-only topic.
        permissions={}
        for topic in grants.get("publish",()): permissions.setdefault("Topic:"+physical_topic(topic),set()).update(("Pub","Get"))
        for topic,subscription in grants.get("subscriptions",()):
            permissions.setdefault("Topic:"+physical_topic(topic),set()).update(("Sub","Get"))
            permissions.setdefault("Group:"+consumer_group(topic,subscription),set()).update(("Sub","Get"))
        for resource,actions in sorted(permissions.items()):
            run("createAcl","-s","User:"+account["username"],"-r",resource,"-a",",".join(sorted(actions)),"-d","Allow")
    print(json.dumps({"version":1,"operations":operations,"normal_topics":len({r["physical_topic"] for r in manifest["routes"]}),"groups":len({r["consumer_group"] for r in manifest["routes"] if r.get("consumer_group")})}))


if __name__=="__main__":main()
