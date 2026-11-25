"""Manual local-model diagnostic: run explicitly with python manual_ollama_probe.py."""

from ollama import Client


def main():
    client = Client(host="http://127.0.0.1:11434", timeout=60)
    response = client.chat(
        model="qwen3:1.7b",
        messages=[{"role": "user", "content": "What is a 3D printer? Answer in two sentences."}],
        think=False,
    )
    print(response.message.content)


if __name__ == "__main__":
    main()
