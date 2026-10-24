package privatefile

import "testing"

func TestNamedManifestKeysDoNotRelaxApprovalDecoding(t *testing.T) {
	var object struct {
		Accounts map[string]struct {
			Owner string `json:"owner"`
		} `json:"accounts"`
	}
	raw := []byte(`{"accounts":{"m3-iam":{"owner":"iam.mysql"}}}`)
	if Decode(raw, &object) == nil {
		t.Fatal("approval decoder accepted manifest-only named key")
	}
	if DecodeNamed(raw, &object, "m3-iam") != nil || object.Accounts["m3-iam"].Owner != "iam.mysql" {
		t.Fatal("known manifest account unavailable")
	}
	for _, raw := range [][]byte{[]byte(`{"accounts":{"m3-iam":{"owner":"iam.mysql"},"m3-iam":{"owner":"iam.mysql"}}}`), []byte(`{"accounts":{"M3-iam":{"owner":"iam.mysql"}}}`), []byte(`{"accounts":{"m3-other":{"owner":"iam.mysql"}}}`), []byte(`{"accounts":{"m3-iam":{"unknown":"iam.mysql"}}}`)} {
		if DecodeNamed(raw, &object, "m3-iam") == nil {
			t.Fatal("duplicate, alias or unreviewed manifest shape accepted")
		}
	}
	if DecodeNamed([]byte(`{"accounts":{}}`), &object, "M3-iam") == nil {
		t.Fatal("invalid account-key extension accepted")
	}
}
