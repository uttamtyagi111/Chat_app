document.addEventListener("DOMContentLoaded", function () {
    // Extract widget_id from the script URL
    let scriptSrc;
    if (document.currentScript && document.currentScript.src) {
        scriptSrc = document.currentScript.src;
    } else {
        // Fallback: Find the script tag with "chat_widget.js" in its src
        const scripts = document.getElementsByTagName("script");
        const script = Array.from(scripts).find(s => s.src.includes("chat_widget.js"));
        if (script) {
            scriptSrc = script.src;
        } else {
            console.error("Unable to find chat_widget.js script tag");
            return;
        }
    }

    const urlParams = new URLSearchParams(scriptSrc.split('?')[1]);
    const widgetId = urlParams.get('widget_id');

    if (!widgetId) {
        console.error("Widget ID not found in script URL");
        return;
    }

    // Widget configuration
    const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
    const WIDGET_CONFIG = {
        apiUrl: isLocal ? "http://localhost:8000/chat/user-chat/" : "http://208.87.134.149:8003/chat/user-chat/",
        wsUrl: isLocal ? "ws://localhost:8000/ws/chat/" : "ws://208.87.134.149:8003/ws/chat/",
        fileUploadUrl: isLocal ? "http://localhost:8000/chat/user-chat/upload-file/" : "http://208.87.134.149:8003/chat/user-chat/upload-file/",
        themeColor: document.currentScript ? document.currentScript.getAttribute("data-theme-color") || "#008060" : "#008060", // WhatsApp green
        logoUrl: "https://emailbulkshoot.s3.ap-southeast-2.amazonaws.com/assests+for+Email+Automation/Techserve%404x.png",
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
                background: #008060;
                color: white;
                padding: 15px;
                border-radius: 50%;
                cursor: pointer;
                box-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
                font-size: 24px;
                z-index: 1000;
                transition: transform 0.2s;
            }
            #chat-bubble:hover {
                transform: scale(1.1);
            }
            #chat-window {
                // display: none;
                // position: fixed;
                // bottom: 80px;
                // right: 20px;
                // width: 340px;
                // height: 550px;
                background: white;
                border-radius: 12px;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
                z-index: 1000;
                font-family: Arial, sans-serif;
                display: flex;
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
            #menu-btn {
                position: absolute;
                left: 10px;
                cursor: pointer;
                font-size: 20px;
                color: #008060;
                padding: 5px;
            }
            #menu-btn:hover {
                color: #00664d;
            }
            #sidebar {
                width: 250px;
                height: 100%;
                background: #F0F0F0;
                box-shadow: 2px 0 10px rgba(0, 0, 0, 0.2);
                transform: translateX(-100%);
                transition: transform 0.3s ease;
                position: absolute;
                z-index: 1;
                overflow-y: auto;
            }
            #chat-window.open #sidebar {
                transform: translateX(0);
            }
            #sidebar-close {
                position: absolute;
                top: 10px;
                right: 10px;
                font-size: 18px;
                color: #333;
                cursor: pointer;
                padding: 5px;
            }
            #sidebar-close:hover {
                color: #008060;
            }
            #sidebar ul {
                list-style: none;
                padding: 60px 20px 20px;
                margin: 0;
            }
            #sidebar ul li {
                padding: 12px 0;
                font-size: 14px;
                color: #333;
                cursor: pointer;
                transition: color 0.2s;
            }
            #sidebar ul li:hover {
                color: #008060;
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
                background: #008060;
                border-radius: 10px;
            }
            #chat-messages::-webkit-scrollbar-thumb:hover {
                background: #00664d;
            }
            #chat-messages {
                scrollbar-width: thin;
                scrollbar-color: #008060 #f1f1f1;
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
                background: #008060;
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
                border-color: #008060;
                outline: none;
                box-shadow: 0 0 0 2px rgba(0, 128, 96, 0.2);
            }
            .submit-btn {
                background: #008060;
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
                background: #00664d;
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
                margin-right: 10px;
                outline: none;
                transition: border-color 0.2s;
            }
            #chat-input:focus {
                border-color: rgba(128, 26, 0, 0.37);
                box-shadow: 0 0 0 2px rgba(0, 128, 96, 0.2);
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
                right: 20px;
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
                color: #008060;
            }
            #send-btn {
                background: #008060;
                color: white;
                border: none;
                border-radius: 20px;
                padding: 10px 15px;
                font-size: 14px;
                cursor: pointer;
                transition: background 0.2s;
            }
            #send-btn:hover {
                background: #00664d;
            }
            #attach-button, #emoji-button {
                cursor: pointer;
                font-size: 18px;
                margin: 0 5px;
            }
        </style>
        <div id="chat-bubble">💬</div>
        <div id="chat-window">
            <div id="chat-header">
                <span id="menu-btn">☰</span>
                Chat with Us
                <span id="mute-toggle">🔊</span>
            </div>
            <div id="sidebar">
                <span id="sidebar-close">✕</span>
                <ul>
                    <li>New Chat</li>
                    <li>Profile</li>
                    <li>Settings</li>
                    <li>Logout</li>
                </ul>
            </div>
            <div id="chat-content">
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
                    <button id="send-btn">Send</button>
                </div>
            </div>
            <div id="emoji-picker"></div>
        </div>
    `;
    document.body.appendChild(widgetContainer);

    // Initialize audio context and sound settings
    let audioContext;
    let notificationEnabled = true;

    // Set up the audio context when user interacts with the page
    document.addEventListener('click', initAudioContext, { once: true });

    function initAudioContext() {
        try {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
            console.log("Audio context initialized");
        } catch (e) {
            console.error("Web Audio API is not supported in this browser", e);
        }
    }

    // Toggle notification sound
    const muteToggle = document.getElementById("mute-toggle");
    if (muteToggle) {
        muteToggle.addEventListener("click", () => {
            notificationEnabled = !notificationEnabled;
            muteToggle.textContent = notificationEnabled ? "🔊" : "🔇";
        });
    } else {
        console.error("Mute toggle (#mute-toggle) not found");
    }

    // Load emoji-picker-element
    const emojiScript = document.createElement("script");
    emojiScript.src = "https://cdn.jsdelivr.net/npm/emoji-picker-element@^1/index.js";
    emojiScript.type = "module";
    document.head.appendChild(emojiScript);

    // Initialize emoji picker
    emojiScript.onload = () => {
        const emojiPicker = document.createElement("emoji-picker");
        const emojiPickerContainer = document.getElementById("emoji-picker");
        if (emojiPickerContainer) {
            emojiPickerContainer.appendChild(emojiPicker);
            emojiPicker.addEventListener("emoji-click", (event) => {
                const input = document.getElementById("chat-input");
                if (input) {
                    input.value += event.detail.unicode;
                    emojiPickerContainer.style.display = "none";
                    notifyTyping();
                }
            });
        } else {
            console.error("Emoji picker container (#emoji-picker) not found");
        }
    };

    // Toggle chat window
    const bubble = document.getElementById("chat-bubble");
    const chatWindow = document.getElementById("chat-window");
    if (bubble && chatWindow) {
        bubble.addEventListener("click", () => {
            chatWindow.style.display = chatWindow.style.display === "none" ? "block" : "none";
            if (chatWindow.style.display === "block" && !socket) {
                initializeChat();
            }
        });
    } else {
        console.error("Chat bubble (#chat-bubble) or chat window (#chat-window) not found");
    }

    // Toggle sidebar
    const menuBtn = document.getElementById("menu-btn");
    const sidebar = document.getElementById("sidebar");
    const sidebarClose = document.getElementById("sidebar-close");
    if (menuBtn && chatWindow) {
        menuBtn.addEventListener("click", () => {
            chatWindow.classList.add("open");
        });
    } else {
        console.error("Menu button (#menu-btn) or chat window (#chat-window) not found");
    }
    if (sidebarClose && chatWindow) {
        sidebarClose.addEventListener("click", () => {
            chatWindow.classList.remove("open");
        });
    } else {
        console.error("Sidebar close button (#sidebar-close) or chat window (#chat-window) not found");
    }

    // Toggle emoji picker
    const emojiButton = document.getElementById("emoji-button");
    const emojiPicker = document.getElementById("emoji-picker");
    if (emojiButton && emojiPicker) {
        emojiButton.addEventListener("click", () => {
            emojiPicker.style.display = emojiPicker.style.display === "block" ? "none" : "block";
        });
    } else {
        console.error("Emoji button (#emoji-button) or emoji picker (#emoji-picker) not found");
    }

    // Hide emoji picker when clicking outside
    document.addEventListener("click", (event) => {
        const emojiPicker = document.getElementById("emoji-picker");
        const emojiButton = document.getElementById("emoji-button");
        if (
            emojiPicker &&
            emojiButton &&
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
                body: JSON.stringify({ widget_id: widgetId }),
            })
                .then((response) => {
                    console.log("Response status:", response.status);
                    if (!response.ok) {
                        response.json().then(data => console.log("Response error:", data));
                        throw new Error("Failed to create room");
                    }
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
        // Close existing socket if it exists
        if (socket) {
            socket.close();
        }
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
                if (formDiv && footer) {
                    formDiv.style.display = "block";
                    footer.style.display = "none";
                    messagesDiv.scrollTop = messagesDiv.scrollHeight;
                }
            } else if (data.form_data_received) {
                if (formDiv && footer) {
                    formDiv.style.display = "none";
                    footer.style.display = "flex";
                }
            } else if (data.typing && data.sender !== "User") {
                const typingId = `typing-${data.sender}`;
                let typingElement = document.getElementById(typingId);
                if (!typingElement) {
                    typingElement = document.createElement("div");
                    typingElement.id = typingId;
                    typingElement.className = "message system";
                    typingElement.innerHTML = `<i>${sanitizeHTML(data.sender)} is typing...</i>`;
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
                    data.sender === "User" ? "user" : data.sender === "System" ? "system" : "agent",
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
    function appendMessage(sender, message, fileUrl, fileName, className, messageId, status) {
        const messagesDiv = document.getElementById("chat-messages");
        if (!messagesDiv) {
            console.error("Chat messages container (#chat-messages) not found");
            return;
        }
        // Check if message already exists
        const existingMessage = document.getElementById(`msg-${messageId}`);
        if (existingMessage) {
            console.log(`Message ${messageId} already exists, updating status`);
            updateMessageStatus(messageId, status, message, fileUrl, fileName);
            return;
        }

        console.log(`Appending message: ${messageId}, sender: ${sender}, status: ${status}`);
        const div = document.createElement("div");
        div.className = `message ${className}`;
        div.id = `msg-${messageId}`;
        const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        const ticks = sender === "User" ? getTicks(status) : "";

        let content = message ? `${sanitizeHTML(message)}` : "";
        if (fileUrl) {
            const isImage = fileName.match(/\.(jpg|jpeg|png|gif)$/i);
            content += `<div class="file-preview">${
                isImage
                    ? `<img src="${sanitizeHTML(fileUrl)}" alt="${sanitizeHTML(fileName)}" />`
                    : `<a href="${sanitizeHTML(fileUrl)}" target="_blank">${sanitizeHTML(fileName)}</a>`
            }</div>`;
        }
        div.innerHTML = `${content}<span class="timestamp">${time} ${ticks}</span>`;
        messagesDiv.appendChild(div);
        messagesDiv.scrollTop = messagesDiv.scrollHeight; // Auto-scroll to bottom
        if (sender === "User") {
            sentMessages[messageId] = true;
        }
    }

    // Append system message
    function appendSystemMessage(message) {
        appendMessage("System", message, null, null, "system", `sys-${Date.now()}`, "delivered");
    }

    // Update message status or content
    function updateMessageStatus(messageId, status, message = null, fileUrl = null, fileName = null) {
        const messageDiv = document.getElementById(`msg-${messageId}`);
        if (messageDiv) {
            const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
            let content = message ? `${sanitizeHTML(message)}` : messageDiv.innerHTML.split('<span class="timestamp">')[0];
            if (fileUrl) {
                const isImage = fileName.match(/\.(jpg|jpeg|png|gif)$/i);
                content += `<div class="file-preview">${
                    isImage
                        ? `<img src="${sanitizeHTML(fileUrl)}" alt="${sanitizeHTML(fileName)}" />`
                        : `<a href="${sanitizeHTML(fileUrl)}" target="_blank">${sanitizeHTML(fileName)}</a>`
                }</div>`;
            }
            messageDiv.innerHTML = `${content}<span class="timestamp">${time} ${getTicks(status)}</span>`;
            const messagesDiv = document.getElementById("chat-messages");
            messagesDiv.scrollTop = messagesDiv.scrollHeight; // Auto-scroll to bottom
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
    const sendBtn = document.getElementById("send-btn");
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
        sendBtn.addEventListener("click", () => {
            if (input && input.value.trim() && socket) {
                sendMessage();
            }
        });
    } else {
        console.error("Send button (#send-btn) not found");
    }

    function sendMessage() {
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
    if (input) {
        input.addEventListener("input", notifyTyping);
    }

    // Handle form submission
    const formSubmit = document.getElementById("form-submit");
    if (formSubmit) {
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
                appendMessage("User", formattedMessage, null, null, "user", messageId, "sent");
                document.getElementById("form-name").value = "";
                document.getElementById("form-email").value = "";
            } else {
                appendSystemMessage("Please enter both name and email.");
            }
        });
    } else {
        console.error("Form submit button (#form-submit) not found");
    }

    // Email validation
    function isValidEmail(email) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(email);
    }

    // Handle file selection
    const fileInput = document.getElementById("file-input");
    if (fileInput) {
        fileInput.addEventListener("change", () => {
            const file = fileInput.files[0];
            const previewContainer = document.getElementById("file-preview-container");
            const previewName = document.getElementById("file-preview-name");
            if (file && previewContainer && previewName) {
                previewName.textContent = file.name;
                previewContainer.style.display = "block";
            } else if (previewContainer) {
                previewContainer.style.display = "none";
            }
        });
    } else {
        console.error("File input (#file-input) not found");
    }

    // Remove selected file
    const removeFile = document.getElementById("remove-file");
    if (removeFile) {
        removeFile.addEventListener("click", () => {
            if (fileInput) {
                fileInput.value = "";
            }
            const previewContainer = document.getElementById("file-preview-container");
            if (previewContainer) {
                previewContainer.style.display = "none";
            }
        });
    } else {
        console.error("Remove file button (#remove-file) not found");
    }

    // Handle file upload
    if (fileInput) {
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
                        appendMessage("User", "", data.file_url, data.file_name, "user", messageId, "sent");
                        fileInput.value = "";
                        const previewContainer = document.getElementById("file-preview-container");
                        if (previewContainer) {
                            previewContainer.style.display = "none";
                        }
                    })
                    .catch((error) => {
                        console.error("File upload error:", error);
                        appendSystemMessage("Failed to upload file.");
                    });
            }
        });
    }

    // Play notification sound using Web Audio API
    function playNotificationSound() {
        if (!notificationEnabled || !audioContext) {
            return;
        }

        try {
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();

            oscillator.type = 'sine';
            oscillator.frequency.setValueAtTime(880, audioContext.currentTime); // A5 note
            oscillator.frequency.setValueAtTime(1318.51, audioContext.currentTime + 0.1); // E6 note

            gainNode.gain.setValueAtTime(0, audioContext.currentTime);
            gainNode.gain.linearRampToValueAtTime(0.2, audioContext.currentTime + 0.05);
            gainNode.gain.linearRampToValueAtTime(0, audioContext.currentTime + 0.3);

            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);

            oscillator.start(audioContext.currentTime);
            oscillator.stop(audioContext.currentTime + 0.3);
        } catch (error) {
            console.error("Error playing notification sound:", error);
        }
    }

    // Sanitize HTML
    function sanitizeHTML(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    // Generate message ID
    function generateMessageId() {
        return `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    }
});