const chatButton = document.getElementById("chatbot-button");
const chatWindow = document.getElementById("chatbot-window");
const chatClose = document.getElementById("chatbot-close");
const chatMessages = document.getElementById("chatbot-messages");
const chatInput = document.getElementById("chatbot-input");
const chatSend = document.getElementById("chatbot-send");

// Backend
const BACKEND_URL = "http://127.0.0.1:3720/chat?sid=demo";

// UI open/close
chatButton.addEventListener("click", () => {
  chatWindow.style.display = "flex";
});

chatClose.addEventListener("click", () => {
  chatWindow.style.display = "none";
});

// Input handlers
chatSend.addEventListener("click", sendMessage);
chatInput.addEventListener("keypress", e => {
  if (e.key === "Enter") sendMessage();
});

function addMessage(text, type) {
  const div = document.createElement("div");
  div.className = `chatbot-msg ${type}`;
  div.textContent = text;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function sendMessage() {
  const text = chatInput.value.trim();
  if (!text) return;

  // Show user bubble
  addMessage(text, "user");
  chatInput.value = "";

  // Build request
  const formData = new FormData();
  formData.append("text", text);

  try {
    const res = await fetch(BACKEND_URL, {
      method: "POST",
      body: formData
    });

    const data = await res.json();
    console.log("AI Response:", data);

    const reply =
      data.reply ||
      data.message ||
      data.text ||
      data.assistant ||
      "[No reply]";

    addMessage(reply, "bot");

  } catch (err) {
    console.error(err);
    addMessage("Error: Unable to connect to AI assistant.", "bot");
  }
}
