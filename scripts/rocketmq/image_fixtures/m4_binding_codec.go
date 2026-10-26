// Copied to the reviewed QS checkout for a pure, no-network codec contract.
// Never installed in a runtime image or production host.
package main

import (
	"encoding/json"
	"fmt"
	"os"

	binding "github.com/FangcunMount/qs-server/internal/apiserver/maintenance/aimessagingbinding"
	"github.com/FangcunMount/qs-server/pkg/version"
)

func check(stage string, err error) {
	if err != nil {
		fmt.Println("M4_CODEC_FAILURE " + stage)
		os.Exit(1)
	}
}

func main() {
	if len(os.Args) != 3 {
		fmt.Println("M4_CODEC_FAILURE arguments")
		os.Exit(1)
	}
	raw, err := os.ReadFile(os.Args[1])
	check("read_binding", err)
	b, err := binding.Decode(raw)
	check("actual_decode", err)
	check("actual_final_binding", binding.ValidateFinalBinding(b))
	base, err := os.ReadFile(os.Args[2])
	check("read_base", err)
	_, err = binding.RenderFinal(base, b)
	check("actual_final_render", err)
	check("report", json.NewEncoder(os.Stdout).Encode(map[string]any{
		"schema": "m4-actual-go-binding-codec/v1", "source_sha": version.GitCommit,
		"passed": 3, "failed": 0, "skipped": 0, "network": false,
		"case_ids": []string{"actual_decode", "actual_final_binding", "actual_final_render"},
	}))
}
