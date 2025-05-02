(function () {
  // Widget configuration
  const isLocal =
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1";
  const WIDGET_CONFIG = {
    apiUrl: isLocal
      ? "http://localhost:8000/chat/user-chat/"
      : "http://208.87.134.149:8003/chat/user-chat/",
    wsUrl: isLocal
      ? "ws://localhost:8000/ws/chat/"
      : "ws://208.87.134.149:8003/ws/chat/",
    fileUploadUrl: isLocal
      ? "http://localhost:8000/chat/user-chat/upload-file/"
      : "http://208.87.134.149:8003/chat/user-chat/upload-file/",
    themeColor:
      document.currentScript.getAttribute("data-theme-color") || "#4a90e2",
    logoUrl:
      "https://emailbulkshoot.s3.ap-southeast-2.amazonaws.com/assests+for+Email+Automation/Techserve%404x.png",
  };

  // Check for existing room_id in local storage
  let roomId = localStorage.getItem("chat_room_id");
  let socket;
  const sentMessages = {};

  // Inject widget HTML
  const widgetContainer = document.createElement("div");
  widgetContainer.id = "chat-widget";
  widgetContainer.innerHTML = `
      <style>
        #chat-widget * {
          box-sizing: border-box;
        }
        #chat-bubble {
          position: fixed;
          bottom: 20px;
          right: 20px;
          background: ${WIDGET_CONFIG.themeColor};
          color: white;
          padding: 15px;
          border-radius: 50%;
          cursor: pointer;
          box-shadow: 0 2px 5px rgba(0,0,0,0.2);
          font-size: 24px;
          z-index: 1000;
        }
        #chat-window {
          display: none;
          position: fixed;
          bottom: 80px;
          right: 20px;
          width: 350px;
          height: 450px;
          background: white;
          border-radius: 12px;
          box-shadow: 0 4px 10px rgba(0,0,0,0.3);
          overflow: hidden;
          z-index: 1000;
          font-family: Arial, sans-serif;
        }
        #chat-header {
          background: ${WIDGET_CONFIG.themeColor};
          color: white;
          padding: 12px;
          font-weight: bold;
          font-size: 16px;
          text-align: center;
        }
        #chat-messages {
          position: relative;
          height: 340px;
          overflow-y: auto;
          padding: 15px;
          background: rgba(255, 255, 255, 0.3);
          display: flex;
          flex-direction: column;
        }
        #chat-messages-logo {
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          width: 50%;
          opacity: 0.4;
          z-index: -1;
          pointer-events: none;
        }
        .message {
          margin: 5px 0;
          max-width: 70%;
          padding: 10px 14px;
          border-radius: 12px;
          font-size: 14px;
          font-weight: 500;
          position: relative;
        }
        .user {
          background: #D0E6FF;
          align-self: flex-end;
          text-align: right;
        }
        .agent {
          background: #E2FFE2;
          align-self: flex-start;
          text-align: left;
        }
        .system {
          text-align: center;
          color: gray;
          font-style: italic;
          width: 100%;
        }
        .timestamp {
          display: block;
          font-size: 10px;
          color: #999;
          margin-top: 4px;
        }
        .tick {
          font-size: 12px;
          margin-left: 5px;
        }
        .tick.blue {
          color: #2196F3;
        }
        .file-preview img {
          max-width: 100%;
          border-radius: 8px;
          margin-top: 5px;
        }
        .file-preview a {
          color: #2196F3;
          text-decoration: none;
        }
        #chat-form {
          display: none;
          padding: 15px;
          background: #f7f7f7;
          border-radius: 8px;
          box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
          margin: 5px 10px;
          max-width: 300px;
          align-self: flex-end;
          text-align: right;
        }
        .form-group {
          margin-bottom: 8px;
        }
        .form-group label {
          display: block;
          font-weight: 500;
          margin-bottom: 3px;
          color: #333;
          font-size: 12px;
          text-align: left;
        }
        .form-group input {
          width: 100%;
          padding: 6px 8px;
          border: 1px solid #ddd;
          border-radius: 4px;
          font-size: 12px;
        }
        .form-group input:focus {
          border-color: ${WIDGET_CONFIG.themeColor};
          outline: none;
          box-shadow: 0 0 0 2px rgba(74, 144, 226, 0.2);
        }
        .submit-btn {
          background: ${WIDGET_CONFIG.themeColor};
          color: white;
          border: none;
          border-radius: 4px;
          padding: 6px 12px;
          font-size: 12px;
          cursor: pointer;
          float: right;
        }
        .submit-btn:hover {
          background: #3a80d2;
        }
        #chat-footer {
          display: flex;
          align-items: center;
          border-top: 1px solid #ddd;
          background: #fff;
        }
        #chat-input {
          flex: 1;
          padding: 12px;
          border: none;
          background: #fff;
          font-size: 14px;
        }
        #attach-button, #emoji-button {
          padding: 12px;
          cursor: pointer;
          color: #666;
        }
        #file-input {
          display: none;
        }
        #file-preview-container {
          display: none;
          padding: 8px;
          background: #f9f9f9;
          border-radius: 4px;
          margin: 0 15px 10px;
        }
        #file-preview-box {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        #file-preview-name {
          max-width: 80%;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          font-size: 12px;
        }
        #remove-file {
          cursor: pointer;
          color: #ff4d4d;
          font-weight: bold;
          padding: 2px 6px;
        }
        #emoji-picker {
          position: absolute;
          bottom: 60px;
          right: 20px;
          background: white;
          border: 1px solid #ccc;
          border-radius: 5px;
          box-shadow: 0 3px 10px rgba(0,0,0,0.2);
          padding: 10px;
          display: none;
          z-index: 1001;
        }
        #emoji-picker .emoji {
          cursor: pointer;
          font-size: 20px;
          padding: 5px;
          margin: 2px;
          display: inline-block;
        }
        #emoji-picker .emoji:hover {
          background: #f0f0f0;
          border-radius: 4px;
        }
      </style>
      <div id="chat-bubble">💬</div>
      <div id="chat-window">
        <div id="chat-header">Chat with Us</div>
        <div id="chat-messages">
          <img id="chat-messages-logo" src="${WIDGET_CONFIG.logoUrl}" alt="Techserve Logo" onload="console.log('Logo loaded')" onerror="console.error('Failed to load logo')" />
        </div>
        <div id="chat-form">
          <div class="form-group">
            <label for="form-name">Name:</label>
            <input id="form-name" type="text" placeholder="Enter your name" required />
          </div>
          <div class="form-group">
            <label for="form-email">Email:</label>
            <input id="form-email" type="email" placeholder="Enter your email" required />
          </div>
          <button id="form-submit" class="submit-btn">Submit</button>
        </div>
        <div id="file-preview-container">
          <div id="file-preview-box">
            <span id="file-preview-name"></span>
            <span id="remove-file">✕</span>
          </div>
        </div>
        <div id="chat-footer">
          <input id="chat-input" type="text" placeholder="Type a message..." />
          <label id="attach-button" for="file-input">📎</label>
          <input id="file-input" type="file" />
          <span id="emoji-button">😊</span>
        </div>
        <div id="emoji-picker"></div>
    `;
  document.body.appendChild(widgetContainer);

  // Load emoji-picker-element
  const emojiScript = document.createElement("script");
  emojiScript.src =
    "https://cdn.jsdelivr.net/npm/emoji-picker-element@^1/index.js";
  emojiScript.type = "module";
  document.head.appendChild(emojiScript);

  // Initialize emoji picker
  emojiScript.onload = () => {
    const emojiPicker = document.createElement("emoji-picker");
    document.getElementById("emoji-picker").appendChild(emojiPicker);
    emojiPicker.addEventListener("emoji-click", (event) => {
      const input = document.getElementById("chat-input");
      input.value += event.detail.unicode;
      document.getElementById("emoji-picker").style.display = "none";
      notifyTyping();
    });
  };

  // Toggle chat window
  const bubble = document.getElementById("chat-bubble");
  const chatWindow = document.getElementById("chat-window");
  bubble.addEventListener("click", () => {
    chatWindow.style.display =
      chatWindow.style.display === "none" ? "block" : "none";
    if (chatWindow.style.display === "block" && !socket) {
      initializeChat();
    }
  });

  // Toggle emoji picker
  const emojiButton = document.getElementById("emoji-button");
  emojiButton.addEventListener("click", () => {
    const emojiPicker = document.getElementById("emoji-picker");
    emojiPicker.style.display =
      emojiPicker.style.display === "block" ? "none" : "block";
  });

  // Hide emoji picker when clicking outside
  document.addEventListener("click", (event) => {
    const emojiPicker = document.getElementById("emoji-picker");
    if (
      emojiPicker.style.display === "block" &&
      event.target !== emojiButton &&
      !emojiPicker.contains(event.target)
    ) {
      emojiPicker.style.display = "none";
    }
  });

  // Initialize chat
  function initializeChat() {
    if (roomId) {
      connectWebSocket(roomId);
    } else {
      fetch(WIDGET_CONFIG.apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      })
        .then((response) => {
          if (!response.ok) throw new Error("Failed to create room");
          return response.json();
        })
        .then((data) => {
          roomId = data.room_id;
          localStorage.setItem("chat_room_id", roomId);
          connectWebSocket(roomId);
        })
        .catch((error) => {
          console.error("Error creating room:", error);
          appendSystemMessage("Failed to start chat. Please try again.");
        });
    }
  }

  // Connect to WebSocket
  function connectWebSocket(roomId) {
    socket = new WebSocket(`${WIDGET_CONFIG.wsUrl}${roomId}/`);

    socket.onopen = () => {
      console.log("WebSocket connected");
    };

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const messagesDiv = document.getElementById("chat-messages");
      const formDiv = document.getElementById("chat-form");
      const footer = document.getElementById("chat-footer");

      if (data.show_form && data.form_type === "user_info") {
        formDiv.style.display = "block";
        footer.style.display = "none";
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
      } else if (data.form_data_received) {
        formDiv.style.display = "none";
        footer.style.display = "flex";
      } else if (data.typing && data.sender !== "User") {
        const typingId = `typing-${data.sender}`;
        let typingElement = document.getElementById(typingId);
        if (!typingElement) {
          typingElement = document.createElement("div");
          typingElement.id = typingId;
          typingElement.className = "message system";
          typingElement.innerHTML = `<i>${sanitizeHTML(
            data.sender
          )} is typing...</i>`;
          messagesDiv.appendChild(typingElement);
          messagesDiv.scrollTop = messagesDiv.scrollHeight;
          setTimeout(() => typingElement.remove(), 2000);
        }
      } else if (data.status === "seen" && sentMessages[data.message_id]) {
        updateMessageStatus(data.message_id, data.status);
      } else if (data.error) {
        appendSystemMessage(`Error: ${sanitizeHTML(data.error)}`);
      } else if (data.message || data.file_url) {
        appendMessage(
          data.sender,
          data.message,
          data.file_url,
          data.file_name,
          data.sender === "User"
            ? "user"
            : data.sender === "System"
            ? "system"
            : "agent",
          data.message_id,
          data.sender === "User" ? "sent" : "delivered"
        );
        if (data.sender !== "User") {
          socket.send(
            JSON.stringify({
              status: "seen",
              message_id: data.message_id,
              sender: "User",
            })
          );
          playNotificationSound();
        }
      }
    };

    socket.onclose = () => {
      console.log("WebSocket disconnected");
      appendSystemMessage("Disconnected. Please refresh to reconnect.");
    };

    socket.onerror = (error) => {
      console.error("WebSocket error:", error);
      appendSystemMessage("Chat error occurred.");
    };
  }

  // Append message
  function appendMessage(
    sender,
    message,
    fileUrl,
    fileName,
    className,
    messageId,
    status
  ) {
    const messagesDiv = document.getElementById("chat-messages");
    const div = document.createElement("div");
    div.className = `message ${className}`;
    div.id = `msg-${messageId}`;
    const time = new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
    const ticks = sender === "User" ? getTicks(status) : "";

    let content = message
      ? `<strong>${sanitizeHTML(sender)}:</strong> ${sanitizeHTML(message)}`
      : `<strong>${sanitizeHTML(sender)}:</strong>`;
    if (fileUrl) {
      const isImage = fileName.match(/\.(jpg|jpeg|png|gif)$/i);
      content += `<div class="file-preview">${
        isImage
          ? `<img src="${sanitizeHTML(fileUrl)}" alt="${sanitizeHTML(
              fileName
            )}" />`
          : `<a href="${sanitizeHTML(fileUrl)}" target="_blank">${sanitizeHTML(
              fileName
            )}</a>`
      }</div>`;
    }
    div.innerHTML = `${content}<span class="timestamp">${time} ${ticks}</span>`;
    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    if (sender === "User") {
      sentMessages[messageId] = true;
    }
  }

  // Append system message
  function appendSystemMessage(message) {
    appendMessage(
      "System",
      message,
      null,
      null,
      "system",
      `sys-${Date.now()}`,
      "delivered"
    );
  }

  // Update message status
  function updateMessageStatus(messageId, status) {
    const messageDiv = document.getElementById(`msg-${messageId}`);
    if (messageDiv) {
      const parts = messageDiv.innerHTML.split('<span class="timestamp">')[0];
      const time = new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      });
      messageDiv.innerHTML = `${parts}<span class="timestamp">${time} ${getTicks(
        status
      )}</span>`;
    }
  }

  // Get tick marks
  function getTicks(status) {
    switch (status) {
      case "sent":
        return '<span class="tick">✓</span>';
      case "delivered":
        return '<span class="tick">✓✓</span>';
      case "seen":
        return '<span class="tick blue">✓✓</span>';
      default:
        return "";
    }
  }

  // Send message
  const input = document.getElementById("chat-input");
  input.addEventListener("keypress", (e) => {
    if (e.key === "Enter" && input.value.trim() && socket) {
      const messageId = generateMessageId();
      socket.send(
        JSON.stringify({
          message: input.value,
          sender: "User",
          message_id: messageId,
        })
      );
      appendMessage("User", input.value, null, null, "user", messageId, "sent");
      input.value = "";
    }
  });

  // Send typing status
  let typingTimeout;
  function notifyTyping() {
    const content = input.value.trim();
    if (socket) {
      socket.send(
        JSON.stringify({
          typing: content.length > 0,
          content: content,
          sender: "User",
        })
      );
      clearTimeout(typingTimeout);
      typingTimeout = setTimeout(() => {
        socket.send(
          JSON.stringify({
            typing: false,
            content: "",
            sender: "User",
          })
        );
      }, 1000);
    }
  }
  input.addEventListener("input", notifyTyping);

  // Handle form submission
  const formSubmit = document.getElementById("form-submit");
  formSubmit.addEventListener("click", () => {
    const name = document.getElementById("form-name").value.trim();
    const email = document.getElementById("form-email").value.trim();
    if (name && email && socket) {
      if (!isValidEmail(email)) {
        appendSystemMessage("Please enter a valid email address.");
        return;
      }
      const messageId = generateMessageId();
      socket.send(
        JSON.stringify({
          form_data: { name, email },
          sender: "User",
          message_id: messageId,
        })
      );
      const formattedMessage = `Name: ${name}, Email: ${email}`;
      appendMessage(
        "User",
        formattedMessage,
        null,
        null,
        "user",
        messageId,
        "sent"
      );
      document.getElementById("form-name").value = "";
      document.getElementById("form-email").value = "";
    } else {
      appendSystemMessage("Please enter both name and email.");
    }
  });

  // Email validation
  function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  }

  // Handle file selection
  const fileInput = document.getElementById("file-input");
  fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    const previewContainer = document.getElementById("file-preview-container");
    const previewName = document.getElementById("file-preview-name");
    if (file) {
      previewName.textContent = file.name;
      previewContainer.style.display = "block";
    } else {
      previewContainer.style.display = "none";
    }
  });

  // Remove selected file
  const removeFile = document.getElementById("remove-file");
  removeFile.addEventListener("click", () => {
    fileInput.value = "";
    document.getElementById("file-preview-container").style.display = "none";
  });

  // Handle file upload
  fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    if (file && socket) {
      const formData = new FormData();
      formData.append("file", file);
      fetch(WIDGET_CONFIG.fileUploadUrl, {
        method: "POST",
        body: formData,
      })
        .then((response) => {
          if (!response.ok) throw new Error("File upload failed");
          return response.json();
        })
        .then((data) => {
          const messageId = generateMessageId();
          socket.send(
            JSON.stringify({
              message: "",
              sender: "User",
              message_id: messageId,
              file_url: data.file_url,
              file_name: data.file_name,
            })
          );
          appendMessage(
            "User",
            "",
            data.file_url,
            data.file_name,
            "user",
            messageId,
            "sent"
          );
          fileInput.value = "";
          document.getElementById("file-preview-container").style.display =
            "none";
        })
        .catch((error) => {
          console.error("File upload error:", error);
          appendSystemMessage("Failed to upload file.");
        });
    }
  });

  // Sanitize HTML
  function sanitizeHTML(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // Generate message ID
  function generateMessageId() {
    return Math.random().toString(36).substr(2, 9);
  }

  // Play notification sound
  function playNotificationSound() {
    const audio = new Audio("https://yourdomain.com/static/notification.mp3");
    audio.play().catch(() => console.log("Notification sound blocked"));
  }
})();
