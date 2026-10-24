package main

import (
	"bytes"
	"context"
	"strings"
	"testing"
)

func TestCLIRefusesEffectfulUnknownAndSensitiveArguments(t *testing.T) {
	for _, args := range [][]string{nil, {"check"}, {"resolve"}, {"native-resume"}, {"preview", "--database-uri", "DO_NOT_PRINT_SECRET"}, {"verify-review", "--secret", "DO_NOT_PRINT_SECRET"}, {"version", "extra"}, {"preview"}, {"verify-review"}} {
		var out, diagnostics bytes.Buffer
		if err := run(context.Background(), args, &out, &diagnostics); err == nil {
			t.Fatal("accepted incomplete/effectful command")
		}
		if strings.Contains(out.String()+diagnostics.String(), "DO_NOT_PRINT_SECRET") || out.Len() != 0 || diagnostics.Len() != 0 {
			t.Fatal("sensitive input echoed")
		}
	}
}
func TestCLIHelpAccuratelyExcludesSDKAndGovernanceEffects(t *testing.T) {
	var out bytes.Buffer
	if err := run(context.Background(), []string{"help"}, &out, &out); err != nil || !strings.Contains(out.String(), "Read-only") || !strings.Contains(out.String(), "no SDK") {
		t.Fatal("misleading CLI help", err)
	}
}
