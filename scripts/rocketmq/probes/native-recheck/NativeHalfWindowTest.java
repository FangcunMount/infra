// Pure policy bounds only; does not construct an MQ client.
public final class NativeHalfWindowTest {
    static void rejected(long born, long now, int hours) {
        try {
            NativeHalfRecheck.remaining(born, now, hours);
        } catch (IllegalArgumentException | ArithmeticException expected) {
            return;
        }
        throw new AssertionError("unsafe finite window accepted");
    }
    public static void main(String[] args) {
        long now = 10_000_000;
        if (NativeHalfRecheck.remaining(now - 1000, now, 48) <= 120_000) throw new AssertionError();
        rejected(0, now, 48);
        rejected(now + 60_001, now, 48);
        rejected(now - 3_600_000, now, 1);
        rejected(now, now, 0);
        rejected(now, now, 8761);
        rejected(now - 3_600_000 + 120_000, now, 1);
        String id = NativeHalfRecheck.physicalId(new byte[] {127,0,0,1}, 10911, 4096);
        if (!id.equals("7F00000100002A9F0000000000001000")) throw new AssertionError();
        if (NativeHalfRecheck.physicalId(new byte[16],10911,0).length() != 56) throw new AssertionError();
        try { NativeHalfRecheck.physicalId(new byte[4],10911,-1); throw new AssertionError(); }
        catch (IllegalArgumentException expected) { }
        try { NativeHalfRecheck.physicalId(new byte[4],0,1); throw new AssertionError(); }
        catch (IllegalArgumentException expected) { }
        System.out.println("M3_NATIVE_WINDOW {\"passed\":11,\"failed\":0,\"skipped\":0,\"network_started\":false}");
    }
}
