class AssistantProvider {
  id() {
    return "local-assistant-api";
  }

  async callApi(prompt) {
    const base = process.env.ASSISTANT_TEST_URL || "http://127.0.0.1:8000";
    const key = process.env.ASSISTANT_SECURITY_TEST_KEY;
    if (!key) {
      return { error: "ASSISTANT_SECURITY_TEST_KEY is required; no test was sent." };
    }
    const response = await fetch(`${base}/api/v1/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Assistant-Key": key,
      },
      body: JSON.stringify({ message: prompt }),
    });
    const payload = await response.json();
    if (!response.ok) {
      return { error: `HTTP ${response.status}: ${payload.detail || "request failed"}` };
    }
    return { output: payload.message };
  }
}

module.exports = AssistantProvider;
