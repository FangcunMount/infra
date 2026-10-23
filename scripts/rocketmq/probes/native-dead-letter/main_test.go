package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/FangcunMount/reliable-messaging/transport"
)

func fixtureConfig(t *testing.T) config {
	t.Helper()
	topic, err := transport.PhysicalTopicV2("infra.native.audit", transport.NormalMessageType, "qs.mysql", "m3-1")
	if err != nil {
		t.Fatal(err)
	}
	group, err := transport.ConsumerGroupV2("infra.native.audit", "audit-only")
	if err != nil {
		t.Fatal(err)
	}
	return config{Project: "rocketmq-m2-owned-fixture", Endpoint: "127.0.0.1:12345", CAFile: "/private/fixture-ca.pem",
		AccessKey: "fixture", SecretKey: "fixture", Key: "audit-fixture",
		Route: transport.RouteBinding{Topic: "infra.native.audit", Subscription: "audit-only", PhysicalTopic: topic,
			ConsumerGroup: group, MessageType: transport.NormalMessageType, Owner: "qs.mysql", RouteRevision: "m3-1"}}
}

func writeConfig(t *testing.T, c config, mode os.FileMode) string {
	t.Helper()
	raw, err := json.Marshal(c)
	if err != nil {
		t.Fatal(err)
	}
	p := filepath.Join(t.TempDir(), "private.json")
	if err = os.WriteFile(p, raw, mode); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestFixtureConfigurationRequiresLoopbackOwnedNormalRouteAndPrivateFile(t *testing.T) {
	c := fixtureConfig(t)
	if _, err := readConfig(writeConfig(t, c, 0600)); err != nil {
		t.Fatal(err)
	}
	for name, mutate := range map[string]func(*config){
		"remote":          func(c *config) { c.Endpoint = "192.0.2.1:8081" },
		"zero_port":       func(c *config) { c.Endpoint = "127.0.0.1:0" },
		"invalid_port":    func(c *config) { c.Endpoint = "127.0.0.1:service" },
		"out_of_range":    func(c *config) { c.Endpoint = "127.0.0.1:65536" },
		"unowned_project": func(c *config) { c.Project = "production" },
		"wrong_type":      func(c *config) { c.Route.MessageType = transport.TransactionMessageType },
		"wrong_revision":  func(c *config) { c.Route.RouteRevision = "other" },
		"wrong_group":     func(c *config) { c.Route.ConsumerGroup = "rmq2_g_unreviewed" },
		"no_subscription": func(c *config) { c.Route.Subscription = "" },
		"relative_CA":     func(c *config) { c.CAFile = "relative.pem" },
	} {
		t.Run(name, func(t *testing.T) {
			bad := c
			mutate(&bad)
			if _, err := readConfig(writeConfig(t, bad, 0600)); err == nil {
				t.Fatal("unsafe fixture accepted")
			}
		})
	}
	if _, err := readConfig(writeConfig(t, c, 0644)); err == nil {
		t.Fatal("readable configuration accepted")
	}
	if _, err := readConfig("relative.json"); err == nil {
		t.Fatal("relative configuration accepted")
	}
}

func TestFixtureConfigurationRejectsExtraDocumentsAndUnknownFields(t *testing.T) {
	for name, suffix := range map[string]string{"second_document": "\n{}", "unknown_field": ",\"Unexpected\":true}"} {
		t.Run(name, func(t *testing.T) {
			c := fixtureConfig(t)
			raw, err := json.Marshal(c)
			if err != nil {
				t.Fatal(err)
			}
			if name == "unknown_field" {
				raw = raw[:len(raw)-1]
			}
			p := filepath.Join(t.TempDir(), "private.json")
			if err = os.WriteFile(p, append(raw, []byte(suffix)...), 0600); err != nil {
				t.Fatal(err)
			}
			if _, err = readConfig(p); err == nil {
				t.Fatal("unbounded fixture document accepted")
			}
		})
	}
}
