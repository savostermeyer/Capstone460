import { useEffect, useMemo, useRef, useState } from "react";

const STORAGE_HISTORY = "skinai_chat_history";
const STORAGE_OPEN = "skinai_chat_open";
const STORAGE_SID = "skinai_sid";
console.log("🔥 ChatbotWidget loaded from:", import.meta.url);

function newSid() {
  return "sid_" + Math.random().toString(36).substring(2);
}

if (!window.__skinaiChatLock) {
  window.__skinaiChatLock = false;
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

  // Backend API base URL from environment, fallback to localhost:3720
  const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://localhost:3720").replace(/\/$/, "");
  const [backendUrl, setBackendUrl] = useState(`${API_BASE}/chat?sid=${sid}`);

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
            text: "Hello! Im skinderella. You can upload images on the upload page or tell me your symptoms and I'll guid your analysis.",
          },
        ];
      }
      return parsed;
    } catch {
      return [
        {
          type: "bot",
          text: "Hello! Im skinderella. You can upload images on the upload page or tell me your symptoms and I'll guid your analysis.",
        },
      ];
    }
  });

  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [imageFile, setImageFile] = useState(null);
  const listRef = useRef(null);
  const fileInputRef = useRef(null);

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

  // ⚡ BULLETPROOF listener: survives StrictMode double-invoke by attaching directly to window at module level
  // (keeps reference even if component remounts)
  if (!window.__skinaiListenersAttached) {
    console.log("🔧 [ChatbotWidget] Attaching global window listeners (one-time)");
    window.__skinaiListenersAttached = true;

    // Direct reference to trigger message addition
    window.__skinaiAddMessage = (text) => {
      if (!text || typeof text !== "string" || !text.trim()) {
        console.warn(
          "[ChatbotWidget] Received invalid message text:",
          typeof text,
          text
        );
        return false;
      }
      // Trigger via custom event that React component listens for
      const evt = new CustomEvent("__skinai:addMessageInternal", {
        detail: { text, timestamp: Date.now() },
      });
      window.dispatchEvent(evt);
      console.debug("[ChatbotWidget] Queued internal add for:", text.substring(0, 50));
      return true;
    };

    window.addEventListener("skinai:assistantMessage", (e) => {
      try {
        console.log("[EVENT] skinai:assistantMessage received:", {
          detailType: typeof e.detail,
          detailLength: e.detail?.length ?? "N/A",
        });

        const text =
          typeof e.detail === "string"
            ? e.detail
            : e.detail?.text || e.detail?.message || e.detail?.reply
            ? e.detail.text || e.detail.message || e.detail.reply
            : JSON.stringify(e.detail);

        if (!text || !String(text).trim()) {
          console.warn("[EVENT] skinai:assistantMessage text was empty, ignoring");
          return;
        }

        console.log(
          "[EVENT] skinai:assistantMessage → calling __skinaiAddMessage"
        );
        window.__skinaiAddMessage(String(text));
        window.dispatchEvent(new CustomEvent("skinai:open"));
      } catch (err) {
        console.error("[EVENT] skinai:assistantMessage handler error:", err);
      }
    });

    window.addEventListener("skinai:open", () => {
      console.log("[EVENT] skinai:open received");
      const evt = new CustomEvent("__skinai:openInternal");
      window.dispatchEvent(evt);
    });
  }

  // Component listens for the internal queued messages
  useEffect(() => {
    function onAddMessageInternal(e) {
      const { text } = e.detail || {};
      if (text) {
        console.debug(
          "[ChatbotWidget] onAddMessageInternal adding message:",
          text
        );
        setMessages((prev) => [...prev, { type: "bot", text }]);
      }
    }

    function onOpenInternal() {
      console.debug("[ChatbotWidget] onOpenInternal setting open=true");
      setOpen(true);
    }

    window.addEventListener("__skinai:addMessageInternal", onAddMessageInternal);
    window.addEventListener("__skinai:openInternal", onOpenInternal);

    return () => {
      window.removeEventListener(
        "__skinai:addMessageInternal",
        onAddMessageInternal
      );
      window.removeEventListener("__skinai:openInternal", onOpenInternal);
    };
  }, []);

  function addMessage(text, type) {
    setMessages((prev) => [...prev, { text, type }]);
  }

  function resetChat() {
    try {
      localStorage.removeItem(STORAGE_HISTORY);
    } catch {}

    const oldSid = sid;
    const freshSid = newSid();
    try {
      localStorage.setItem(STORAGE_SID, freshSid);
    } catch {}

    setBackendUrl(`${API_BASE}/chat?sid=${freshSid}`);

    // Also notify backend to clear the old session (helps with rate limits)
    if (oldSid) {
      fetch(`${API_BASE}/chat/reset?sid=${encodeURIComponent(oldSid)}`, {
        method: "POST",
      }).catch((e) => console.warn("Could not reset backend session:", e));
    }

    setMessages([
      { type: "bot", text: "🔄 Chat reset. You can start a new conversation." },
    ]);
    setInput("");
  }

  async function sendMessage() {
    const text = input.trim();
    const hasImage = Boolean(imageFile);

    // HARD guard (prevents double fire)
    if ((!text && !hasImage) || busy || window.__skinaiChatLock) return;

    window.__skinaiChatLock = true;

    if (text) {
      addMessage(text, "user");
    } else if (hasImage) {
      addMessage("[Image attached]", "user");
    }
    setInput("");
    setImageFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    setBusy(true);

    const formData = new FormData();
    formData.append("text", text);
    formData.append("page", "chat");
    if (hasImage) formData.append("image", imageFile);

    // Exponential backoff retry for rate-limit errors
    const maxRetries = 3;
    let attempt = 0;
    let lastError = null;

    while (attempt < maxRetries) {
      try {
        const res = await fetch(backendUrl, {
          method: "POST",
          body: formData,
        });

        const data = await res.json();

        // Check if backend returned a rate-limit error
        if (data.error_code === "RATE_LIMIT" || (data.error && data.error.includes("429"))) {
          lastError = data;
          attempt++;
          if (attempt < maxRetries) {
            // Longer exponential backoff: 2s, 4s, 8s (give API more time to recover)
            const waitMs = Math.pow(2, attempt) * 1000;
            console.warn(
              `Rate limit detected. Retrying in ${waitMs / 1000}s (attempt ${attempt}/${maxRetries})`
            );
            await new Promise((resolve) => setTimeout(resolve, waitMs));
            continue;
          }
        }

        const display = data.display || {};
        const message =
          display.message ||
          data.reply ||
          data.message ||
          data.text ||
          data.assistant ||
          "[No reply]";
        const followUp = display.follow_up_question || data.follow_up_question || "None";

        const botText =
          followUp && followUp !== "None"
            ? `${String(message)}\n\nFollow-up: ${String(followUp)}`
            : String(message);

        addMessage(botText, "bot");
        // Success, exit retry loop
        attempt = maxRetries;
      } catch (err) {
        lastError = err;
        attempt++;
        if (attempt < maxRetries) {
          const waitMs = Math.pow(2, attempt) * 1000;
          console.warn(
            `Request failed. Retrying in ${waitMs / 1000}s (attempt ${attempt}/${maxRetries}):`,
            err
          );
          await new Promise((resolve) => setTimeout(resolve, waitMs));
          continue;
        }
      }
    }

    // Final error handling if all retries exhausted
    if (attempt >= maxRetries && lastError) {
      console.error("Max retries exceeded:", lastError);
      addMessage(
        "The assistant is temporarily unavailable. Please try again in a few moments or reset the conversation.",
        "bot",
      );
    }

    // Always clean up: release lock and clear busy state
    setBusy(false);
    window.__skinaiChatLock = false;
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !busy && !window.__skinaiChatLock) {
      if (!input.trim() && !imageFile) return;
      e.preventDefault();
      sendMessage();
    }
  }

  function onPickImage(e) {
    const file = e.target.files?.[0] || null;
    if (file && !file.type.startsWith("image/")) {
      setImageFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }
    setImageFile(file);
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
            <button
              id="chatbot-attach"
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={busy}
              aria-label="Attach image"
              title="Attach image"
            >
              <svg
                className="chatbot-attach-icon"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  d="M7.5 12.5 16 4a3.5 3.5 0 0 1 5 5L11 19a5 5 0 1 1-7.1-7.1l9.4-9.4"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
            <input
              id="chatbot-file"
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={onPickImage}
              hidden
            />
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
              disabled={busy || (!input.trim() && !imageFile)}
            >
              ➤
            </button>
          </div>
          {imageFile && (
            <div id="chatbot-attachment-row">
              <span id="chatbot-attachment-name">{imageFile.name}</span>
              <button
                id="chatbot-attachment-remove"
                type="button"
                onClick={() => {
                  setImageFile(null);
                  if (fileInputRef.current) fileInputRef.current.value = "";
                }}
              >
                ✕
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
