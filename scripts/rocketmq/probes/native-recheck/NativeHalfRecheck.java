// Isolated 5.5.1 feasibility probe. Not a production recovery command.
import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import java.net.InetAddress;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Properties;
import java.util.Set;
import org.apache.rocketmq.acl.common.AclUtils;
import org.apache.rocketmq.client.exception.MQBrokerException;
import org.apache.rocketmq.client.exception.MQClientException;
import org.apache.rocketmq.common.message.MessageConst;
import org.apache.rocketmq.common.message.MessageExt;
import org.apache.rocketmq.tools.admin.DefaultMQAdminExt;

public final class NativeHalfRecheck {
    static final long MIN_REMAINING_MS = 120_000;

    static long remaining(long born, long now, int hours) {
        if (hours < 1 || hours > 8760 || born <= 0 || born > now + 60_000) {
            throw new IllegalArgumentException("invalid_retention_context");
        }
        long end = Math.addExact(born, Math.multiplyExact((long) hours, 3_600_000L));
        long value = Math.subtractExact(end, now);
        if (value <= MIN_REMAINING_MS) throw new IllegalArgumentException("finite_window_exhausted");
        return value;
    }

    static String physicalId(byte[] address, int port, long offset) {
        if ((address.length != 4 && address.length != 16) || port < 1 || port > 65535 || offset < 0) {
            throw new IllegalArgumentException("invalid_physical_context");
        }
        ByteBuffer encoded = ByteBuffer.allocate(address.length + 12);
        encoded.put(address).putInt(port).putLong(offset);
        return HexFormat.of().withUpperCase().formatHex(encoded.array());
    }

    static String hash(byte[] value) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
    }

    static String text(JSONObject request, String key) {
        Object value = request.get(key);
        if (!(value instanceof String) || ((String) value).isEmpty()) throw new IllegalArgumentException("request_shape");
        return (String) value;
    }

    static void require(boolean value) {
        if (!value) throw new IllegalArgumentException("candidate_mismatch");
    }

    public static void main(String[] args) {
        DefaultMQAdminExt admin = null;
        boolean attempted = false;
        JSONObject result = null;
        String stage = "request";
        int exitCode = 0;
        boolean closed = true;
        JSONObject checks = new JSONObject();
        try {
            require(args.length == 0);
            require("true".equals(System.getenv("GITHUB_ACTIONS")));
            String project = System.getenv("M3_NATIVE_RECHECK_PROJECT");
            require(project != null && project.matches("rocketmq-m2-[a-z0-9-]{1,70}"));
            byte[] raw = System.in.readNBytes(16_385);
            require(raw.length > 0 && raw.length <= 16_384);
            JSONObject request = JSON.parseObject(raw, JSONObject.class);
            Set<String> fields = Set.of("mode", "source_topic", "commitlog_offset", "queue_id", "queue_offset", "expected_real_topic", "expected_owner",
                "expected_reference_sha256", "expected_wire_sha256", "expected_unique_id_sha256", "expected_retention_hours",
                "expected_route_revision");
            require(request != null && request.keySet().equals(fields));
            String mode = text(request, "mode");
            String topic = text(request, "source_topic");
            for (String key : Set.of("commitlog_offset", "queue_id", "queue_offset")) {
                Object value = request.get(key);
                require((value instanceof Long || value instanceof Integer) && ((Number) value).longValue() >= 0);
            }
            long offset = request.getLongValue("commitlog_offset");
            require(mode.equals("inspect") || mode.equals("resume"));
            require(topic.equals("RMQ_SYS_TRANS_HALF_TOPIC") || topic.equals("TRANS_CHECK_MAX_TIME_TOPIC"));
            for (String key : Set.of("expected_reference_sha256", "expected_wire_sha256", "expected_unique_id_sha256")) {
                require(text(request, key).matches("[0-9a-f]{64}"));
            }
            String owner = text(request, "expected_owner");
            require(Set.of("iam.mysql", "qs.mysql", "qs.mongo", "ai.mysql").contains(owner));
            String revision = text(request, "expected_route_revision");
            require(revision.matches("[A-Za-z0-9_.-]{1,128}"));
            String realTopic = text(request, "expected_real_topic");
            require(realTopic.matches("[A-Za-z0-9_.%_-]{1,255}"));
            stage = "admin_start";
            admin = new DefaultMQAdminExt(AclUtils.getAclRPCHook("/opt/rocketmq/conf/tools.yml"), 8_000);
            admin.setNamesrvAddr("nameserver:9876");
            admin.setVipChannelEnabled(false);
            admin.start();
            stage = "broker_binding";
            Properties config = admin.getBrokerConfig("127.0.0.1:10911");
            int hours = Integer.parseInt(config.getProperty("fileReservedTime"));
            require(request.get("expected_retention_hours") instanceof Integer
                && request.getIntValue("expected_retention_hours") == hours);
            // QueryMsgByKey returns MessageClientExt.getMsgId(), which can be
            // UNIQ_KEY. It is NOT a physical offset ID. Build the physical ID
            // from the exact index offset and this fixed Broker's own address.
            require(config.getProperty("brokerIP1") != null && !config.getProperty("brokerIP1").isBlank());
            InetAddress current = InetAddress.getByName(config.getProperty("brokerIP1"));
            String id = physicalId(current.getAddress(), Integer.parseInt(config.getProperty("listenPort", "10911")), offset);
            stage = "physical_record";
            // 5.5.1 validates VIEW_MESSAGE_BY_ID against REAL_TOPIC for half /
            // check-max storage. Read the exact local offset directly, without
            // DefaultMQAdminExt's catch-all fallback to a UNIQ_KEY search.
            MessageExt message = admin.getDefaultMQAdminExtImpl().getMqClientInstance()
                .getMQClientAPIImpl().viewMessage("127.0.0.1:10911", realTopic, offset, 8_000);
            checks.put("physical_message_present", message != null);
            require(message != null);
            checks.put("source_topic", topic.equals(message.getTopic()));
            checks.put("physical_offset", message.getCommitLogOffset() == offset);
            checks.put("queue_id", message.getQueueId() == request.getLongValue("queue_id"));
            checks.put("queue_offset", message.getQueueOffset() == request.getLongValue("queue_offset"));
            checks.put("real_topic", realTopic.equals(message.getUserProperty(MessageConst.PROPERTY_REAL_TOPIC)));
            for (Object value : checks.values()) require(Boolean.TRUE.equals(value));
            stage = "frozen_identity";
            byte[] body = message.getBody();
            String reference = message.getUserProperty("rm_tx_ref");
            String unique = message.getUserProperty(MessageConst.PROPERTY_UNIQ_CLIENT_MESSAGE_ID_KEYIDX);
            require(body != null && body.length > 0 && body.length <= 262_144 && reference != null && unique != null);
            byte[] encoded = reference.getBytes(StandardCharsets.UTF_8);
            checks.put("bounded_reference", encoded.length <= 8192);
            checks.put("reference_sha256", hash(encoded).equals(text(request, "expected_reference_sha256")));
            checks.put("wire_sha256", hash(body).equals(text(request, "expected_wire_sha256")));
            checks.put("unique_id_sha256", hash(unique.getBytes(StandardCharsets.UTF_8)).equals(text(request, "expected_unique_id_sha256")));
            for (Object value : checks.values()) require(Boolean.TRUE.equals(value));
            JSONObject ref = JSON.parseObject(reference);
            require(owner.equals(ref.getString("owner")) && realTopic.equals(ref.getString("physical_topic"))
                && revision.equals(ref.getString("route_revision"))
                && text(request, "expected_wire_sha256").equals(ref.getString("wire_hash")));
            stage = "finite_window";
            long window = remaining(message.getBornTimestamp(), System.currentTimeMillis(), hours);
            boolean enqueued = false;
            if (mode.equals("resume")) {
                stage = "native_recheck";
                attempted = true;
                enqueued = admin.resumeCheckHalfMessage(realTopic, id);
                require(enqueued);
            }
            result = new JSONObject();
            result.put("schema", "m3-isolated-native-recheck/v0");
            result.put("mode", mode);
            result.put("outcome", enqueued ? "RecheckEnqueued" : "NotAttempted");
            result.put("body_exported", false);
            result.put("wire_sha256", hash(body));
            result.put("reference_sha256", hash(encoded));
            result.put("unique_id_sha256", hash(unique.getBytes(StandardCharsets.UTF_8)));
            result.put("retention_hours", hours);
            result.put("remaining_seconds", window / 1000);
            result.put("body_bytes", body.length);
        } catch (Exception failure) {
            result = new JSONObject();
            result.put("schema", "m3-isolated-native-recheck/v0");
            result.put("outcome", attempted ? "Unknown" : "NotAttempted");
            result.put("status", "unavailable");
            result.put("stage", stage);
            result.put("failure_kind", failure.getClass().getSimpleName());
            if (failure instanceof MQBrokerException) result.put("response_code", ((MQBrokerException) failure).getResponseCode());
            if (failure instanceof MQClientException) result.put("response_code", ((MQClientException) failure).getResponseCode());
            result.put("checks", checks);
            result.put("body_exported", false);
            exitCode = 1;
        } finally {
            try {
                if (admin != null) admin.shutdown();
            } catch (RuntimeException cleanup) {
                closed = false;
                exitCode = 1;
            }
        }
        result.put("admin_shutdown_returned", closed);
        System.out.println("M3_NATIVE_RECHECK " + JSON.toJSONString(result));
        if (exitCode != 0) System.exit(exitCode);
    }
}
