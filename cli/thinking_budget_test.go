package main

import (
	"slices"
	"strconv"
	"testing"
)

func TestThinkingBudgetReachesEngineAndInstanceIdentity(t *testing.T) {
	m := releaseManifest(t)
	for _, budget := range []int{0, 512} {
		_, args, _ := launchCommand(Paths{}, m, "/runtime", "/model/flint-int4.json", 11500, serveSettings{thinkingBudget: &budget})
		i := slices.Index(args, "--thinking-budget")
		if i < 0 || i+1 >= len(args) || args[i+1] != strconv.Itoa(budget) {
			t.Fatal("thinking budget did not reach engine", args)
		}
		s := Status{Ready: true, Model: m.Model, Revision: m.Revision, Runtime: m.RuntimeSHA, Context: m.Context, Instance: instanceKey(m), Endpoint: "http://127.0.0.1:11500/v1", ThinkingBudget: &budget}
		if !sameInstance(s, m, 11500, serveSettings{thinkingBudget: &budget}) {
			t.Fatal("matching budget rejected")
		}
		if sameInstance(s, m, 11500) {
			t.Fatal("budgeted server reused for unlimited request")
		}
		different := budget + 1
		if sameInstance(s, m, 11500, serveSettings{thinkingBudget: &different}) {
			t.Fatal("different budget reused")
		}
	}
	_, args, _ := launchCommand(Paths{}, m, "/runtime", "/model/flint-int4.json", 11500)
	if slices.Contains(args, "--thinking-budget") {
		t.Fatal("omitted budget changed default")
	}
}

func TestThinkingBudgetRejectsInvalidCLIValues(t *testing.T) {
	t.Setenv("XDG_DATA_HOME", t.TempDir())
	t.Setenv("XDG_CACHE_HOME", t.TempDir())
	for _, value := range []string{"-1", "1.5", "abc"} {
		if err := run([]string{"serve", "--thinking-budget", value}); err == nil {
			t.Fatalf("accepted invalid thinking budget %q", value)
		}
	}
}
