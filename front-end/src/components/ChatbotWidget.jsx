import { useEffect, useMemo, useRef, useState } from "react";

const STORAGE_HISTORY = "skinai_chat_history";
const STORAGE_OPEN = "skinai_chat_open";
const STORAGE_SID = "skinai_sid";

function newSid() {
  return "sid_" + Math.random().toString(36).substring(2);
}

export default function ChatbotWidget({ title = "Talk to AI Agent" }) {
  // SID (persisted)
  const sid = useMemo(() => {
    try {
      let existing = localStorage.getItem(STORAGE_SID);
      if (!existing) {
        existing = newSid();
        localStorage.setItem(STORAGE_SID, existing);
      }
      return existing;
    } catch {
      return newSid();
    }
  }, []);

  // Backend URL (exactly like your original)
  const [backendUrl, setBackendUrl] = useState(
    `http://127.0.0.1:3720/chat?sid=${sid}`
  );

  // Open state (persisted)
  const [open, setOpen] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_OPEN) === "true";
    } catch {
      return false;
    }
  });

  // History (persisted)
  const [messages, setMessages] = useState(() => {
    try {
      const raw = localStorage.getItem(STORAGE_HISTORY);
      const parsed = raw ? JSON.parse(raw) : [];
      if (parsed.length === 0) {
        return [
          {
            type: "bot",
            text:
              "Hello! Im skinderella. You can upload images on the upload page or tell me your symptoms and I'll guid your analysis.",
          },
        ];
      }
      return parsed;
    } catch {
      return [
        {
          type: "bot",
          text:
            "Hello! Im skinderella. You can upload images on the upload page or tell me your symptoms and I'll guid your analysis.",
        },
      ];
    }
  });

  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const listRef = useRef(null);

  // Persist open state
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_OPEN, open ? "true" : "false");
    } catch {}
  }, [open]);

  // Persist history
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_HISTORY, JSON.stringify(messages));
    } catch {}
  }, [messages]);

  // Auto-scroll
  useEffect(() => {
    if (!open) return;
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, open]);

  function addMessage(text, type) {
    setMessages((prev) => [...prev, { text, type }]);
  }

  function resetChat() {
    try {
      localStorage.removeItem(STORAGE_HISTORY);
    } catch {}

    const freshSid = newSid();
    try {
      localStorage.setItem(STORAGE_SID, freshSid);
    } catch {}

    setBackendUrl(`http://127.0.0.1:3720/chat?sid=${freshSid}`);

    setMessages([
      { type: "bot", text: "🔄 Chat reset. You can start a new conversation." },
    ]);
    setInput("");
  }

  async function sendMessage() {
    const text = input.trim();
    if (!text || busy) return;

    addMessage(text, "user");
    setInput("");
    setBusy(true);

    const formData = new FormData();
    formData.append("text", text);

    try {
      const res = await fetch(backendUrl, {
        method: "POST",
        body: formData,
      });

      const data = await res.json();

      const reply =
        data.reply ||
        data.message ||
        data.text ||
        data.assistant ||
        "[No reply]";

      addMessage(String(reply), "bot");
    } catch (err) {
      console.error(err);
      addMessage("Error: Unable to connect to AI assistant.", "bot");
    } finally {
      setBusy(false);
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter") {
      e.preventDefault();
      sendMessage();
    }
  }

  return (
    <div id="chatbot-widget">
      <button
        id="chatbot-button"
        type="button"
        onClick={() => setOpen(true)}
        aria-expanded={open}
      >
        <span className="chat-icon">💬</span>
        <span className="chat-label">{title}</span>
      </button>

      {open && (
        <div id="chatbot-window" role="dialog" aria-label={title}>
          <div id="chatbot-header">
            <span>{title}</span>
            <div style={{ display: "flex", gap: 8 }}>
              <button id="chatbot-reset" type="button" onClick={resetChat}>
                ↺
              </button>
              <button
                id="chatbot-close"
                type="button"
                onClick={() => setOpen(false)}
              >
                ✕
              </button>
            </div>
          </div>

          <div id="chatbot-messages" ref={listRef}>
            {messages.map((m, i) => (
              <div key={i} className={`chatbot-msg ${m.type}`}>
                {m.text}
              </div>
            ))}
            {busy && <div className="chatbot-msg bot">Typing…</div>}
          </div>

          <div id="chatbot-input-area">
            <input
              id="chatbot-input"
              type="text"
              placeholder="Type your message…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              disabled={busy}
            />
            <button
              id="chatbot-send"
              type="button"
              onClick={sendMessage}
              disabled={busy || !input.trim()}
            >
              ➤
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
