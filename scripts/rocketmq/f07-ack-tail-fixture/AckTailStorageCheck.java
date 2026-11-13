package org.apache.rocketmq.broker.processor;

import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import org.apache.rocketmq.broker.BrokerController;
import org.apache.rocketmq.common.BrokerConfig;
import org.apache.rocketmq.common.PopAckConstants;
import org.apache.rocketmq.common.UtilAll;
import org.apache.rocketmq.common.message.MessageDecoder;
import org.apache.rocketmq.common.message.MessageExt;
import org.apache.rocketmq.remoting.netty.NettyClientConfig;
import org.apache.rocketmq.remoting.netty.NettyServerConfig;
import org.apache.rocketmq.store.MessageStore;
import org.apache.rocketmq.store.SelectMappedBufferResult;
import org.apache.rocketmq.store.config.MessageStoreConfig;
import org.apache.rocketmq.store.queue.ConsumeQueueInterface;
import org.apache.rocketmq.store.queue.CqUnit;

public final class AckTailStorageCheck {
    private static final String TOPIC = "rmq_sys_REVIVE_LOG_FangcunMount";
    private static final String CHECKPOINT = "{\"t\":\"isolated\",\"c\":\"group\",\"q\":0,\"so\":100,\"pt\":42,\"bn\":\"broker\",\"n\":2,\"d\":[0,3]}";
    private static final String ACK = "{\"t\":\"isolated\",\"c\":\"group\",\"q\":0,\"so\":100,\"pt\":42,\"bn\":\"broker\",\"ao\":103}";
    private static final InetSocketAddress LOCAL = new InetSocketAddress("127.0.0.1", 10911);
    private static final Method ADVANCE;

    static {
        try {
            ADVANCE = PopReviveService.class.getDeclaredMethod("advanceVerifiedAckTail", long.class);
            ADVANCE.setAccessible(true);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static void main(String[] args) throws Exception {
        Fixture fixture = new Fixture(args[0]);
        fixture.record(1, 0, "ck", CHECKPOINT, false);
        fixture.record(2, 0, "ack", ACK, false);
        fixture.expect("committed CK and retained ACK", 1, 2);

        fixture.record(3, 0, "ack", ACK.replace("group", "other"), false);
        fixture.record(4, 0, "ack", ACK, false);
        fixture.expect("verified prefix stops at unmatched ACK", 1, 2);
        fixture.expect("later matching ACK remains behind the gap", 2, 2);

        fixture.record(2, 0, "ack", ACK.replace("\"pt\":42", "\"pt\":41"), false);
        fixture.expect("old POP", 1, 1);
        fixture.record(2, 0, "ack", ACK.replace("broker", "other"), false);
        fixture.expect("other source broker", 1, 1);
        fixture.record(2, 0, "ack", ACK.replace("\"q\":0", "\"q\":1"), false);
        fixture.expect("other source queue", 1, 1);
        fixture.record(2, 0, "ack", ACK.replace("\"ao\":103", "\"ao\":4294967399"), false);
        fixture.expect("offset overflow cannot alias a valid ACK", 1, 1);
        fixture.record(2, 1, "ack", ACK, false);
        fixture.expect("other physical revive queue", 1, 1);
        fixture.record(2, 0, "ck", CHECKPOINT, false);
        fixture.expect("pending CK remains visible", 1, 1);
        fixture.record(2, 0, "ack", ACK, true);
        fixture.expect("corrupt body CRC", 1, 1);
        fixture.record(2, 0, "ack", ACK, false);
        fixture.minimum = 2;
        fixture.expect("checkpoint truncated from retained index", 1, 1);

        fixture.clear();
        fixture.record(1, 0, "ck", CHECKPOINT, false);
        for (long offset = 2; offset <= 130; offset++) {
            fixture.record(offset, 0, "ack", ACK, false);
        }
        fixture.expect("checkpoint outside bounded lookback", 129, 129);
        fixture.expect("bounded forward scan", 1, 33);
        fixture.expect("forward scan resumes in following batch", 33, 65);

        fixture.clear();
        fixture.record(1, 0, "ck", CHECKPOINT, false);
        fixture.record(2, 0, "ck", CHECKPOINT.replace("\"n\":2,\"d\":[0,3]", "\"n\":1,\"d\":[0]"), false);
        fixture.record(3, 0, "ack", ACK.replace("\"ao\":103", "\"ao\":100"), false);
        fixture.expect("same-key physical CK collision holds the cursor", 2, 2);

        fixture.clear();
        fixture.record(1, 0, "ck", CHECKPOINT, false);
        fixture.record(3, 0, "ck", CHECKPOINT.replace("\"n\":2,\"d\":[0,3]", "\"n\":1,\"d\":[0]"), false);
        fixture.record(4, 0, "ack", ACK.replace("\"ao\":103", "\"ao\":100"), false);
        fixture.expect("an unreadable committed slot cannot hide a same-key CK", 3, 3);

        fixture.record(2, 0, "ck", CHECKPOINT, true);
        fixture.expect("a corrupt committed CK cannot be skipped", 3, 3);
        fixture.record(2, 0, "ck", "null", false);
        fixture.expect("an empty decoded committed CK cannot be skipped", 3, 3);
        fixture.record(2, 0, "ck", "{broken", false);
        fixture.expect("a malformed committed CK cannot be skipped", 3, 3);

        fixture.clear();
        fixture.record(1, 0, "ck", CHECKPOINT, false);
        fixture.record(2, 0, "ack", ACK, false);
        fixture.record(3, 0, "ack", "{broken", false);
        fixture.expect("a malformed tail ACK stops after the valid prefix", 1, 2);

        System.out.println("ACK-tail encoded storage checks passed");
    }

    private static final class Fixture {
        private final Map<Long, byte[]> records = new HashMap<>();
        private final BrokerController controller;
        private long minimum = 1;
        private long end = 1;

        Fixture(String storePath) {
            BrokerConfig config = new BrokerConfig();
            config.setBrokerName("broker");
            MessageStoreConfig store = new MessageStoreConfig();
            store.setStorePathRootDir(storePath);
            controller = new BrokerController(config, new NettyServerConfig(), new NettyClientConfig(), store);
            ConsumeQueueInterface queue = (ConsumeQueueInterface) Proxy.newProxyInstance(
                getClass().getClassLoader(), new Class<?>[] {ConsumeQueueInterface.class}, (proxy, method, args) -> {
                    switch (method.getName()) {
                        case "getMinOffsetInQueue": return minimum;
                        case "getMaxOffsetInQueue": return end;
                        case "get":
                            long offset = (long) args[0];
                            byte[] record = records.get(offset);
                            return record == null || offset < minimum ? null : new CqUnit(offset, offset, record.length, 0);
                        default: throw new AssertionError(method);
                    }
                });
            MessageStore messageStore = (MessageStore) Proxy.newProxyInstance(
                getClass().getClassLoader(), new Class<?>[] {MessageStore.class}, (proxy, method, args) -> {
                    switch (method.getName()) {
                        case "dispatchBehindBytes": return 0L;
                        case "getConsumeQueue":
                            if (!TOPIC.equals(args[0]) || (int) args[1] != 0) {
                                throw new AssertionError("unexpected queue");
                            }
                            return queue;
                        case "selectOneMessageByOffset":
                            long offset = (long) args[0];
                            byte[] record = records.get(offset);
                            return record == null ? null : new SelectMappedBufferResult(
                                offset, ByteBuffer.wrap(record), record.length, null);
                        default: throw new AssertionError(method);
                    }
                });
            controller.setMessageStore(messageStore);
        }

        void record(long offset, int queue, String tags, String json, boolean corrupt) throws Exception {
            MessageExt message = new MessageExt();
            message.setTopic(TOPIC);
            message.setQueueId(queue);
            message.setQueueOffset(offset);
            message.setCommitLogOffset(offset);
            message.setTags(tags);
            message.setBornHost(LOCAL);
            message.setStoreHost(LOCAL);
            byte[] body = json.getBytes(StandardCharsets.UTF_8);
            message.setBody(body);
            message.setBodyCRC(UtilAll.crc32(body) + (corrupt ? 1 : 0));
            records.put(offset, MessageDecoder.encode(message, false));
            end = Math.max(end, offset + 1);
        }

        void clear() {
            records.clear();
            minimum = 1;
            end = 1;
        }

        void expect(String name, long committed, long expected) throws Exception {
            controller.getConsumerOffsetManager().commitOffset("test", PopAckConstants.REVIVE_GROUP, TOPIC, 0, committed);
            PopReviveService service = new PopReviveService(controller, TOPIC, 0);
            service.setShouldRunPopRevive(true);
            long returned = (long) ADVANCE.invoke(service, committed);
            long stored = controller.getConsumerOffsetManager().queryOffset(PopAckConstants.REVIVE_GROUP, TOPIC, 0);
            if (returned != expected || stored != expected) {
                throw new AssertionError(name + ": expected " + expected + ", got " + returned + "/" + stored);
            }
            System.out.println("passed " + name);
        }

    }
}
