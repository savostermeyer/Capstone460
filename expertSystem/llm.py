# expertSystem/llm.py
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DEFAULT_MODEL = "gpt-5.1-mini"   # fast+cheap; swap to a bigger model if needed

def chat(messages, **kwargs):
    """
    Thin wrapper around Chat Completions for now.
    """
    resp = client.chat.completions.create(
        model=kwargs.get("model", DEFAULT_MODEL),
        messages=messages,
        temperature=kwargs.get("temperature", 0.2),
        response_format=kwargs.get("response_format", {"type": "text"}),
    )
    return resp.choices[0].message
