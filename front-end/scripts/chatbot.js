const chatButton = document.getElementById("chatbot-button");
const chatWindow = document.getElementById("chatbot-window");
const chatClose = document.getElementById("chatbot-close");
const chatMessages = document.getElementById("chatbot-messages");
const chatInput = document.getElementById("chatbot-input");
const chatSend = document.getElementById("chatbot-send");

chatButton.addEventListener("click", () => {
  chatWindow.style.display = "flex";
});

chatClose.addEventListener("click", () => {
  chatWindow.style.display = "none";
});

chatSend.addEventListener("click", sendMessage);
chatInput.addEventListener("keypress", e => {
  if (e.key === "Enter") sendMessage();
});

function sendMessage() {
  const text = chatInput.value.trim();
  if (!text) return;

  addMessage(text, "user");
  chatInput.value = "";

  setTimeout(() => {
    addMessage("Thank you for your message! The AI assistant demo is not connected yet, but you can integrate your Flask/Gemini backend here.", "bot");
  }, 600);
}

function addMessage(text, type) {
  const div = document.createElement("div");
  div.className = `chatbot-msg ${type}`;
  div.textContent = text;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}
