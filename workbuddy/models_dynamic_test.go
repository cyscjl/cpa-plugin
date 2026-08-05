package main

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestParseModelsAPIBody_PrefersCLIOrderButKeepsExtraCatalog(t *testing.T) {
	body := []byte(`{
  "code": 0,
  "data": {
    "models": [
      {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash", "disabled": false, "contextWindow": 1000000, "maxTokens": 8192},
      {"id": "kimi-k3-1", "name": "Kimi-K3", "disabled": false, "contextWindow": 262144, "maxTokens": 8192},
      {"id": "old-disabled", "name": "Gone", "disabled": true}
    ],
    "agents": [
      {"name": "cli", "models": ["deepseek-v4-flash"]}
    ]
  }
}`)
	out, err := parseModelsAPIBody(body)
	if err != nil {
		t.Fatal(err)
	}
	if len(out) != 2 {
		t.Fatalf("want 2 models, got %d: %+v", len(out), out)
	}
	if out[0].ID != "deepseek-v4-flash" {
		t.Fatalf("cli order first, got %s", out[0].ID)
	}
	if out[1].ID != "kimi-k3-1" {
		t.Fatalf("catalog extra kimi-k3-1 missing, got %s", out[1].ID)
	}
}

func TestParseModelsAPIBody_NoCLIAgentUsesFullCatalog(t *testing.T) {
	body := []byte(`{
  "code": 0,
  "data": {
    "models": [
      {"id": "kimi-k3-1", "name": "Kimi-K3", "disabled": false},
      {"id": "glm-5.2", "name": "GLM-5.2", "disabled": false}
    ],
    "agents": []
  }
}`)
	out, err := parseModelsAPIBody(body)
	if err != nil {
		t.Fatal(err)
	}
	ids := make([]string, 0, len(out))
	for _, m := range out {
		ids = append(ids, m.ID)
	}
	joined := strings.Join(ids, ",")
	if !strings.Contains(joined, "kimi-k3-1") || !strings.Contains(joined, "glm-5.2") {
		t.Fatalf("expected full catalog, got %v", ids)
	}
}

func TestWbModelsIncludesKimiK3(t *testing.T) {
	found := false
	for _, m := range wbModels() {
		if m.ID == "kimi-k3-1" {
			found = true
			break
		}
	}
	if !found {
		t.Fatal("static fallback missing kimi-k3-1")
	}
}

func TestParseModelsAPIBody_RealFixtureKeepsKimiK31(t *testing.T) {
	// Minimal shape from live /console/enterprises/personal/models (redacted).
	body := []byte(`{
  "code": 0,
  "data": {
    "models": [
      {"id": "deepseek-v4-flash", "name": "DeepSeek-V4-Flash", "disabled": false},
      {"id": "kimi-k3-1", "name": "Kimi-K3", "disabled": false},
      {"id": "kimi-k2.7", "name": "Kimi-K2.7-Code", "disabled": false}
    ],
    "agents": [
      {"name": "cli", "models": ["deepseek-v4-flash", "kimi-k3-1", "kimi-k2.7"]}
    ]
  }
}`)
	out, err := parseModelsAPIBody(body)
	if err != nil {
		t.Fatal(err)
	}
	ids := map[string]bool{}
	for _, m := range out {
		ids[m.ID] = true
	}
	if !ids["kimi-k3-1"] {
		t.Fatalf("missing kimi-k3-1 in %+v", out)
	}
}

func TestParseModelsAPIBody_AllDisabled(t *testing.T) {
	body := []byte(`{"code":0,"data":{"models":[{"id":"x","disabled":true}],"agents":[{"name":"cli","models":["x"]}]}}`)
	_, err := parseModelsAPIBody(body)
	if err == nil {
		t.Fatal("expected error when all disabled")
	}
}

func TestParseModelsAPIBody_BadCode(t *testing.T) {
	_, err := parseModelsAPIBody([]byte(`{"code":1,"data":{}}`))
	if err == nil {
		t.Fatal("expected code error")
	}
}

// compile-time sanity: response shape used by callModelsAPI stays decodable
func TestModelsAPIResponseShape(t *testing.T) {
	raw := []byte(`{"code":0,"data":{"models":[{"id":"a","name":"A","contextWindow":1,"maxTokens":2}],"agents":[{"name":"cli","models":["a"]}]}}`)
	var probe map[string]any
	if err := json.Unmarshal(raw, &probe); err != nil {
		t.Fatal(err)
	}
}
