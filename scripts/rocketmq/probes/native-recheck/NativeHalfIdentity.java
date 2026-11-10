// Shared, side-effect-free identity and retention checks for the native child.
import com.alibaba.fastjson2.JSONObject;
import java.nio.ByteBuffer;
import java.security.MessageDigest;
import java.util.HexFormat;

final class NativeHalfIdentity {
    private NativeHalfIdentity() {}

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
}
