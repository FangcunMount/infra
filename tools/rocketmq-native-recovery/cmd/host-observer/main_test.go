package main

import (
	"github.com/FangcunMount/reliable-messaging/transport"
	"testing"
)

func TestCIOnlyObserverContract(t *testing.T) {
	c := config{Endpoint: "127.0.0.1:8081", AccessKey: "fixture", SecretKey: "fixture", CA: "private-ca", Subscription: "original", Inputs: []transport.RouteBinding{{Topic: "iam.authz.version.v2", Subscription: "original", Owner: "iam.mysql", RouteRevision: "m3-1", MessageType: transport.TransactionMessageType}}}
	env := map[string]string{"GITHUB_ACTIONS": "true", "RUNNER_OS": "Linux", "RUNNER_ENVIRONMENT": "github-hosted", "GITHUB_REPOSITORY": "FangcunMount/infra"}
	get := func(k string) string { return env[k] }
	if validate(c, get) != nil {
		t.Fatal("explicit isolated route refused")
	}
	for _, key := range []string{"GITHUB_ACTIONS", "RUNNER_OS", "RUNNER_ENVIRONMENT", "GITHUB_REPOSITORY"} {
		v := env[key]
		delete(env, key)
		if validate(c, get) == nil {
			t.Fatal("ordinary environment admitted")
		}
		env[key] = v
	}
	c.Endpoint = "public.example:8081"
	if validate(c, get) == nil {
		t.Fatal("external endpoint admitted")
	}
}
func TestObserverNeverStartsOnWorkstation(t *testing.T) {
	t.Setenv("GITHUB_ACTIONS", "")
	if run("/missing/private/config", "") == nil {
		t.Fatal("ordinary workstation admitted")
	}
}
