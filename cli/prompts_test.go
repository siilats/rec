package main

import (
	"slices"
	"strings"
	"testing"
)

func TestPromptsReachEngineAndInstanceIdentity(t *testing.T) {
	m := releaseManifest(t)
	for _, enabled := range []bool{false, true} {
		settings := serveSettings{prompts: enabled}
		_, args, _ := launchCommand(Paths{}, m, "/runtime", "/model/flint-int4.json", 11500, settings)
		if slices.Contains(args, "--prompts") != enabled {
			t.Fatalf("prompts=%v: %v", enabled, args)
		}
		s := Status{Ready: true, Model: m.Model, Revision: m.Revision, Runtime: m.RuntimeSHA, Context: m.Context, Instance: instanceKey(m), Endpoint: "http://127.0.0.1:11500/v1", Prompts: enabled}
		if !sameInstance(s, m, 11500, settings) || sameInstance(s, m, 11500, serveSettings{prompts: !enabled}) {
			t.Fatal("prompt preview setting must match when reusing a server")
		}
	}
}

func TestPromptsCLIFlagIsAccepted(t *testing.T) {
	t.Setenv("XDG_DATA_HOME", t.TempDir())
	t.Setenv("XDG_CACHE_HOME", t.TempDir())
	err := run([]string{"serve", "--prompts", "--manifest", "/nonexistent/prompts-test.json"})
	if err == nil || strings.Contains(err.Error(), "flag provided but not defined") || !strings.Contains(err.Error(), "prompts-test.json") {
		t.Fatalf("--prompts did not reach manifest loading: %v", err)
	}
}
