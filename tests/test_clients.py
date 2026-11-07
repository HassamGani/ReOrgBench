from reorgbench.harness.clients import OpenAIClient, _infra_status, make_client


class _E(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.status_code = code


def test_billing_and_auth_errors_are_infrastructure():
    assert _infra_status(_E(400, "Your credit balance is too low to access the Anthropic API."))
    assert _infra_status(_E(429, "insufficient_quota"))
    assert _infra_status(_E(401, "invalid x-api-key"))
    assert not _infra_status(_E(400, "messages: field required"))


def test_openai_specs_get_an_openai_client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    assert isinstance(make_client("openai:some-model"), OpenAIClient)
