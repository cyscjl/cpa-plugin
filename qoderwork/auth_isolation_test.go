package main

import (
	"encoding/json"
	"testing"

	"github.com/router-for-me/CLIProxyAPI/v7/sdk/pluginapi"
)

func decodeParse(t *testing.T, raw []byte) pluginapi.AuthParseResponse {
	t.Helper()
	var env envelope
	if err := json.Unmarshal(raw, &env); err != nil {
		t.Fatalf("envelope: %v", err)
	}
	if !env.OK {
		t.Fatalf("not ok: %+v", env.Error)
	}
	var resp pluginapi.AuthParseResponse
	if err := json.Unmarshal(env.Result, &resp); err != nil {
		t.Fatalf("result: %v", err)
	}
	return resp
}

// Issue #11: workbuddy type-less files must not be claimed by qoderwork.
func TestHandleParseAuth_RejectsWorkbuddyTypeless(t *testing.T) {
	req := pluginapi.AuthParseRequest{
		Provider: "",
		FileName: "workbuddy-00e26541.json",
		RawJSON: []byte(`{
			"auth":{"accessToken":"at","refreshToken":"rt","domain":"www.codebuddy.cn"},
			"account":{"uid":"00e26541"}
		}`),
	}
	body, _ := json.Marshal(req)
	out, err := handleParseAuth(body)
	if err != nil {
		t.Fatal(err)
	}
	if decodeParse(t, out).Handled {
		t.Fatal("must not claim workbuddy- filename / codebuddy domain")
	}
}

func TestHandleParseAuth_RejectsWorkbuddyType(t *testing.T) {
	req := pluginapi.AuthParseRequest{
		Provider: "",
		FileName: "x.json",
		RawJSON:  []byte(`{"type":"workbuddy","auth":{"accessToken":"at","domain":"www.codebuddy.cn"},"account":{"uid":"u"}}`),
	}
	body, _ := json.Marshal(req)
	out, err := handleParseAuth(body)
	if err != nil {
		t.Fatal(err)
	}
	if decodeParse(t, out).Handled {
		t.Fatal("must not claim type=workbuddy")
	}
}

func TestHandleParseAuth_AcceptsQoderworkPrefix(t *testing.T) {
	req := pluginapi.AuthParseRequest{
		Provider: "",
		FileName: "qoderwork-uid.json",
		RawJSON: []byte(`{
			"auth":{"accessToken":"jt-x","domain":"qoder.com.cn"},
			"account":{"uid":"uid"}
		}`),
	}
	body, _ := json.Marshal(req)
	out, err := handleParseAuth(body)
	if err != nil {
		t.Fatal(err)
	}
	if !decodeParse(t, out).Handled {
		t.Fatal("qoderwork- prefix + qoder domain should be claimed")
	}
}

func TestToAuthData_StorageJSONEmbedsType(t *testing.T) {
	sa := &storedAuth{
		Auth:    storedTokens{AccessToken: "jt-a", Domain: "qoder.com.cn"},
		Account: storedAccount{UID: "u1"},
	}
	ad := toAuthData(sa)
	var doc map[string]any
	if err := json.Unmarshal(ad.StorageJSON, &doc); err != nil {
		t.Fatal(err)
	}
	if doc["type"] != providerName {
		t.Fatalf("type=%v want %s", doc["type"], providerName)
	}
}
