from ollama import Client

# Connect to Ollama running locally.
client = Client(
    host="http://127.0.0.1:11434",
    timeout=60,
)

# Send a question to the local AI model.
response = client.chat(
    model="qwen3:1.7b",
    messages=[
        {
            "role": "user",
            "content": "What is a 3D printer? Answer in two sentences.",
        }
    ],
    think=False,
)

# Display the generated answer.
print(response.message.content)