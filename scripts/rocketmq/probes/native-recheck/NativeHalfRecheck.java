// Isolated 5.5.1 feasibility probe. Not a production recovery command.
import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import java.util.Set;
import org.apache.rocketmq.acl.common.AclUtils;
import org.apache.rocketmq.client.exception.MQBrokerException;
import org.apache.rocketmq.client.exception.MQClientException;
import org.apache.rocketmq.common.message.MessageConst;
import org.apache.rocketmq.common.message.MessageExt;
import org.apache.rocketmq.tools.admin.DefaultMQAdminExt;

public final class NativeHalfRecheck {
    public static void main(String[] args) {
        DefaultMQAdminExt admin = null;
        boolean attempted = false;
        JSONObject result = null;
        String stage = "request";
        int exitCode = 0;
        boolean closed = true;
        JSONObject checks = new JSONObject();
        try {
            NativeHalfIdentity.require(args.length == 0);
            NativeHalfIdentity.require("true".equals(System.getenv("GITHUB_ACTIONS")));
            String project = System.getenv("M3_NATIVE_RECHECK_PROJECT");
            NativeHalfIdentity.require(project != null && project.matches("rocketmq-m2-[a-z0-9-]{1,70}"));
            byte[] raw = System.in.readNBytes(16_385);
            NativeHalfIdentity.require(raw.length > 0 && raw.length <= 16_384);
            JSONObject request = JSON.parseObject(raw, JSONObject.class);
            Set<String> fields = Set.of("mode", "source_topic", "commitlog_offset", "queue_id", "queue_offset", "expected_real_topic", "expected_owner",
                "expected_reference_sha256", "expected_wire_sha256", "expected_unique_id_sha256", "expected_retention_hours",
                "expected_route_revision");
            NativeHalfIdentity.require(request != null && request.keySet().equals(fields));
            String mode = NativeHalfIdentity.text(request, "mode");
            String topic = NativeHalfIdentity.text(request, "source_topic");
            for (String key : Set.of("commitlog_offset", "queue_id", "queue_offset")) {
                Object value = request.get(key);
                NativeHalfIdentity.require((value instanceof Long || value instanceof Integer) && ((Number) value).longValue() >= 0);
            }
            long offset = request.getLongValue("commitlog_offset");
            NativeHalfIdentity.require(mode.equals("inspect") || mode.equals("resume"));
            NativeHalfIdentity.require(topic.equals("RMQ_SYS_TRANS_HALF_TOPIC") || topic.equals("TRANS_CHECK_MAX_TIME_TOPIC"));
            for (String key : Set.of("expected_reference_sha256", "expected_wire_sha256", "expected_unique_id_sha256")) {
                NativeHalfIdentity.require(NativeHalfIdentity.text(request, key).matches("[0-9a-f]{64}"));
            }
            String owner = NativeHalfIdentity.text(request, "expected_owner");
            NativeHalfIdentity.require(Set.of("iam.mysql", "qs.mysql", "qs.mongo", "ai.mysql").contains(owner));
            String revision = NativeHalfIdentity.text(request, "expected_route_revision");
            NativeHalfIdentity.require(revision.matches("[A-Za-z0-9_.-]{1,128}"));
            String realTopic = NativeHalfIdentity.text(request, "expected_real_topic");
            NativeHalfIdentity.require(realTopic.matches("[A-Za-z0-9_.%_-]{1,255}"));
            stage = "admin_start";
            admin = new DefaultMQAdminExt(AclUtils.getAclRPCHook("/opt/rocketmq/conf/tools.yml"), 8_000);
            admin.setNamesrvAddr("nameserver:9876");
            admin.setVipChannelEnabled(false);
            admin.start();
            stage = "broker_binding";
            Properties config = admin.getBrokerConfig("127.0.0.1:10911");
            int hours = Integer.parseInt(config.getProperty("fileReservedTime"));
            NativeHalfIdentity.require(request.get("expected_retention_hours") instanceof Integer
                && request.getIntValue("expected_retention_hours") == hours);
            // QueryMsgByKey returns MessageClientExt.getMsgId(), which can be
            // UNIQ_KEY. It is NOT a physical offset ID. Build the physical ID
            // from the exact index offset and this fixed Broker's own address.
            NativeHalfIdentity.require(config.getProperty("brokerIP1") != null && !config.getProperty("brokerIP1").isBlank());
            InetAddress current = InetAddress.getByName(config.getProperty("brokerIP1"));
            String id = NativeHalfIdentity.physicalId(current.getAddress(), Integer.parseInt(config.getProperty("listenPort", "10911")), offset);
            stage = "physical_record";
            // 5.5.1 validates VIEW_MESSAGE_BY_ID against REAL_TOPIC for half /
            // check-max storage. Read the exact local offset directly, without
            // DefaultMQAdminExt's catch-all fallback to a UNIQ_KEY search.
            MessageExt message = admin.getDefaultMQAdminExtImpl().getMqClientInstance()
                .getMQClientAPIImpl().viewMessage("127.0.0.1:10911", realTopic, offset, 8_000);
            checks.put("physical_message_present", message != null);
            NativeHalfIdentity.require(message != null);
            checks.put("source_topic", topic.equals(message.getTopic()));
            checks.put("physical_offset", message.getCommitLogOffset() == offset);
            checks.put("queue_id", message.getQueueId() == request.getLongValue("queue_id"));
            checks.put("queue_offset", message.getQueueOffset() == request.getLongValue("queue_offset"));
            checks.put("real_topic", realTopic.equals(message.getUserProperty(MessageConst.PROPERTY_REAL_TOPIC)));
            for (Object value : checks.values()) NativeHalfIdentity.require(Boolean.TRUE.equals(value));
            stage = "frozen_identity";
            byte[] body = message.getBody();
            String reference = message.getUserProperty("rm_tx_ref");
            String unique = message.getUserProperty(MessageConst.PROPERTY_UNIQ_CLIENT_MESSAGE_ID_KEYIDX);
            NativeHalfIdentity.require(body != null && body.length > 0 && body.length <= 262_144 && reference != null && unique != null);
            byte[] encoded = reference.getBytes(StandardCharsets.UTF_8);
            checks.put("bounded_reference", encoded.length <= 8192);
            checks.put("reference_sha256", NativeHalfIdentity.hash(encoded).equals(NativeHalfIdentity.text(request, "expected_reference_sha256")));
            checks.put("wire_sha256", NativeHalfIdentity.hash(body).equals(NativeHalfIdentity.text(request, "expected_wire_sha256")));
            checks.put("unique_id_sha256", NativeHalfIdentity.hash(unique.getBytes(StandardCharsets.UTF_8)).equals(NativeHalfIdentity.text(request, "expected_unique_id_sha256")));
            for (Object value : checks.values()) NativeHalfIdentity.require(Boolean.TRUE.equals(value));
            JSONObject ref = JSON.parseObject(reference);
            NativeHalfIdentity.require(owner.equals(ref.getString("owner")) && realTopic.equals(ref.getString("physical_topic"))
                && revision.equals(ref.getString("route_revision"))
                && NativeHalfIdentity.text(request, "expected_wire_sha256").equals(ref.getString("wire_hash")));
            stage = "finite_window";
            long window = NativeHalfIdentity.remaining(message.getBornTimestamp(), System.currentTimeMillis(), hours);
            boolean enqueued = false;
            if (mode.equals("resume")) {
                stage = "native_recheck";
                attempted = true;
                enqueued = admin.resumeCheckHalfMessage(realTopic, id);
                NativeHalfIdentity.require(enqueued);
            }
            result = new JSONObject();
            result.put("schema", "m3-isolated-native-recheck/v0");
            result.put("mode", mode);
            result.put("outcome", enqueued ? "RecheckEnqueued" : "NotAttempted");
            result.put("body_exported", false);
            result.put("wire_sha256", NativeHalfIdentity.hash(body));
            result.put("reference_sha256", NativeHalfIdentity.hash(encoded));
            result.put("unique_id_sha256", NativeHalfIdentity.hash(unique.getBytes(StandardCharsets.UTF_8)));
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
