
document.addEventListener("DOMContentLoaded", async function () {
  let scriptSrc;
  let scriptTag;

  if (document.currentScript && document.currentScript.src) {
    scriptSrc = document.currentScript.src;
    scriptTag = document.currentScript;
  } else {
    const scripts = document.getElementsByTagName("script");
    scriptTag = Array.from(scripts).find((s) => s.src.includes("chat_widget.js"));
    if (scriptTag) {
      scriptSrc = scriptTag.src;
    } else {
      console.error("Unable to find chat_widget.js script tag");
      return;
    }
  }

  const urlParams = new URLSearchParams(scriptSrc.split("?")[1]);
  const widgetId = urlParams.get("widget_id");

  if (!widgetId) {
    console.error("Widget ID not found in script URL");
    return;
  }

  // Widget configuration
  console.log("Initializing chat widget with ID:", widgetId);
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
    // themeColor: "#008060",
    // logoUrl: "https://crm-chat-files.s3.amazonaws.com/widget_logos/b80482a9-5625-4441-9e3f-c5733c3db7b3/image%202100.png",
    position: "right",
    chatTitle: "Chat with Us",
    placeholder: "Type a message...",
    bubbleSize: "100",
    windowWidth: "340",
    windowHeight: "400",
    bottomOffset: "20",
    sideOffset: "20",
    enableAttentionGrabber: false,
    attentionGrabber: "",
    is_active: false,
  };

  const baseApi = isLocal
    ? "http://localhost:8000"
    : "http://208.87.134.149:8003";

  try {
    const response = await fetch(`${baseApi}/chat/widget/settings/${widgetId}/`);
    if (!response.ok) throw new Error("Failed to fetch widget settings");
    const { settings } = await response.json();

    if (settings) {
      WIDGET_CONFIG.themeColor = settings.primaryColor || WIDGET_CONFIG.themeColor;
      WIDGET_CONFIG.logoUrl = settings.logo || WIDGET_CONFIG.logoUrl;
      WIDGET_CONFIG.position = settings.position || WIDGET_CONFIG.position;
      WIDGET_CONFIG.enableAttentionGrabber = settings.enableAttentionGrabber || false;
      WIDGET_CONFIG.attentionGrabber = settings.attentionGrabber || "";
      WIDGET_CONFIG.chatTitle = settings.welcomeMessage || WIDGET_CONFIG.chatTitle;
      WIDGET_CONFIG.placeholder = settings.placeholder || WIDGET_CONFIG.placeholder;
      WIDGET_CONFIG.is_active = settings.is_active || WIDGET_CONFIG.is_active;
    }
  } catch (err) {
    console.warn("Error fetching widget settings:", err);
  }

  // Check if widget is active before rendering
  if (!WIDGET_CONFIG.is_active) {
    console.log("Widget is not active, not rendering");
    return; // Exit early if widget is not active
  }

  const bubblePosition = WIDGET_CONFIG.position === "left" ? "left" : "right";
  const windowPosition = WIDGET_CONFIG.position === "left" ? "left" : "right";

  const widgetContainer = document.createElement("div");
  widgetContainer.id = "chat-widget";

  const attentionGrabberHTML =
    WIDGET_CONFIG.enableAttentionGrabber && WIDGET_CONFIG.attentionGrabber
      ? `<img src="${WIDGET_CONFIG.attentionGrabber}" alt="Attention Grabber" style="width: 100px; margin-bottom: 8px; display: block;" />`
      : "";

  // Inject widget HTML
  // const widgetContainer = document.createElement("div");
  // widgetContainer.id = "chat-widget";
  widgetContainer.innerHTML = `
        <style>
            #chat-widget * {
                box-sizing: border-box;
            }
            
            /* Chat bubble container with dynamic positioning */
            #chat-bubble-container {
              position: fixed;
              bottom: ${WIDGET_CONFIG.bottomOffset}px;
              ${bubblePosition}: ${WIDGET_CONFIG.sideOffset}px;
              z-index: 1000;
            }
            
            #chat-bubble {
              position: relative;
              background: ${WIDGET_CONFIG.themeColor};
              padding: 10px;
              border-radius: 50%;
              cursor: pointer;
              box-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
              transition: transform 0.2s;
              width: ${WIDGET_CONFIG.bubbleSize}px;
              height: ${WIDGET_CONFIG.bubbleSize}px;
              display: flex;
              align-items: center;
              justify-content: center;
            }

            #chat-bubble img {
                width: ${parseInt(WIDGET_CONFIG.bubbleSize) - 20}px;
                height: ${parseInt(WIDGET_CONFIG.bubbleSize) - 20}px;
                object-fit: contain;
                border-radius: 50%;
            }

            #chat-bubble:hover {
                transform: scale(1.1);
            }
            
            /* Notification badge positioning */
            .notification-badge {
                position: absolute;
                top: -5px;
                ${bubblePosition === "left" ? "left" : "right"}: -5px;
                background: #ff4757;
                color: white;
                border-radius: 50%;
                width: 22px;
                height: 22px;
                display: none;
                align-items: center;
                justify-content: center;
                font-size: 12px;
                font-weight: bold;
                border: 2px solid white;
                z-index: 1001;
                animation: pulse 2s infinite;
            }
            
            .notification-badge.show {
                display: flex !important;
            }
            
            @keyframes pulse {
                0% { transform: scale(1); }
                50% { transform: scale(1.1); }
                100% { transform: scale(1); }
            }
            
            #chat-window {
                display: none;
                position: fixed;
                bottom: ${parseInt(WIDGET_CONFIG.bottomOffset) + parseInt(WIDGET_CONFIG.bubbleSize) + 10}px;
                ${windowPosition}: ${WIDGET_CONFIG.sideOffset}px;
                width: ${WIDGET_CONFIG.windowWidth}px;
                height: ${WIDGET_CONFIG.windowHeight}px;
                background: white;
                border-radius: 12px;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
                z-index: 1000;
                font-family: Arial, sans-serif;
                flex-direction: column;
            }
            
            #chat-header {
                background: linear-gradient(to right, #F0F0F0, #E5E5E5);
                color: #333;
                padding: 12px;
                font-weight: bold;
                font-size: 16px;
                text-align: center;
                flex-shrink: 0;
                border-bottom: 1px solid #DDD;
                display: flex;
                align-items: center;
                justify-content: center;
                position: relative;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                width: 100%;
                z-index: 2;
            }
            
            #chat-content {
                flex: 1;
                display: flex;
                flex-direction: column;
                width: 100%;
            }
            
            #chat-messages {
                position: relative;
                flex-grow: 1;
                min-height: 200px;
                overflow-y: auto;
                padding: 15px;
                background: white;
                display: flex;
                flex-direction: column;
            }
            
            #chat-messages::-webkit-scrollbar {
                width: 6px;
            }
            
            #chat-messages::-webkit-scrollbar-track {
                background: #f1f1f1;
                border-radius: 10px;
            }
            
            #chat-messages::-webkit-scrollbar-thumb {
                background: ${WIDGET_CONFIG.themeColor};
                border-radius: 10px;
            }
            
            #chat-messages::-webkit-scrollbar-thumb:hover {
                background: ${WIDGET_CONFIG.themeColor}CC;
            }
            
            #chat-messages {
                scrollbar-width: thin;
                scrollbar-color: ${WIDGET_CONFIG.themeColor} #f1f1f1;
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
                margin: 8px 0;
                max-width: 75%;
                padding: 12px 15px;
                border-radius: 15px;
                font-size: 14px;
                font-weight: 500;
                position: relative;
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            }
            
            .user {
                background: ${WIDGET_CONFIG.themeColor};
                color: white;
                align-self: flex-end;
                text-align: right;
            }
            
            .agent, .system {
                background: #E5DDD5;
                color: #333;
                align-self: flex-start;
                text-align: left;
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
                background: #E5DDD5;
                border-radius: 10px;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
                margin: 8px 0;
                max-width: 300px;
                align-self: flex-start;
                text-align: right;
                flex-shrink: 0;
            }
            
            .form-group {
                margin-bottom: 10px;
            }
            
            .form-group label {
                display: block;
                font-weight: 500;
                margin-bottom: 5px;
                color: #333;
                font-size: 12px;
                text-align: left;
            }
            
            .form-group input {
                width: 100%;
                padding: 8px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 12px;
            }
            
            .form-group input:focus {
                border-color: ${WIDGET_CONFIG.themeColor};
                outline: none;
                box-shadow: 0 0 0 2px ${WIDGET_CONFIG.themeColor}33;
            }
            
            .submit-btn {
                background: ${WIDGET_CONFIG.themeColor};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 15px;
                font-size: 12px;
                cursor: pointer;
                float: right;
                transition: background 0.2s;
            }
            
            .submit-btn:hover {
                background: ${WIDGET_CONFIG.themeColor}CC;
            }
            
            #chat-footer {
                display: flex;
                align-items: center;
                border-top: 1px solid #ddd;
                background: rgba(249, 249, 249, 0.26);
                padding: 10px;
                flex-shrink: 0;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }
            
            #chat-input {
                flex: 1;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 20px;
                font-size: 14px;
                outline: none;
                transition: border-color 0.2s;
            }
            
            #chat-input:focus {
                border-color: ${WIDGET_CONFIG.themeColor};
                box-shadow: 0 0 0 2px ${WIDGET_CONFIG.themeColor}33;
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
                flex-shrink: 0;
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
                ${windowPosition}: 20px;
                background: white;
                border: 1px solid #ccc;
                border-radius: 5px;
                box-shadow: 0 3px 10px rgba(0, 0, 0, 0.2);
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
            
            #mute-toggle {
                position: absolute;
                top: 10px;
                right: 10px;
                cursor: pointer;
                font-size: 16px;
                color: #666;
                padding: 5px;
            }
            
            #mute-toggle:hover {
                color: ${WIDGET_CONFIG.themeColor};
            }
            
            #send-btn {
                background: ${WIDGET_CONFIG.themeColor};
                color: white;
                border: none;
                border-radius: 20px;
                padding: 10px 15px;
                font-size: 14px;
                cursor: pointer;
                transition: background 0.2s;
            }
            
            #send-btn:hover {
                background: ${WIDGET_CONFIG.themeColor}CC;
            }
            
            #attach-button, #emoji-button {
                cursor: pointer;
                font-size: 18px;
                margin: 0 5px;
            }
            
            /* Responsive adjustments */
            @media (max-width: 768px) {
                #chat-window {
                    width: calc(100vw - 40px);
                    max-width: ${WIDGET_CONFIG.windowWidth}px;
                    ${windowPosition}: 20px;
                }
            }
        </style>
        
        <!-- Chat bubble container with notification badge -->
        <div id="chat-bubble-container">
          ${attentionGrabberHTML}
            <div id="chat-bubble">
              <img id="chat-bubble-logo" src="${WIDGET_CONFIG.logoUrl}" alt="Chat Logo" />
            </div>
            <div class="notification-badge">1</div>
        </div>
        
        <div id="chat-window">
            <div id="chat-header">
                ${WIDGET_CONFIG.chatTitle}
                <span id="mute-toggle">🔊</span>
            </div>
            <div id="chat-content">
                <div id="chat-messages">
                    <img id="chat-messages-logo" src="${WIDGET_CONFIG.logoUrl}" alt="Chat Logo" onload="console.log('Logo loaded')" onerror="console.error('Failed to load logo')" />
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
                    <input id="chat-input" type="text" placeholder="${WIDGET_CONFIG.placeholder}" />
                    <label id="attach-button" for="file-input">📎</label>
                    <input id="file-input" type="file" />
                    <span id="emoji-button">😊</span>
                    <button id="send-btn">Send</button>
                </div>
            </div>
            <div id="emoji-picker"></div>
        </div>
    `;
  document.body.appendChild(widgetContainer);

  // Log configuration for debugging
  console.log('Widget Configuration:', WIDGET_CONFIG);


  // Globals
  let audioContext = null;
  let socket = null;
  let roomId = localStorage.getItem("chat_room_id") || null;
  let notificationEnabled = true;
  const sentMessages = {};

  // ADD THIS: IP caching variable
  let cachedClientIP = null;

  // Widget state management
  let widgetState = {
    isOpen: false,
    notificationShown: false,
    connectionEstablished: false,
    pageLoadTime: Date.now(),
  };

  // DOM elements cache
  const muteToggle = document.getElementById("mute-toggle");
  const emojiPickerContainer = document.getElementById("emoji-picker");
  const chatBubbleContainer = document.getElementById("chat-bubble-container");
  const chatBubble = document.getElementById("chat-bubble");
  const chatWindow = document.getElementById("chat-window");
  const emojiButton = document.getElementById("emoji-button");
  const input = document.getElementById("chat-input");
  const sendBtn = document.getElementById("send-btn");
  const formSubmit = document.getElementById("form-submit");
  const fileInput = document.getElementById("file-input");
  const removeFileBtn = document.getElementById("remove-file");
  const filePreviewContainer = document.getElementById(
    "file-preview-container"
  );
  const filePreviewName = document.getElementById("file-preview-name");

  // ADD THIS: Function to get client IP
  async function getClientIP() {
    try {
      const response = await fetch("https://api.ipify.org?format=json");
      const data = await response.json();
      if (data && data.ip) return data.ip;
      throw new Error("Invalid IP data");
    } catch (error) {
      console.warn("Primary IP fetch failed:", error);
      try {
        const response = await fetch("https://ipapi.co/ip/");
        const ip = await response.text();
        return ip.trim();
      } catch (fallbackError) {
        console.warn("Fallback IP fetch failed:", fallbackError);
        return null;
      }
    }
  }

  // ADD THIS: Function to cache client IP early
  async function initializeClientIP() {
    try {
      cachedClientIP = await getClientIP();
      console.log("IP cached for widget:", cachedClientIP);
    } catch (error) {
      console.warn("Failed to cache client IP:", error);
    }
  }

  // Initialize AudioContext once
  function initAudioContext() {
    if (audioContext) return;
    try {
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
      console.log("Audio context initialized");
    } catch (e) {
      console.error("Web Audio API is not supported in this browser", e);
    }
  }
  initAudioContext();

  // FIXED: Simplified widget initialization
  function initializeWidgetBehavior() {
    console.log("🔧 initializeWidgetBehavior() called");

    // Ensure widget is closed initially
    if (chatWindow) {
      chatWindow.style.display = "none";
      widgetState.isOpen = false;
      console.log("✅ Widget closed on initialization");
    }

    // Show notification after 2 seconds
    setTimeout(() => {
      console.log("⏰ Showing notification badge after 2 seconds");
      showNotificationBadge();
    }, 2000);
  }

  // FIXED: Simplified notification badge function
  function showNotificationBadge() {
    console.log("🔔 showNotificationBadge() called");

    if (widgetState.notificationShown) {
      console.log("ℹ️ Notification already shown");
      return;
    }

    const notificationBadge = document.querySelector(".notification-badge");
    if (notificationBadge) {
      console.log("✅ Found notification badge, showing it");
      notificationBadge.classList.add("show");
      widgetState.notificationShown = true;
      console.log("🎉 Notification badge shown successfully!");
    } else {
      console.error("❌ Notification badge not found");
    }
  }

      // Set chat bubble position dynamically (left or right)
    const bubbleContainer = document.getElementById("chat-bubble-container");
    if (bubbleContainer) {
      if (WIDGET_CONFIG.position === "left") {
        bubbleContainer.style.left = "20px";
        bubbleContainer.style.right = "";
      } else {
        bubbleContainer.style.right = "20px";
        bubbleContainer.style.left = "";
      }
    }


  // FIXED: Hide notification badge
  function hideNotificationBadge() {
    console.log("🔕 hideNotificationBadge() called");
    const notificationBadge = document.querySelector(".notification-badge");
    if (notificationBadge) {
      notificationBadge.classList.remove("show");
      console.log("✅ Notification badge hidden");
    }
  }

  // Toggle notification sound mute/unmute
  if (muteToggle) {
    muteToggle.textContent = notificationEnabled ? "🔊" : "🔇";
    muteToggle.addEventListener("click", () => {
      notificationEnabled = !notificationEnabled;
      muteToggle.textContent = notificationEnabled ? "🔊" : "🔇";
    });
  }

  // Load emoji-picker-element script and initialize picker once loaded
  const emojiScript = document.createElement("script");
  emojiScript.src =
    "https://cdn.jsdelivr.net/npm/emoji-picker-element@^1/index.js";
  emojiScript.type = "module";
  document.head.appendChild(emojiScript);

  let emojiPicker = null;
  emojiScript.onload = () => {
    if (!emojiPickerContainer) {
      console.error("Emoji picker container (#emoji-picker) not found");
      return;
    }
    // Create emoji picker element
    emojiPicker = document.createElement("emoji-picker");
    emojiPickerContainer.appendChild(emojiPicker);
    emojiPicker.addEventListener("emoji-click", (event) => {
      if (input) {
        input.value += event.detail.unicode;
        emojiPickerContainer.style.display = "none";
        notifyTyping();
      }
    });
  };

  // Toggle chat window visibility and initialize chat on open
  if (chatBubble && chatWindow) {
    chatBubble.addEventListener("click", (event) => {
      // Prevent event bubbling
      event.stopPropagation();

      // Hide notification badge when opening chat
      hideNotificationBadge();

      if (!widgetState.isOpen) {
        // First time opening - establish connection
        openChatWidget();
      } else {
        // Toggle visibility
        const isVisible = chatWindow.style.display === "flex";
        chatWindow.style.display = isVisible ? "none" : "flex";
      }
    });
  }

  function openChatWidget() {
    if (!chatWindow) return;

    // Show chat window
    chatWindow.style.display = "flex";
    widgetState.isOpen = true;

    // Show connecting message only if not already connected
    if (!widgetState.connectionEstablished) {
      establishConnection();
    }
  }

  function establishConnection() {
    // Prevent multiple connection attempts
    if (widgetState.connectionEstablished) {
      return;
    }

    widgetState.connectionEstablished = true;

    // Initialize chat connection
    if (!socket) {
      initializeChat();
    }

    // Show trigger message after connection
    setTimeout(() => {
      // Only show welcome message if chat window is still open
      if (widgetState.isOpen && chatWindow.style.display === "flex") {
        // Clear the connecting message
        const messages = document.querySelectorAll(
          "#chat-messages .message.system"
        );
        if (messages.length > 1) {
          messages[0].remove(); // Remove "Connecting..." message
        }
      }
    }, 1500);
  }

  // Hide emoji picker when clicking outside
  document.addEventListener("click", (event) => {
    if (
      emojiPickerContainer &&
      emojiButton &&
      emojiPickerContainer.style.display === "block" &&
      event.target !== emojiButton &&
      !emojiPickerContainer.contains(event.target)
    ) {
      emojiPickerContainer.style.display = "none";
    }
  });

  // REPLACE THIS: Initialize chat session, create room if needed - UPDATED VERSION
  async function initializeChat() {
    if (roomId) {
      connectWebSocket(roomId);
      return;
    }

    try {
      // Get client IP address (use cached IP or fetch fresh)
      // Get client IP address (use cached IP or fetch fresh)
      const clientIP = cachedClientIP || (await getClientIP());
      console.log("Client IP obtained:", clientIP);

      if (!clientIP) {
        throw new Error("Client IP is not available. Cannot create chat room.");
      }

      // Prepare request body with IP address
      const requestBody = {
        widget_id: widgetId,
        ip: clientIP, // Include IP address in the request
        user_agent: navigator.userAgent, // Include user agent for better context
      };

      const response = await fetch(WIDGET_CONFIG.apiUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest", // Optional: helps identify AJAX requests
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const errorData = await response.json();
        console.log("Response error:", errorData);
        throw new Error(
          `Failed to create room: ${response.status} ${response.statusText}`
        );
      }

      const data = await response.json();
      roomId = data.room_id;
      localStorage.setItem("chat_room_id", roomId);
      connectWebSocket(roomId);
    } catch (error) {
      console.error("Error creating room:", error);
      appendSystemMessage("Failed to start chat. Please try again.");
    }
  }

  // WebSocket connection setup
  function connectWebSocket(roomId) {
    if (socket) {
      socket.close();
    }
    socket = new WebSocket(`${WIDGET_CONFIG.wsUrl}${roomId}/`);

    socket.onopen = () => {
      console.log("WebSocket connected");
      updateConnectionStatus(true);
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleIncomingMessage(data);
      } catch (e) {
        console.error("Failed to parse WebSocket message:", e);
      }
    };

    socket.onclose = () => {
      console.log("WebSocket disconnected");
      updateConnectionStatus(false);
      appendSystemMessage("Disconnected. Please refresh to reconnect.");
    };

    socket.onerror = (error) => {
      console.error("WebSocket error:", error);
      updateConnectionStatus(false);
      appendSystemMessage("Chat error occurred.");
    };
  }

  function updateConnectionStatus(connected) {
    const statusElements = document.querySelectorAll(
      ".connection-status, .status-indicator"
    );
    statusElements.forEach((element) => {
      if (connected) {
        element.classList.add("connected");
        element.classList.remove("disconnected");
      } else {
        element.classList.add("disconnected");
        element.classList.remove("connected");
      }
    });
  }

  // Incoming message handler
  function handleIncomingMessage(data) {
    const messagesDiv = document.getElementById("chat-messages");
    const formDiv = document.getElementById("chat-form");
    const footer = document.getElementById("chat-footer");

    if (data.show_form && data.form_type === "user_info") {
      if (formDiv && footer) {
        formDiv.style.display = "block";
        footer.style.display = "none";
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
      }
      return;
    }

    if (data.form_data_received) {
      if (formDiv && footer) {
        formDiv.style.display = "none";
        footer.style.display = "flex";
      }
      return;
    }

    if (data.typing && data.sender !== "User") {
      const typingId = `typing-${data.sender}`;
      if (!document.getElementById(typingId)) {
        const typingElement = document.createElement("div");
        typingElement.id = typingId;
        typingElement.className = "message system";
        typingElement.innerHTML = `<i>${sanitizeHTML(
          data.sender
        )} is typing...</i>`;
        messagesDiv.appendChild(typingElement);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
        setTimeout(() => {
          const el = document.getElementById(typingId);
          if (el) el.remove();
        }, 2000);
      }
      return;
    }

    if (data.status === "seen" && sentMessages[data.message_id]) {
      updateMessageStatus(data.message_id, data.status);
      return;
    }

    if (data.error) {
      appendSystemMessage(`Error: ${sanitizeHTML(data.error)}`);
      return;
    }

    if (data.message || data.file_url) {
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
        data.sender === "User" ? "delivered" : "delivered"
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
  }

  // Append chat message
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
    if (!messagesDiv) {
      console.error("Chat messages container (#chat-messages) not found");
      return;
    }
    if (document.getElementById(`msg-${messageId}`)) {
      updateMessageStatus(messageId, status, message, fileUrl, fileName);
      return;
    }

    const div = document.createElement("div");
    div.className = `message ${className}`;
    div.id = `msg-${messageId}`;
    const time = new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
    const ticks = sender === "User" ? getTicks(status) : "";

    let content = message ? sanitizeHTML(message) : "";
    if (fileUrl) {
      const isImage = /\.(jpg|jpeg|png|gif)$/i.test(fileName);
      content += `<div class="file-preview">${
        isImage
          ? `<img src="${sanitizeHTML(fileUrl)}" alt="${sanitizeHTML(
              fileName
            )}" />`
          : `<a href="${sanitizeHTML(
              fileUrl
            )}" target="_blank" rel="noopener noreferrer">${sanitizeHTML(
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

  // Append system message wrapper
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

  // Update existing message status/content
  function updateMessageStatus(
    messageId,
    status,
    message = null,
    fileUrl = null,
    fileName = null
  ) {
    const messageDiv = document.getElementById(`msg-${messageId}`);
    if (!messageDiv) return;

    const time = new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });

    let content =
      message !== null
        ? sanitizeHTML(message)
        : messageDiv.innerHTML.split('<span class="timestamp">')[0];
    if (fileUrl) {
      const isImage = /\.(jpg|jpeg|png|gif)$/i.test(fileName);
      content += `<div class="file-preview">${
        isImage
          ? `<img src="${sanitizeHTML(fileUrl)}" alt="${sanitizeHTML(
              fileName
            )}" />`
          : `<a href="${sanitizeHTML(
              fileUrl
            )}" target="_blank" rel="noopener noreferrer">${sanitizeHTML(
              fileName
            )}</a>`
      }</div>`;
    }

    messageDiv.innerHTML = `${content}<span class="timestamp">${time} ${getTicks(
      status
    )}</span>`;
    const messagesDiv = document.getElementById("chat-messages");
    if (messagesDiv) messagesDiv.scrollTop = messagesDiv.scrollHeight;
  }

  // Return tick marks HTML based on status
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

  // Send message logic
  function sendMessage() {
    if (!input || !socket || !input.value.trim()) return;

    const messageId = generateMessageId();
    const messageText = input.value.trim();

    socket.send(
      JSON.stringify({
        message: messageText,
        sender: "User",
        message_id: messageId,
      })
    );
    appendMessage("User", messageText, null, null, "user", messageId, "sent");
    input.value = "";
  }

  // Input enter key event & send button event
  if (input) {
    input.addEventListener("keypress", (e) => {
      if (e.key === "Enter" && input.value.trim() && socket) {
        sendMessage();
      }
    });
  } else {
    console.error("Chat input (#chat-input) not found");
  }

  if (sendBtn) {
    sendBtn.addEventListener("click", sendMessage);
  } else {
    console.error("Send button (#send-btn) not found");
  }

  // Debounced typing notification
  let typingTimeout;
  function notifyTyping() {
    if (!socket || !input) return;

    const content = input.value.trim();

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
  if (input) {
    input.addEventListener("input", notifyTyping);
  }

  // Form submission handler for user info form
  if (formSubmit) {
    formSubmit.addEventListener("click", () => {
      const nameField = document.getElementById("form-name");
      const emailField = document.getElementById("form-email");
      const name = nameField?.value.trim() || "";
      const email = emailField?.value.trim() || "";

      if (!name || !email) {
        appendSystemMessage("Please enter both name and email.");
        return;
      }
      if (!isValidEmail(email)) {
        appendSystemMessage("Please enter a valid email address.");
        return;
      }
      if (!socket) return;

      const messageId = generateMessageId();
      socket.send(
        JSON.stringify({
          form_data: {
            name: name,
            email: email,
          },
          sender: "User",
          message_id: messageId,
        })
      );

      // Clear form fields
      if (nameField) nameField.value = "";
      if (emailField) emailField.value = "";

      appendSystemMessage("Information submitted successfully!");
    });
  } else {
    console.error("Form submit button (#form-submit) not found");
  }

  // File upload handling
  if (fileInput) {
    fileInput.addEventListener("change", (e) => {
      const file = e.target.files[0];
      if (!file) return;

      // File size validation (10MB limit)
      const maxSize = 10 * 1024 * 1024;
      if (file.size > maxSize) {
        appendSystemMessage("File size too large. Maximum size is 10MB.");
        fileInput.value = "";
        return;
      }

      // Show file preview
      if (filePreviewContainer && filePreviewName) {
        filePreviewName.textContent = file.name;
        filePreviewContainer.style.display = "flex";
      }
    });
  } else {
    console.error("File input (#file-input) not found");
  }

  // Remove file preview
  if (removeFileBtn && filePreviewContainer && fileInput) {
    removeFileBtn.addEventListener("click", () => {
      fileInput.value = "";
      filePreviewContainer.style.display = "none";
    });
  } else {
    console.error(
      "Remove file button (#remove-file) or related elements not found"
    );
  }

  // File upload function
  function uploadFile() {
    if (!fileInput || !fileInput.files[0] || !socket) return;

    const file = fileInput.files[0];
    const messageId = generateMessageId();
    const formData = new FormData();
    formData.append("file", file);
    formData.append("room_id", roomId);
    formData.append("message_id", messageId);

    fetch(`${WIDGET_CONFIG.apiUrl}/upload`, {
      method: "POST",
      body: formData,
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to upload file");
        }
        return response.json();
      })
      .then((data) => {
        socket.send(
          JSON.stringify({
            file_url: data.file_url,
            file_name: file.name,
            sender: "User",
            message_id: messageId,
          })
        );
        appendMessage(
          "User",
          null,
          data.file_url,
          file.name,
          "user",
          messageId,
          "sent"
        );

        // Clear file input and hide preview
        fileInput.value = "";
        if (filePreviewContainer) {
          filePreviewContainer.style.display = "none";
        }
      })
      .catch((error) => {
        console.error("Error uploading file:", error);
        appendSystemMessage("Failed to upload file. Please try again.");
      });
  }

  // Utility functions
  function generateMessageId() {
    return `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  function sanitizeHTML(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  }

  function playNotificationSound() {
    if (!notificationEnabled || !audioContext) return;

    try {
      const oscillator = audioContext.createOscillator();
      const gainNode = audioContext.createGain();

      oscillator.connect(gainNode);
      gainNode.connect(audioContext.destination);

      oscillator.frequency.setValueAtTime(800, audioContext.currentTime);
      oscillator.frequency.setValueAtTime(600, audioContext.currentTime + 0.1);

      gainNode.gain.setValueAtTime(0, audioContext.currentTime);
      gainNode.gain.linearRampToValueAtTime(
        0.3,
        audioContext.currentTime + 0.01
      );
      gainNode.gain.exponentialRampToValueAtTime(
        0.01,
        audioContext.currentTime + 0.3
      );

      oscillator.start(audioContext.currentTime);
      oscillator.stop(audioContext.currentTime + 0.3);
    } catch (e) {
      console.error("Error playing notification sound:", e);
    }
  }

  // UPDATED: Initialize on DOM content loaded
  document.addEventListener("DOMContentLoaded", async () => {
    console.log("Chat widget initialized");

    // Cache the client IP early
    await initializeClientIP();

    // Initialize widget behavior (closed state, notification timer)
    initializeWidgetBehavior();

    // Don't auto-connect - only connect when user clicks the widget
  });

  // Handle page visibility changes to manage WebSocket connection
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      console.log("Page hidden, maintaining WebSocket connection");
    } else {
      console.log("Page visible");
      // Reconnect if socket is closed and user has already opened widget
      if (
        widgetState.connectionEstablished &&
        roomId &&
        (!socket || socket.readyState === WebSocket.CLOSED)
      ) {
        connectWebSocket(roomId);
      }
    }
  });

  // Clean up on page unload
  window.addEventListener("beforeunload", () => {
    if (socket) {
      socket.close();
    }
    if (audioContext) {
      audioContext.close();
    }
  });
});
