#!/usr/bin/env bash
set -euo pipefail
umask 027
: "${JAVA_OPT_EXT:?explicit bounded JVM options required}"
read -r -a jvm_options <<< "$JAVA_OPT_EXT"
case "${1:-}" in
  nameserver) main=(org.apache.rocketmq.namesrv.NamesrvStartup) ;;
  broker) main=(-Drmq.logback.configurationFile=/opt/rocketmq/conf/rmq.proxy.logback.xml org.apache.rocketmq.proxy.ProxyStartup -pm local -bc /etc/rocketmq/broker.conf -pc /etc/rocketmq/proxy.json) ;;
  *) echo 'expected nameserver or broker role' >&2; exit 2 ;;
esac
# Java is PID1: Docker SIGTERM reaches RocketMQ shutdown hooks directly.
exec "$JAVA_HOME/bin/java" -server -XX:+UseG1GC -XX:+ExitOnOutOfMemoryError   '-Xlog:gc*:file=/home/rocketmq/logs/gc.log:time,tags:filecount=3,filesize=10M'   "${jvm_options[@]}" -cp '/opt/rocketmq/conf:/opt/rocketmq/lib/*' "${main[@]}"
