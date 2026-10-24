// Pure source contract export. No database, broker, user data or network.
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"regexp"

	catalog "github.com/FangcunMount/qs-server/internal/pkg/eventing/catalog"
	"github.com/FangcunMount/qs-server/pkg/version"
)

type consumerContract struct {
	ID            string                `json:"id"`
	Runtime       string                `json:"runtime"`
	EventType     string                `json:"event_type"`
	Topic         string                `json:"topic"`
	Channel       string                `json:"channel"`
	Delivery      catalog.DeliveryClass `json:"delivery"`
	OutboxProfile catalog.OutboxProfile `json:"outbox_profile"`
}

func main() {
	if !regexp.MustCompile(`^[a-f0-9]{40}$`).MatchString(version.GitCommit) {
		os.Exit(1)
	}
	wire, err := catalog.Load("configs/events.yaml")
	if err != nil {
		os.Exit(1)
	}
	registry, err := catalog.NewEffectiveRegistry(catalog.NewCatalog(wire), catalog.DefaultSpecs())
	if err != nil {
		os.Exit(1)
	}
	rows := []consumerContract{}
	for _, event := range registry.Snapshot() {
		for _, consumer := range event.AdditionalConsumers {
			rows = append(rows, consumerContract{consumer.ID, consumer.Runtime, event.Type, event.Topic, consumer.Channel, event.Delivery, event.OutboxProfile})
		}
	}
	if len(rows) == 0 {
		os.Exit(1)
	}
	raw, err := json.Marshal(map[string]any{"schema": "qs-original-consumer-contract/v1", "source_sha": version.GitCommit, "consumers": rows})
	if err != nil {
		os.Exit(1)
	}
	fmt.Println("QS_CONSUMER_CONTRACT " + string(raw))
}
