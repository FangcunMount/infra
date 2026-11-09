// Fixed 5.5.1 child of infra's reviewed Go execution wrapper. This class is
// deliberately NOT an authorization entrypoint: it requires the wrapper's
// private generated request, immutable runner and live issued coordinator.
// No business retry, synthetic COMMIT or mutation of Broker config is allowed.
import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Properties;
import java.util.Set;
import org.apache.rocketmq.acl.common.AclUtils;
import org.apache.rocketmq.common.message.MessageConst;
import org.apache.rocketmq.common.message.MessageExt;
import org.apache.rocketmq.tools.admin.DefaultMQAdminExt;

public final class NativeHalfManaged {
    public static void main(String[] args) {
        DefaultMQAdminExt admin = null;
        JSONObject result = new JSONObject();
        boolean attempted = false;
        int exitCode = 0;
        boolean closed = true;
        String stage = "request";
        try {
            NativeHalfIdentity.require(args.length == 0);
            byte[] raw = System.in.readNBytes(16_385);
            NativeHalfIdentity.require(raw.length > 0 && raw.length <= 16_384);
            JSONObject request = JSON.parseObject(raw, JSONObject.class);
            Set<String> keys = Set.of("schema", "mode", "request_sha256", "invocation_nonce", "source_sha", "native_index_sha256",
                "nameserver", "broker", "source_topic", "commitlog_offset", "queue_id", "queue_offset", "expected_real_topic", "expected_owner",
                "expected_reference_sha256", "expected_wire_sha256", "expected_unique_id_sha256", "expected_retention_hours", "expected_route_revision");
            NativeHalfIdentity.require(request != null && request.keySet().equals(keys));
            NativeHalfIdentity.require("m3-managed-native-request/v1".equals(request.getString("schema")));
            String mode = NativeHalfIdentity.text(request, "mode");
            NativeHalfIdentity.require(mode.equals("inspect") || mode.equals("resume"));
            for (String key : Set.of("request_sha256", "invocation_nonce", "native_index_sha256", "expected_reference_sha256", "expected_wire_sha256", "expected_unique_id_sha256")) {
                NativeHalfIdentity.require(NativeHalfIdentity.text(request, key).matches("[0-9a-f]{64}"));
            }
            NativeHalfIdentity.require(NativeHalfIdentity.text(request, "source_sha").matches("[0-9a-f]{40}"));
            for (String key : Set.of("commitlog_offset", "queue_id", "queue_offset")) {
                Object v = request.get(key);
                NativeHalfIdentity.require((v instanceof Long || v instanceof Integer) && ((Number)v).longValue() >= 0);
            }
            String topic = NativeHalfIdentity.text(request, "source_topic");
            NativeHalfIdentity.require(topic.equals("TRANS_CHECK_MAX_TIME_TOPIC"));
            String owner = NativeHalfIdentity.text(request, "expected_owner");
            NativeHalfIdentity.require(Set.of("iam.mysql", "qs.mysql", "qs.mongo", "ai.mysql").contains(owner));
            String realTopic = NativeHalfIdentity.text(request, "expected_real_topic");
            NativeHalfIdentity.require(realTopic.matches("[A-Za-z0-9_.%_-]{1,255}"));
            NativeHalfIdentity.require("m3-1".equals(request.getString("expected_route_revision")));
            for (String key : Set.of("nameserver", "broker")) {
                NativeHalfIdentity.require(NativeHalfIdentity.text(request,key).matches("[A-Za-z0-9_.:\\[\\]-]{1,253}:[0-9]{1,5}"));
            }
            result.put("schema", "m3-managed-native-recheck/v1");
            result.put("mode", mode);
            for (String key : Set.of("request_sha256", "invocation_nonce", "source_sha", "native_index_sha256")) result.put(key, request.getString(key));
            result.put("body_exported", false);
            result.put("outcome", "NotAttempted");

            // Credentials/config are supplied only by the frozen script/image,
            // never by a message or the generated request. No Docker socket.
            stage = "admin_start";
            admin = new DefaultMQAdminExt(AclUtils.getAclRPCHook(System.getProperty("m3.native.tools", "/opt/rocketmq/conf/tools.yml")), 8_000);
            admin.setNamesrvAddr(request.getString("nameserver"));
            admin.setVipChannelEnabled(false);
            admin.start();
            stage = "broker_binding";
            String broker = request.getString("broker");
            Properties config = admin.getBrokerConfig(broker);
            int hours = Integer.parseInt(config.getProperty("fileReservedTime"));
            NativeHalfIdentity.require(request.get("expected_retention_hours") instanceof Integer && request.getIntValue("expected_retention_hours") == hours);
            NativeHalfIdentity.require(Long.parseLong(config.getProperty("transactionTimeOut")) == 6000
                && Long.parseLong(config.getProperty("transactionCheckInterval")) == 5000
                && Integer.parseInt(config.getProperty("transactionCheckMax")) == 24);
            long offset = request.getLongValue("commitlog_offset");
            NativeHalfIdentity.require(config.getProperty("brokerIP1") != null && !config.getProperty("brokerIP1").isBlank());
            InetAddress address = InetAddress.getByName(config.getProperty("brokerIP1"));
            String id = NativeHalfIdentity.physicalId(address.getAddress(), Integer.parseInt(config.getProperty("listenPort", "10911")), offset);
            stage = "physical_record";
            MessageExt message = admin.getDefaultMQAdminExtImpl().getMqClientInstance().getMQClientAPIImpl().viewMessage(broker, realTopic, offset, 8_000);
            NativeHalfIdentity.require(message != null && topic.equals(message.getTopic()) && message.getCommitLogOffset() == offset
                && message.getQueueId() == request.getLongValue("queue_id") && message.getQueueOffset() == request.getLongValue("queue_offset")
                && realTopic.equals(message.getUserProperty(MessageConst.PROPERTY_REAL_TOPIC)));
            stage = "frozen_identity";
            byte[] body = message.getBody();
            String reference = message.getUserProperty("rm_tx_ref");
            String unique = message.getUserProperty(MessageConst.PROPERTY_UNIQ_CLIENT_MESSAGE_ID_KEYIDX);
            NativeHalfIdentity.require(body != null && body.length > 0 && body.length <= 262_144 && reference != null && unique != null);
            byte[] encoded = reference.getBytes(StandardCharsets.UTF_8);
            NativeHalfIdentity.require(encoded.length <= 8192
                && NativeHalfIdentity.hash(encoded).equals(request.getString("expected_reference_sha256"))
                && NativeHalfIdentity.hash(body).equals(request.getString("expected_wire_sha256"))
                && NativeHalfIdentity.hash(unique.getBytes(StandardCharsets.UTF_8)).equals(request.getString("expected_unique_id_sha256")));
            JSONObject ref = JSON.parseObject(reference);
            NativeHalfIdentity.require(owner.equals(ref.getString("owner")) && realTopic.equals(ref.getString("physical_topic"))
                && "m3-1".equals(ref.getString("route_revision")) && request.getString("expected_wire_sha256").equals(ref.getString("wire_hash")));
            stage = "finite_window";
            long window = NativeHalfIdentity.remaining(message.getBornTimestamp(), System.currentTimeMillis(), hours);
            result.put("wire_sha256", NativeHalfIdentity.hash(body));
            result.put("reference_sha256", NativeHalfIdentity.hash(encoded));
            result.put("unique_id_sha256", NativeHalfIdentity.hash(unique.getBytes(StandardCharsets.UTF_8)));
            result.put("retention_hours", hours);
            result.put("remaining_seconds", window / 1000);
            result.put("body_bytes", body.length);
            if (mode.equals("resume")) {
                stage = "native_recheck";
                attempted = true;
                result.put("outcome", "Unknown");
                NativeHalfIdentity.require(admin.resumeCheckHalfMessage(realTopic, id));
                result.put("outcome", "RecheckEnqueued");
            }
        } catch (Exception unavailable) {
            result.put("outcome", attempted ? "Unknown" : "NotAttempted");
            result.put("failure_stage", stage);
            result.put("failure_kind", unavailable.getClass().getSimpleName());
            exitCode = 1; // No raw exception, body, reference or credential output.
        } finally {
            try { if (admin != null) admin.shutdown(); }
            catch (RuntimeException failure) { closed = false; exitCode = 1; result.put("failure_stage", "admin_shutdown"); result.put("failure_kind", failure.getClass().getSimpleName()); }
        }
        result.put("admin_shutdown_returned", closed);
        result.put("observed_at", Instant.now().toString());
        System.out.println("M3_MANAGED_NATIVE " + JSON.toJSONString(result));
        if (exitCode != 0) System.exit(exitCode);
    }
}
