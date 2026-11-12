package org.apache.rocketmq.broker.processor;

import java.lang.reflect.Proxy;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;
import org.apache.rocketmq.common.attribute.CQType;
import org.apache.rocketmq.common.message.MessageAccessor;
import org.apache.rocketmq.common.message.MessageConst;
import org.apache.rocketmq.common.message.MessageDecoder;
import org.apache.rocketmq.common.message.MessageExt;
import org.apache.rocketmq.store.MessageStore;
import org.apache.rocketmq.store.SelectMappedBufferResult;
import org.apache.rocketmq.store.queue.ConsumeQueueInterface;
import org.apache.rocketmq.store.queue.CqUnit;

public final class RetryIndexRegression {
    private static final String TOPIC = "%RETRY%f07-fixture";
    private static final String WITNESS = "fixture-original-checkpoint";
    private static final byte[] BODY = "original synthetic body".getBytes(StandardCharsets.UTF_8);
    private static final InetSocketAddress HOST = new InetSocketAddress("127.0.0.1", 10911);

    public static void main(String[] args) throws Exception {
        Fixture oldPrefix = new Fixture(0, 4100);
        require(oldPrefix.find(oldPrefix.position(4100)) == -1 && oldPrefix.recordReads == 0, "old prefix was decoded");
        require(oldPrefix.indexReads < 20, "old prefix seek was linear");

        Fixture rotated = new Fixture(4100, 4120);
        rotated.markers.add(4116L);
        require(rotated.find(rotated.position(4110)) == rotated.position(4116), "retained witness not reused");
        require(rotated.recordReads == 9, "retained suffix was not read exactly");

        Fixture longSuffix = new Fixture(4100, 8300);
        longSuffix.markers.add(8299L);
        require(longSuffix.find(longSuffix.position(4100)) == longSuffix.position(8299), "long suffix witness lost");
        require(longSuffix.recordReads == 4199, "long suffix incomplete");

        Fixture emptyAfterRotation = new Fixture(8200, 8200);
        require(emptyAfterRotation.find(emptyAfterRotation.position(8200)) == -1, "rotated empty queue rejected");

        Fixture duplicate = new Fixture(4100, 4120);
        duplicate.markers.add(4112L);
        duplicate.markers.add(4116L);
        reject(duplicate, duplicate.position(4110), "ambiguous");

        Fixture expired = new Fixture(4100, 4120);
        expired.minimumPhysical = expired.position(4111);
        reject(expired, expired.position(4110), "outside the retained CommitLog");

        Fixture missing = new Fixture(4100, 4120);
        missing.missingOffset = 4117;
        reject(missing, missing.position(4110), "entry is unavailable");

        Fixture corrupt = new Fixture(4100, 4120);
        corrupt.badBodyOffset = 4116;
        corrupt.markers.add(4116L);
        reject(corrupt, corrupt.position(4110), "differs from the source");

        Fixture racingRetention = new Fixture(4100, 4120);
        racingRetention.rotateDuringRead = true;
        reject(racingRetention, racingRetention.position(4110), "changed during the scan");
        System.out.println("F07 retained retry index: 9 controls passed");
    }

    private static void reject(Fixture fixture, long source, String reason) throws Exception {
        try {
            fixture.find(source);
        } catch (IllegalStateException failure) {
            require(failure.getMessage().contains(reason), failure.toString());
            return;
        }
        throw new AssertionError("unsafe scan accepted: " + reason);
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static final class Fixture {
        private long minimum;
        private final long exclusiveEnd;
        private long minimumPhysical;
        private long missingOffset = -1;
        private long badBodyOffset = -1;
        private boolean rotateDuringRead;
        private int indexReads;
        private int recordReads;
        private final Set<Long> markers = new HashSet<>();

        Fixture(long minimum, long exclusiveEnd) {
            this.minimum = minimum;
            this.exclusiveEnd = exclusiveEnd;
        }

        long position(long offset) {
            return 512 * offset + 100;
        }

        long find(long sourcePosition) throws Exception {
            ConsumeQueueInterface index = (ConsumeQueueInterface) Proxy.newProxyInstance(
                getClass().getClassLoader(), new Class<?>[]{ConsumeQueueInterface.class}, (self, method, args) -> {
                    switch (method.getName()) {
                        case "getCQType": return CQType.SimpleCQ;
                        case "getMinOffsetInQueue": return minimum;
                        case "getMaxOffsetInQueue": return exclusiveEnd;
                        case "get":
                            long offset = (Long) args[0];
                            indexReads++;
                            if (offset == missingOffset || offset < minimum || offset >= exclusiveEnd) {
                                return null;
                            }
                            return new CqUnit(offset, position(offset), record(offset).length, 0);
                        default: throw new AssertionError(method);
                    }
                });
            MessageStore store = (MessageStore) Proxy.newProxyInstance(
                getClass().getClassLoader(), new Class<?>[]{MessageStore.class}, (self, method, args) -> {
                    switch (method.getName()) {
                        case "dispatchBehindBytes": return 0L;
                        case "getMinPhyOffset": return minimumPhysical;
                        case "getMaxPhyOffset": return position(exclusiveEnd + 1);
                        case "getConsumeQueue": return index;
                        case "selectOneMessageByOffset":
                            long position = (Long) args[0];
                            long offset = (position - 100) / 512;
                            byte[] raw = record(offset);
                            recordReads++;
                            if (rotateDuringRead) {
                                minimum++;
                                rotateDuringRead = false;
                            }
                            return new SelectMappedBufferResult(position, ByteBuffer.wrap(raw), raw.length, null);
                        default: throw new AssertionError(method);
                    }
                });
            MessageExt source = new MessageExt();
            source.setCommitLogOffset(sourcePosition);
            source.setBody(BODY);
            MessageAccessor.putProperty(source, MessageConst.PROPERTY_UNIQ_CLIENT_MESSAGE_ID_KEYIDX, "same-message");
            return PopReviveService.findReviveWitness(store, TOPIC, 0, WITNESS, source);
        }

        private byte[] record(long offset) throws Exception {
            MessageExt message = new MessageExt();
            message.setTopic(TOPIC);
            message.setQueueId(0);
            message.setQueueOffset(offset);
            message.setCommitLogOffset(position(offset));
            message.setBornHost(HOST);
            message.setStoreHost(HOST);
            message.setBody(offset == badBodyOffset ? new byte[]{1} : BODY);
            MessageAccessor.putProperty(message, MessageConst.PROPERTY_UNIQ_CLIENT_MESSAGE_ID_KEYIDX, "same-message");
            if (markers.contains(offset)) {
                MessageAccessor.putProperty(message, "F07_REVIVE_WITNESS", WITNESS);
            }
            return MessageDecoder.encode(message, false);
        }
    }
}
