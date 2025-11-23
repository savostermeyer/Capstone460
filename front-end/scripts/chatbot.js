const chatButton = document.getElementById("chatbot-button");
const chatWindow = document.getElementById("chatbot-window");
const chatClose = document.getElementById("chatbot-close");
const chatMessages = document.getElementById("chatbot-messages");
const chatInput = document.getElementById("chatbot-input");
const chatSend = document.getElementById("chatbot-send");

// Session ID
let sid = localStorage.getItem("skinai_sid")
if(!sid) {
  sid = "sid_" + Math.random().toString(36).substring(2);
  localStorage.setItem("skinai_sid", sid);
}

//Restore chat open state
let chatOpenState = localStorage.getItem("skinai_chat_open") || "false";
if (chatOpenState === "true"){
  chatWindow.style.display = "flex";
}

// Backend  <-- MUST BE let, not const (so reset can update it)
let BACKEND_URL = `http://127.0.0.1:3720/chat?sid=${sid}`;

// Show chat history
let savedHistory = JSON.parse(localStorage.getItem("skinai_chat_history") || "[]");

function renderHistory(){
  chatMessages.innerHTML = "";
  savedHistory.forEach(msg =>{
    const div = document.createElement("div");
    div.className = `chatbot-msg ${msg.type}`;
    div.textContent = msg.text;  
    chatMessages.appendChild(div);
  });
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

renderHistory(); 

//if history is empty
if(savedHistory.length === 0){
  addMessage(
    "Hello! Im skinderella. You can upload images on the upload page or tell me your symptoms and I'll guid your analysis. " , 
    "bot"
  );
}

// UI open/close
chatButton.addEventListener("click", () => {
  chatWindow.style.display = "flex";
  localStorage.setItem("skinai_chat_open", "true");
  renderHistory(); // reload saved messages
});

chatClose.addEventListener("click", () => {
  chatWindow.style.display = "none";
  localStorage.setItem("skinai_chat_open", "false");
});

// Input handlers
chatSend.addEventListener("click", sendMessage);
chatInput.addEventListener("keypress", e => {
  if (e.key === "Enter") sendMessage();
});

function addMessage(text, type) {

  // Save to localStorage
  savedHistory.push({ text, type });
  localStorage.setItem("skinai_chat_history", JSON.stringify(savedHistory));

  // Add to UI
  const div = document.createElement("div");
  div.className = `chatbot-msg ${type}`;
  div.textContent = text;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Make addMessage available for upload.html
window.addMessage = addMessage;


// ------------------------------------
// RESET CHAT FUNCTION (new)
// ------------------------------------

// RESET button (↺)
const chatReset = document.getElementById("chatbot-reset");

chatReset.addEventListener("click", () => {
  // 1. Clear UI messages
  chatMessages.innerHTML = "";

  // 2. Clear saved history
  localStorage.removeItem("skinai_chat_history");
  savedHistory = []; // local copy also cleared

  // 3. Generate a NEW SID so AI conversation resets
  const newSid = "sid_" + Math.random().toString(36).substring(2);
  localStorage.setItem("skinai_sid", newSid);

  // 4. Update backend URL immediately
  BACKEND_URL = `http://127.0.0.1:3720/chat?sid=${newSid}`;

  // 5. Confirm to user
  const div = document.createElement("div");
  div.className = "chatbot-msg bot";
  div.textContent = "🔄 Chat reset. You can start a new conversation.";
  chatMessages.appendChild(div);
});


// ------------------------------------
// SEND MESSAGE TO BACKEND
// ------------------------------------

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
