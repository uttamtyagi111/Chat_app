
// ✅ Self-contained Chat Widget (Bubble + Modal + WebSocket) in one file

(function () {
  const CONFIG = {
    themeColor: "#10B981",
    logoUrl: "",
    position: "right",
    widgetId: "03d5490f-590e",
    apiUrl: "http://localhost:8000/chat/user-chat/",
    wsUrl: "ws://localhost:8000/ws/chat/",
    fileUploadUrl: "http://localhost:8000/chat/user-chat/upload-file/"
  };

  const widgetHTML = `
    <style>
      #chat-bubble {
        position: fixed;
        bottom: 20px;
        ${CONFIG.position}: 20px;
        background: ${CONFIG.themeColor};
        color: white;
        padding: 15px;
        border-radius: 50%;
        cursor: pointer;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
        font-size: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 1000;
      }
      #chat-window {
        display: none;
        position: fixed;
        bottom: 90px;
        ${CONFIG.position}: 20px;
        width: 300px;
        height: 400px;
        background: white;
        border: 1px solid #ccc;
        box-shadow: 0 4px 10px rgba(0,0,0,0.3);
        border-radius: 10px;
        z-index: 1000;
        flex-direction: column;
        font-family: Arial, sans-serif;
      }
      #chat-header {
        background: ${CONFIG.themeColor};
        color: white;
        padding: 10px;
        text-align: center;
        font-weight: bold;
        border-top-left-radius: 10px;
        border-top-right-radius: 10px;
      }
      #chat-messages {
        flex: 1;
        padding: 10px;
        overflow-y: auto;
      }
      #chat-footer {
        display: flex;
        padding: 10px;
        border-top: 1px solid #eee;
      }
      #chat-input {
        flex: 1;
        padding: 5px;
        border: 1px solid #ccc;
        border-radius: 5px;
      }
      #send-btn {
        margin-left: 5px;
        padding: 5px 10px;
        background: ${CONFIG.themeColor};
        color: white;
        border: none;
        border-radius: 5px;
        cursor: pointer;
      }
    </style>
    <div id="chat-bubble">💬</div>
    <div id="chat-window">
      <div id="chat-header">Chat with us</div>
      <div id="chat-messages"></div>
      <div id="chat-footer">
        <input type="text" id="chat-input" placeholder="Type a message..." />
        <button id="send-btn">Send</button>
      </div>
    </div>
  `;

  const container = document.createElement("div");
  container.innerHTML = widgetHTML;
  document.body.appendChild(container);

  const chatBubble = document.getElementById("chat-bubble");
  const chatWindow = document.getElementById("chat-window");
  const chatInput = document.getElementById("chat-input");
  const chatMessages = document.getElementById("chat-messages");
  const sendBtn = document.getElementById("send-btn");

  let socket;
  let roomId = localStorage.getItem("chat_room_id");

  chatBubble.addEventListener("click", () => {
    chatWindow.style.display = "flex";
    if (!socket) initializeChat();
  });

  sendBtn.addEventListener("click", sendMessage);
  chatInput.addEventListener("keypress", (e) => {
    if (e.key === "Enter") sendMessage();
  });

  function sendMessage() {
    const text = chatInput.value.trim();
    if (!text || !socket) return;
    const msg = {
      sender: "User",
      message: text
    };
    socket.send(JSON.stringify(msg));
    appendMessage("You", text);
    chatInput.value = "";
  }

  function appendMessage(sender, text) {
    const msgDiv = document.createElement("div");
    msgDiv.textContent = `${sender}: ${text}`;
    msgDiv.style.marginBottom = "8px";
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function initializeChat() {
    if (roomId) {
      connectWebSocket(roomId);
    } else {
      fetch(CONFIG.apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ widget_id: CONFIG.widgetId, ip: "127.0.0.1" })
      })
      .then(res => res.json())
      .then(data => {
        roomId = data.room_id;
        localStorage.setItem("chat_room_id", roomId);
        connectWebSocket(roomId);
      })
      .catch(err => console.error("Room creation failed:", err));
    }
  }

  function connectWebSocket(roomId) {
    socket = new WebSocket(CONFIG.wsUrl + roomId + "/");

    socket.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.message) appendMessage("Agent", data.message);
    };

    socket.onopen = () => console.log("WebSocket connected.");
    socket.onclose = () => console.log("WebSocket disconnected.");
    socket.onerror = (err) => console.error("WebSocket error:", err);
  }
})();
