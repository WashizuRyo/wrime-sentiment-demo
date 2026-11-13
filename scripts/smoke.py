"""Real-model HTTP smoke test; requires backend.local on loopback port 8000."""
import json
import urllib.error
import urllib.request


def request(method, text):
    req = urllib.request.Request(f"http://127.0.0.1:8000/predict/{method}",
                                 data=json.dumps({"text": text}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


def main():
    records = []
    for method in ("lora", "full"):
        for text, truncated in (("今日はとても楽しかった！", False), ("最悪な一日だった。", False), ("明日は月曜日です。", False), ("今日は楽しかった。" * 600, True)):
            result = request(method, text)
            assert result["model"] == method
            assert -2 <= result["sentiment"] <= 2
            assert set(result["probabilities"]) == {"-2", "-1", "0", "1", "2"}
            assert abs(sum(result["probabilities"].values()) - 1) < 1e-5
            assert str(result["sentiment"]) == max(result["probabilities"], key=result["probabilities"].get)
            assert result["truncated"] == truncated
            records.append({"model": method, "input_chars": len(text), "sentiment": result["sentiment"],
                            "truncated": result["truncated"], "elapsed_ms": result["elapsed_ms"]})
    try:
        request("lora", "")
    except urllib.error.HTTPError as error:
        assert error.code == 400
    else:
        raise AssertionError("Empty text was accepted")
    print(json.dumps(records, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
