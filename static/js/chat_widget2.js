// Initialize all global variables at the top
let audioContext = null;
let socket = null;
let notificationEnabled = true;
const sentMessages = {};
let roomId = null;
let cachedClientIP = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_DELAY = 3000; // 3 seconds
let chatHistoryLoaded = false;
let historyLimit = localStorage.getItem('chat_history_limit') || 'full';
const historyOptions = {
    '5': 'Last 5 messages',
    '10': 'Last 10 messages',
    'full': 'Full history'
};

// Widget state management
let widgetState = {
    isOpen: false,
    notificationShown: false,
    connectionEstablished: false,
    pageLoadTime: Date.now(),
    isTyping: false,
    lastTypingTime: 0
};

// Form trigger keywords (case-insensitive)
const FORM_TRIGGER_KEYWORDS = [
    "fill the following information",
    "provide your details",
    "enter your name and email",
    "we need your contact information",
    "please share your details"
];

// Function to get client IP
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

// Main initialization function
async function initializeChatWidget() {
    try {
        // Get script element and extract widget ID
        let scriptSrc;
        let scriptTag;

        if (document.currentScript && document.currentScript.src) {
            scriptSrc = document.currentScript.src;
            scriptTag = document.currentScript;
        } else {
            const scripts = document.getElementsByTagName("script");
            scriptTag = Array.from(scripts).find((s) => s.src.includes("chat_widget2.js"));
            if (scriptTag) {
                scriptSrc = scriptTag.src;
            } else {
                console.error("Unable to find chat_widget2.js script tag");
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
        const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";

        const WIDGET_CONFIG = {
            apiUrl: isLocal ? "http://localhost:8000/chat/user-chat/" : "http://208.87.134.149:8003/chat/user-chat/",
            wsUrl: isLocal ? "ws://localhost:8000/ws/chat/" : "ws://208.87.134.149:8003/ws/chat/",
            fileUploadUrl: isLocal ? "http://localhost:8000/chat/user-chat/upload-file/" : "http://208.87.134.149:8003/chat/user-chat/upload-file/",
            historyUrl: isLocal ? "http://localhost:8000/chat/user-chat/history/" : "http://208.87.134.149:8003/chat/user-chat/history/",
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
            themeColor: "#4e8cff",
            logoUrl: ""
        };

        const baseApi = isLocal ? "http://localhost:8000" : "http://208.87.134.149:8003";

        // Get client IP first
        const clientIP = await getClientIP();

        if (!clientIP) {
            throw new Error("Client IP is not available");
        }

        const requestBody = {
            widget_id: widgetId,
            ip: clientIP,
            user_agent: navigator.userAgent,
        };

        const response = await fetch(`${baseApi}/chat/user-chat/`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            },
            body: JSON.stringify(requestBody),
        });

        if (!response.ok) throw new Error("Failed to initialize chat");

        const data = await response.json();

        // Store room ID immediately
        roomId = data.room_id;
        localStorage.setItem("chat_room_id", roomId);
        localStorage.setItem("chat_widget_id", widgetId);

        // Apply widget settings from backend
        const settings = data.widget?.settings || {};
        Object.assign(WIDGET_CONFIG, {
            themeColor: settings.primaryColor || WIDGET_CONFIG.themeColor,
            logoUrl: settings.logo || WIDGET_CONFIG.logoUrl,
            position: settings.position || WIDGET_CONFIG.position,
            enableAttentionGrabber: settings.enableAttentionGrabber || false,
            attentionGrabber: settings.attentionGrabber || "",
            chatTitle: settings.name || WIDGET_CONFIG.chatTitle,
            placeholder: settings.placeholder || WIDGET_CONFIG.placeholder,
            is_active: data.widget?.is_active ?? settings.is_active ?? true
        });

        console.log("✅ Chat initialized with room:", roomId);
        console.log("🔧 Widget active status:", WIDGET_CONFIG.is_active);

        // Check if widget is active before rendering
        if (WIDGET_CONFIG.is_active === false) {
            console.log("Widget is not active, not rendering");
            return;
        }

        // Create widget container
        const widgetContainer = document.createElement("div");
        widgetContainer.id = "chat-widget";
        document.body.appendChild(widgetContainer);

        // Define bubble position before loading CSS/HTML
        const bubblePosition = WIDGET_CONFIG.position === "left" ? "left" : "right";
        const windowPosition = WIDGET_CONFIG.position === "left" ? "left" : "right";

        const attentionGrabberHTML = WIDGET_CONFIG.enableAttentionGrabber && WIDGET_CONFIG.attentionGrabber
            ? `<img src="${WIDGET_CONFIG.attentionGrabber}" alt="Attention Grabber" style="width: 100px; margin-bottom: 8px; display: block;" />`
            : "";

        // Load CSS and HTML
        async function loadCSS() {
            const cssResponse = await fetch('http://localhost:8000/static/css/chat_widget.css');
            const cssText = await cssResponse.text();

            const processedCSS = cssText
                .replace(/\${WIDGET_CONFIG\.themeColor}/g, WIDGET_CONFIG.themeColor)
                .replace(/\${WIDGET_CONFIG\.bottomOffset}/g, WIDGET_CONFIG.bottomOffset)
                .replace(/\${WIDGET_CONFIG\.sideOffset}/g, WIDGET_CONFIG.sideOffset)
                .replace(/\${WIDGET_CONFIG\.bubbleSize}/g, WIDGET_CONFIG.bubbleSize)
                .replace(/\${parseInt\(WIDGET_CONFIG\.bubbleSize\) - 20}/g, parseInt(WIDGET_CONFIG.bubbleSize) - 20)
                .replace(/\${parseInt\(WIDGET_CONFIG\.bottomOffset\) \+ parseInt\(WIDGET_CONFIG\.bubbleSize\) \+ 10}/g, parseInt(WIDGET_CONFIG.bottomOffset) + parseInt(WIDGET_CONFIG.bubbleSize) + 10)
                .replace(/\${WIDGET_CONFIG\.windowWidth}/g, WIDGET_CONFIG.windowWidth)
                .replace(/\${WIDGET_CONFIG\.windowHeight}/g, WIDGET_CONFIG.windowHeight)
                .replace(/\${bubblePosition}/g, bubblePosition)
                .replace(/\${windowPosition}/g, windowPosition);

            const styleElement = document.createElement('style');
            styleElement.textContent = processedCSS;
            document.head.appendChild(styleElement);
        }

        async function loadHTML() {
            const htmlResponse = await fetch('http://localhost:8000/static/html/chat-widget.html');
            const htmlText = await htmlResponse.text();

            return htmlText
                .replace(/\${attentionGrabberHTML}/g, attentionGrabberHTML)
                .replace(/\${WIDGET_CONFIG\.logoUrl}/g, WIDGET_CONFIG.logoUrl)
                .replace(/\${WIDGET_CONFIG\.chatTitle}/g, WIDGET_CONFIG.chatTitle)
                .replace(/\${WIDGET_CONFIG\.placeholder}/g, WIDGET_CONFIG.placeholder)
                .replace(/\${bubblePosition}/g, bubblePosition);
        }

        await loadCSS();
        const processedHTML = await loadHTML();
        widgetContainer.innerHTML = processedHTML;

        // Initialize DOM elements after HTML is loaded
        const elements = {
            muteToggle: document.getElementById("mute-toggle"),
            emojiPickerContainer: document.getElementById("emoji-picker"),
            chatBubble: document.getElementById("chat-bubble"),
            chatWindow: document.getElementById("chat-window"),
            emojiButton: document.getElementById("emoji-button"),
            input: document.getElementById("chat-input"),
            sendBtn: document.getElementById("send-btn"),
            formSubmit: document.getElementById("form-submit"),
            fileInput: document.getElementById("file-input"),
            removeFileBtn: document.getElementById("remove-file"),
            filePreviewContainer: document.getElementById("file-preview-container"),
            filePreviewName: document.getElementById("file-preview-name"),
            messagesDiv: document.getElementById("chat-messages"),
            formDiv: document.getElementById("chat-form"),
            footer: document.getElementById("chat-footer"),
            nameInput: document.getElementById("form-name"),
            emailInput: document.getElementById("form-email")
        };

        // Initialize AudioContext
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

        // Add history controls
        function addHistoryControls() {
            if (document.querySelector('.history-controls')) return;

            const historyControls = document.createElement('div');
            historyControls.className = 'history-controls';
            historyControls.style.display = 'none';
            
            const label = document.createElement('span');
            label.textContent = 'Load history:';
            label.className = 'history-label';
            
            const select = document.createElement('select');
            select.className = 'history-select';
            
            Object.entries(historyOptions).forEach(([value, text]) => {
                const option = document.createElement('option');
                option.value = value;
                option.textContent = text;
                if (value === historyLimit) option.selected = true;
                select.appendChild(option);
            });
            
            select.addEventListener('change', (e) => {
                historyLimit = e.target.value;
                localStorage.setItem('chat_history_limit', historyLimit);
                loadChatHistory();
            });
            
            const toggleBtn = document.createElement('button');
            toggleBtn.className = 'history-toggle';
            toggleBtn.innerHTML = '⚙️';
            toggleBtn.title = 'History settings';
            toggleBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                historyControls.style.display = historyControls.style.display === 'none' ? 'flex' : 'none';
            });
            
            historyControls.appendChild(label);
            historyControls.appendChild(select);
            
            const chatHeader = document.querySelector('.chat-header');
            if (chatHeader) {
                chatHeader.appendChild(toggleBtn);
                chatHeader.appendChild(historyControls);
            }

            const style = document.createElement('style');
            style.textContent = `
                .history-controls {
                    display: none;
                    align-items: center;
                    gap: 8px;
                    padding: 8px;
                    background: #f5f5f5;
                    border-radius: 4px;
                    position: absolute;
                    right: 40px;
                    top: 10px;
                    z-index: 100;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                }
                .history-label {
                    font-size: 12px;
                    color: #666;
                }
                .history-select {
                    padding: 4px;
                    border-radius: 4px;
                    border: 1px solid #ccc;
                    font-size: 12px;
                }
                .history-toggle {
                    background: none;
                    border: none;
                    cursor: pointer;
                    font-size: 16px;
                    padding: 4px;
                    position: absolute;
                    right: 10px;
                    top: 10px;
                }
                .history-toggle:hover {
                    opacity: 0.8;
                }
            `;
            document.head.appendChild(style);
        }

        // Initialize widget behavior
        function initializeWidgetBehavior() {
            console.log("🔧 initializeWidgetBehavior() called");

            if (elements.chatWindow) {
                elements.chatWindow.style.display = "none";
                widgetState.isOpen = false;
                console.log("✅ Widget closed on initialization");
            }

            setTimeout(() => {
                console.log("⏰ Showing notification badge after 2 seconds");
                showNotificationBadge();
            }, 2000);
        }

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

        function hideNotificationBadge() {
            console.log("🔕 hideNotificationBadge() called");
            const notificationBadge = document.querySelector(".notification-badge");
            if (notificationBadge) {
                notificationBadge.classList.remove("show");
                console.log("✅ Notification badge hidden");
            }
        }

        // Set up mute toggle if element exists
        if (elements.muteToggle) {
            elements.muteToggle.textContent = notificationEnabled ? "🔊" : "🔇";
            elements.muteToggle.addEventListener("click", () => {
                notificationEnabled = !notificationEnabled;
                elements.muteToggle.textContent = notificationEnabled ? "🔊" : "🔇";
            });
        }

        // Set up emoji picker
        if (elements.emojiPickerContainer) {
            const emojiScript = document.createElement("script");
            emojiScript.src = "https://cdn.jsdelivr.net/npm/emoji-picker-element@^1/index.js";
            emojiScript.type = "module";
            document.head.appendChild(emojiScript);

            emojiScript.onload = () => {
                const emojiPicker = document.createElement("emoji-picker");
                elements.emojiPickerContainer.appendChild(emojiPicker);
                emojiPicker.addEventListener("emoji-click", (event) => {
                    if (elements.input) {
                        elements.input.value += event.detail.unicode;
                        elements.emojiPickerContainer.style.display = "none";
                        notifyTyping();
                    }
                });
            };
        }

        // Set up chat bubble toggle
        if (elements.chatBubble && elements.chatWindow) {
            elements.chatBubble.addEventListener("click", (event) => {
                event.stopPropagation();
                hideNotificationBadge();
                const isVisible = elements.chatWindow.style.display === "flex";
                elements.chatWindow.style.display = isVisible ? "none" : "flex";
                widgetState.isOpen = !isVisible;
                console.log(`Chat widget ${isVisible ? 'closed' : 'opened'}`);
                
                // When opening, mark all messages as seen
                if (!isVisible && socket && socket.readyState === WebSocket.OPEN) {
                    markAllMessagesAsSeen();
                }
            });
        }

        // WebSocket connection with reconnection and history support
        function connectWebSocket(roomId) {
            if (socket && socket.readyState === WebSocket.OPEN) {
                console.log("WebSocket already connected");
                return;
            }

            if (socket) {
                socket.close();
            }

            console.log("🔌 Connecting WebSocket for room:", roomId);
            socket = new WebSocket(`${WIDGET_CONFIG.wsUrl}${roomId}/`);

            socket.onopen = async () => {
                console.log("✅ WebSocket connected successfully");
                reconnectAttempts = 0;
                updateConnectionStatus(true);
                widgetState.connectionEstablished = true;
                
                // Send initial presence notification
                socket.send(JSON.stringify({
                    type: "presence",
                    status: "online",
                    sender: "User"
                }));

                // Load chat history if not already loaded
                if (!chatHistoryLoaded) {
                    await loadChatHistory();
                    chatHistoryLoaded = true;
                }
            };

            socket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    console.log("📩 Received WebSocket message:", data);
                    handleIncomingMessage(data);
                } catch (e) {
                    console.error("Failed to parse WebSocket message:", e);
                }
            };

            socket.onclose = (event) => {
                console.log("🔌 WebSocket disconnected, code:", event.code, "reason:", event.reason);
                updateConnectionStatus(false);
                widgetState.connectionEstablished = false;

                if (widgetState.isOpen && elements.chatWindow && elements.chatWindow.style.display === "flex") {
                    appendSystemMessage("Disconnected. Attempting to reconnect...");
                }

                // Attempt reconnection
                if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
                    const delay = RECONNECT_DELAY * Math.pow(2, reconnectAttempts);
                    console.log(`⏳ Attempting to reconnect in ${delay/1000} seconds...`);
                    setTimeout(() => {
                        reconnectAttempts++;
                        connectWebSocket(roomId);
                    }, delay);
                } else {
                    console.log("❌ Max reconnection attempts reached");
                    appendSystemMessage("Connection lost. Please refresh the page.");
                }
            };

            socket.onerror = (error) => {
                console.error("❌ WebSocket error:", error);
                updateConnectionStatus(false);
                widgetState.connectionEstablished = false;

                if (widgetState.isOpen && elements.chatWindow && elements.chatWindow.style.display === "flex") {
                    appendSystemMessage("Chat error occurred.");
                }
            };
        }

        // Load chat history from server
        async function loadChatHistory() {
            try {
                console.log(`📜 Loading chat history (limit: ${historyLimit})...`);
                
                const loadingId = `loading-${Date.now()}`;
                appendSystemMessage("Loading chat history...", loadingId);
                
                const response = await fetch(WIDGET_CONFIG.historyUrl, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    body: JSON.stringify({
                        room_id: roomId,
                        widget_id: localStorage.getItem("chat_widget_id"),
                        limit: historyLimit === 'full' ? 0 : parseInt(historyLimit)
                    }),
                });

                if (!response.ok) {
                    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
                    throw new Error(error.error || 'Failed to load chat history');
                }

                const history = await response.json();
                
                // Remove loading indicator
                const loadingElement = document.getElementById(`msg-${loadingId}`);
                if (loadingElement) loadingElement.remove();
                
                if (history.messages && history.messages.length > 0) {
                    // Clear existing non-system messages
                    const existingMessages = elements.messagesDiv.querySelectorAll('.message:not(.system)');
                    existingMessages.forEach(msg => msg.remove());

                    // Add history messages
                    history.messages.forEach(msg => {
                        appendMessage(
                            msg.sender,
                            msg.message,
                            msg.file_url,
                            msg.file_name,
                            msg.sender === "User" ? "user" : msg.sender === "System" ? "system" : "agent",
                            msg.message_id,
                            msg.status || "delivered",
                            msg.timestamp
                        );

                        // Track user messages that need seen status updates
                        if (msg.sender === "User") {
                            sentMessages[msg.message_id] = true;
                        }
                    });

                    // Show history info
                    // appendSystemMessage(`Loaded ${history.returned_messages} of ${history.total_messages} messages`);
                    
                    // Mark messages as seen if chat is open
                    if (widgetState.isOpen) {
                        markAllMessagesAsSeen();
                    }
                } else {
                    appendSystemMessage("No chat history found");
                }
            } catch (error) {
                console.error("Error loading chat history:", error);
                appendSystemMessage("Could not load chat history: " + error.message);
            }
        }

        function updateConnectionStatus(connected) {
            const statusElements = document.querySelectorAll(".connection-status, .status-indicator");
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

        // Message handling functions
       function handleIncomingMessage(data) {
            if (!elements.messagesDiv || !elements.formDiv || !elements.footer) return;

            console.log("📩 Incoming message:", data);

            // Form trigger keywords (case-insensitive)
            const FORM_TRIGGER_KEYWORDS = [
                "fill the following information",
                "provide your details",
                "enter your name and email",
                "we need your contact information",
                "please share your details"
            ];

            // --- Enhanced Form Trigger Logic ---
            const isFormTriggerMessage = data.message && 
                FORM_TRIGGER_KEYWORDS.some(keyword => 
                    data.message.toLowerCase().includes(keyword.toLowerCase())
                );
            
            const shouldShowForm = (data.show_form && data.form_type === "user_info") || isFormTriggerMessage;

            if (shouldShowForm) {
                elements.formDiv.style.display = "block";
                elements.footer.style.display = "none";
                
                // Show the trigger message (unless it's a hidden system command)
                if (data.message && !data.hidden_trigger) {
                    appendMessage(
                        data.sender || "System",
                        data.message,
                        null,
                        null,
                        "agent",
                        data.message_id || `sys-${Date.now()}`,
                        "delivered",
                        data.timestamp
                    );
                }
                elements.messagesDiv.scrollTop = elements.messagesDiv.scrollHeight;
                return;
            }

            // Handle form submission confirmation
            if (data.form_data_received) {
                elements.formDiv.style.display = "none";
                elements.footer.style.display = "flex";
                appendSystemMessage("Thank you for your information!");
                return;
            }

            // Handle typing indicators
            if (data.typing && data.sender !== "User") {
                const typingId = `typing-${data.sender}`;
                if (!document.getElementById(typingId)) {
                    const typingElement = document.createElement("div");
                    typingElement.id = typingId;
                    typingElement.className = "message system";
                    typingElement.innerHTML = `<i>${sanitizeHTML(data.sender)} is typing...</i>`;
                    elements.messagesDiv.appendChild(typingElement);
                    elements.messagesDiv.scrollTop = elements.messagesDiv.scrollHeight;
                    setTimeout(() => {
                        const el = document.getElementById(typingId);
                        if (el) el.remove();
                    }, 2000);
                }
                return;
            }

            // Handle message seen status
            if (data.status === "seen" && sentMessages[data.message_id]) {
                updateMessageStatus(data.message_id, data.status);
                return;
            }

            // Handle errors
            if (data.error) {
                appendSystemMessage(`Error: ${sanitizeHTML(data.error)}`);
                return;
            }

            // Handle agent assignment
            if (data.type === "agent_assigned") {
                appendSystemMessage(`Agent ${data.agent_name} has joined the chat`);
                return;
            }

            // Handle suggested replies
            if (data.suggested_replies && data.suggested_replies.length > 0) {
                showSuggestedReplies(data.suggested_replies);
            }

            // Handle regular messages
            if (data.message || data.file_url) {
                appendMessage(
                    data.sender,
                    data.message,
                    data.file_url,
                    data.file_name,
                    data.sender === "User" ? "user" : data.sender === "System" ? "system" : "agent",
                    data.message_id,
                    data.sender === "User" ? "delivered" : "delivered",
                    data.timestamp
                );
                
                if (data.sender !== "User") {
                    markMessageAsSeen(data.message_id);
                    playNotificationSound();
                }
            }
        }

        
        function appendMessage(sender, message, fileUrl, fileName, className, messageId, status, timestamp) {
            if (!elements.messagesDiv) return;

            // Check if message already exists
            if (document.getElementById(`msg-${messageId}`)) {
                updateMessageStatus(messageId, status, message, fileUrl, fileName);
                return;
            }

            const div = document.createElement("div");
            div.className = `message ${className}`;
            div.id = `msg-${messageId}`;
            
            // Format timestamp
            const messageTime = timestamp ? new Date(timestamp) : new Date();
            const timeString = messageTime.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
            const ticks = sender === "User" ? getTicks(status) : "";

            let content = message ? sanitizeHTML(message) : "";
            if (fileUrl) {
                const isImage = /\.(jpg|jpeg|png|gif)$/i.test(fileName);
                content += `<div class="file-preview">${
                    isImage 
                        ? `<img src="${sanitizeHTML(fileUrl)}" alt="${sanitizeHTML(fileName)}" />`
                        : `<a href="${sanitizeHTML(fileUrl)}" target="_blank" rel="noopener noreferrer">${sanitizeHTML(fileName)}</a>`
                }</div>`;
            }

            div.innerHTML = `${content}<span class="timestamp">${timeString} ${ticks}</span>`;
            elements.messagesDiv.appendChild(div);
            elements.messagesDiv.scrollTop = elements.messagesDiv.scrollHeight;

            if (sender === "User") {
                sentMessages[messageId] = true;
            }
        }

        function appendSystemMessage(message, messageId = null) {
            const id = messageId || `sys-${Date.now()}`;
            appendMessage("System", message, null, null, "system", id, "delivered");
        }

        function updateMessageStatus(messageId, status, message = null, fileUrl = null, fileName = null) {
            const messageDiv = document.getElementById(`msg-${messageId}`);
            if (!messageDiv) return;

            const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
            let content = message !== null ? sanitizeHTML(message) : messageDiv.innerHTML.split('<span class="timestamp">')[0];
            
            if (fileUrl) {
                const isImage = /\.(jpg|jpeg|png|gif)$/i.test(fileName);
                content += `<div class="file-preview">${
                    isImage 
                        ? `<img src="${sanitizeHTML(fileUrl)}" alt="${sanitizeHTML(fileName)}" />`
                        : `<a href="${sanitizeHTML(fileUrl)}" target="_blank" rel="noopener noreferrer">${sanitizeHTML(fileName)}</a>`
                }</div>`;
            }

            messageDiv.innerHTML = `${content}<span class="timestamp">${time} ${getTicks(status)}</span>`;
            if (elements.messagesDiv) elements.messagesDiv.scrollTop = elements.messagesDiv.scrollHeight;
        }

        function getTicks(status) {
            switch (status) {
                case "sent": return '<span class="tick">✓</span>';
                case "delivered": return '<span class="tick">✓✓</span>';
                case "seen": return '<span class="tick blue">✓✓</span>';
                default: return "";
            }
        }

        function showSuggestedReplies(replies) {
            if (!elements.messagesDiv || !replies.length) return;
            
            const container = document.createElement("div");
            container.className = "suggested-replies";
            
            replies.forEach(reply => {
                const button = document.createElement("button");
                button.textContent = reply;
                button.addEventListener("click", () => {
                    if (elements.input) {
                        elements.input.value = reply;
                        sendMessage();
                    }
                });
                container.appendChild(button);
            });
            
            elements.messagesDiv.appendChild(container);
            elements.messagesDiv.scrollTop = elements.messagesDiv.scrollHeight;
        }

        // Message sending
        function sendMessage() {
            if (!elements.input || !socket) return;
            
            const messageText = elements.input.value.trim();
            if (!messageText && !elements.fileInput.files[0]) return;

            // If we have a file, upload it first
            if (elements.fileInput.files[0]) {
                uploadFile();
                return;
            }

            const messageId = generateMessageId();
            
            socket.send(JSON.stringify({
                message: messageText,
                sender: "User",
                message_id: messageId,
            }));
            
            appendMessage("User", messageText, null, null, "user", messageId, "sent");
            elements.input.value = "";
            
            // Reset typing state
            widgetState.isTyping = false;
            sendTypingNotification(false);
        }

        if (elements.input) {
            elements.input.addEventListener("keypress", (e) => {
                if (e.key === "Enter" && (elements.input.value.trim() || elements.fileInput.files[0]) && socket) {
                    sendMessage();
                }
            });
        }

        if (elements.sendBtn) {
            elements.sendBtn.addEventListener("click", sendMessage);
        }

        // Typing notification
        let typingTimeout;
        function sendTypingNotification(isTyping) {
            if (!socket || !elements.input) return;

            const content = elements.input.value.trim();
            socket.send(JSON.stringify({
                typing: isTyping,
                content: content,
                sender: "User",
            }));
        }

        function notifyTyping() {
            const now = Date.now();
            const isTyping = elements.input.value.trim().length > 0;
            
            // Only send notification if state changed or it's been more than 2 seconds
            if (isTyping !== widgetState.isTyping || now - widgetState.lastTypingTime > 2000) {
                widgetState.isTyping = isTyping;
                widgetState.lastTypingTime = now;
                sendTypingNotification(isTyping);
            }

            clearTimeout(typingTimeout);
            typingTimeout = setTimeout(() => {
                widgetState.isTyping = false;
                sendTypingNotification(false);
            }, 2000);
        }
        
        if (elements.input) {
            elements.input.addEventListener("input", notifyTyping);
        }

        // Form submission
        if (elements.formSubmit) {
            elements.formSubmit.addEventListener("click", () => {
                const name = elements.nameInput?.value.trim() || "";
                const email = elements.emailInput?.value.trim() || "";

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
                socket.send(JSON.stringify({
                    form_data: { name, email },
                    sender: "User",
                    message_id: messageId,
                }));

                appendSystemMessage("Information submitted successfully!");
            });
        }

        // File upload handling
        if (elements.fileInput) {
            elements.fileInput.addEventListener("change", (e) => {
                const file = e.target.files[0];
                if (!file) return;

                const maxSize = 10 * 1024 * 1024; // 10MB
                if (file.size > maxSize) {
                    appendSystemMessage("File size too large. Maximum size is 10MB.");
                    elements.fileInput.value = "";
                    return;
                }

                if (elements.filePreviewContainer && elements.filePreviewName) {
                    elements.filePreviewName.textContent = file.name;
                    elements.filePreviewContainer.style.display = "flex";
                }
            });
        }

        if (elements.removeFileBtn && elements.filePreviewContainer && elements.fileInput) {
            elements.removeFileBtn.addEventListener("click", () => {
                elements.fileInput.value = "";
                elements.filePreviewContainer.style.display = "none";
            });
        }

        function uploadFile() {
            if (!elements.fileInput || !elements.fileInput.files[0] || !socket) return;

            const file = elements.fileInput.files[0];
            const messageId = generateMessageId();
            const formData = new FormData();
            formData.append("file", file);
            formData.append("room_id", roomId);
            formData.append("message_id", messageId);

            fetch(`${WIDGET_CONFIG.fileUploadUrl}`, {
                method: "POST",
                body: formData,
            })
                .then((response) => {
                    if (!response.ok) throw new Error("Failed to upload file");
                    return response.json();
                })
                .then((data) => {
                    socket.send(JSON.stringify({
                        file_url: data.file_url,
                        file_name: file.name,
                        sender: "User",
                        message_id: messageId,
                    }));
                    appendMessage("User", null, data.file_url, file.name, "user", messageId, "sent");
                    elements.fileInput.value = "";
                    if (elements.filePreviewContainer) elements.filePreviewContainer.style.display = "none";
                })
                .catch((error) => {
                    console.error("Error uploading file:", error);
                    appendSystemMessage("Failed to upload file. Please try again.");
                });
        }

        // Mark message as seen
        function markMessageAsSeen(messageId) {
            if (!socket || socket.readyState !== WebSocket.OPEN) return;
            
            socket.send(JSON.stringify({
                status: "seen",
                message_id: messageId,
                sender: "User",
            }));
        }

        // Mark all messages as seen
        function markAllMessagesAsSeen() {
            if (!socket || socket.readyState !== WebSocket.OPEN) return;
            
            Object.keys(sentMessages).forEach(messageId => {
                socket.send(JSON.stringify({
                    status: "seen",
                    message_id: messageId,
                    sender: "User",
                }));
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
                gainNode.gain.linearRampToValueAtTime(0.3, audioContext.currentTime + 0.01);
                gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.3);

                oscillator.start(audioContext.currentTime);
                oscillator.stop(audioContext.currentTime + 0.3);
            } catch (e) {
                console.error("Error playing notification sound:", e);
            }
        }

        // Initialize widget behavior
        initializeWidgetBehavior();
        addHistoryControls();

        // Auto-connect WebSocket
        if (roomId) {
            setTimeout(() => {
                console.log("🚀 Auto-connecting WebSocket...");
                connectWebSocket(roomId);
            }, 1000);
        }

    } catch (err) {
        console.error("Error initializing chat:", err);
        // If we have elements but initialization failed, show error
        if (document.getElementById("chat-widget")) {
            appendSystemMessage("Failed to initialize chat. Please refresh the page.");
        }
    }
}

// Start the widget when DOM is ready
document.addEventListener("DOMContentLoaded", initializeChatWidget);

// Clean up on page unload
window.addEventListener("beforeunload", () => {
    if (socket) {
        // Send offline status before closing
        if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({
                type: "presence",
                status: "offline",
                sender: "User"
            }));
        }
        socket.close();
    }
    if (audioContext) {
        audioContext.close();
    }
});

// // Initialize all global variables at the top
// let audioContext = null;
// let socket = null;
// let notificationEnabled = true;
// const sentMessages = {};
// let roomId = null;
// let cachedClientIP = null;

// // Widget state management
// let widgetState = {
//     isOpen: false,
//     notificationShown: false,
//     connectionEstablished: false,
//     pageLoadTime: Date.now(),
// };

// // Function to get client IP
// async function getClientIP() {
//     try {
//         const response = await fetch("https://api.ipify.org?format=json");
//         const data = await response.json();
//         if (data && data.ip) return data.ip;
//         throw new Error("Invalid IP data");
//     } catch (error) {
//         console.warn("Primary IP fetch failed:", error);
//         try {
//             const response = await fetch("https://ipapi.co/ip/");
//             const ip = await response.text();
//             return ip.trim();
//         } catch (fallbackError) {
//             console.warn("Fallback IP fetch failed:", fallbackError);
//             return null;
//         }
//     }
// }

// document.addEventListener("DOMContentLoaded", async function () {
//     // Initialize DOM elements after widget is created
//     function initializeDOMElements() {
//         return {
//             muteToggle: document.getElementById("mute-toggle"),
//             emojiPickerContainer: document.getElementById("emoji-picker"),
//             chatBubbleContainer: document.getElementById("chat-bubble-container"),
//             chatBubble: document.getElementById("chat-bubble"),
//             chatWindow: document.getElementById("chat-window"),
//             emojiButton: document.getElementById("emoji-button"),
//             input: document.getElementById("chat-input"),
//             sendBtn: document.getElementById("send-btn"),
//             formSubmit: document.getElementById("form-submit"),
//             fileInput: document.getElementById("file-input"),
//             removeFileBtn: document.getElementById("remove-file"),
//             filePreviewContainer: document.getElementById("file-preview-container"),
//             filePreviewName: document.getElementById("file-preview-name"),
//             messagesDiv: document.getElementById("chat-messages"),
//             formDiv: document.getElementById("chat-form"),
//             footer: document.getElementById("chat-footer")
//         };
//     }

//     let scriptSrc;
//     let scriptTag;

//     if (document.currentScript && document.currentScript.src) {
//         scriptSrc = document.currentScript.src;
//         scriptTag = document.currentScript;
//     } else {
//         const scripts = document.getElementsByTagName("script");
//         scriptTag = Array.from(scripts).find((s) => s.src.includes("chat_widget2.js"));
//         if (scriptTag) {
//             scriptSrc = scriptTag.src;
//         } else {
//             console.error("Unable to find chat_widget2.js script tag");
//             return;
//         }
//     }

//     const urlParams = new URLSearchParams(scriptSrc.split("?")[1]);
//     const widgetId = urlParams.get("widget_id");

//     if (!widgetId) {
//         console.error("Widget ID not found in script URL");
//         return;
//     }

//     // Widget configuration
//     console.log("Initializing chat widget with ID:", widgetId);
//     const isLocal =
//         window.location.hostname === "localhost" ||
//         window.location.hostname === "127.0.0.1";

//     const WIDGET_CONFIG = {
//         apiUrl: isLocal
//             ? "http://localhost:8000/chat/user-chat/"
//             : "http://208.87.134.149:8003/chat/user-chat/",
//         wsUrl: isLocal
//             ? "ws://localhost:8000/ws/chat/"
//             : "ws://208.87.134.149:8003/ws/chat/",
//         fileUploadUrl: isLocal
//             ? "http://localhost:8000/chat/user-chat/upload-file/"
//             : "http://208.87.134.149:8003/chat/user-chat/upload-file/",
//         position: "right",
//         chatTitle: "Chat with Us",
//         placeholder: "Type a message...",
//         bubbleSize: "100",
//         windowWidth: "340",
//         windowHeight: "400",
//         bottomOffset: "20",
//         sideOffset: "20",
//         enableAttentionGrabber: false,
//         attentionGrabber: "",
//         is_active: false,
//     };

//     const baseApi = isLocal
//         ? "http://localhost:8000"
//         : "http://208.87.134.149:8003";

//     try {
//         // Get client IP first
//         const clientIP = await getClientIP();

//         if (!clientIP) {
//             throw new Error("Client IP is not available");
//         }

//         const requestBody = {
//             widget_id: widgetId,
//             ip: clientIP,
//             user_agent: navigator.userAgent,
//         };

//         const response = await fetch(`${baseApi}/chat/user-chat/`, {
//             method: "POST",
//             headers: {
//                 "Content-Type": "application/json",
//                 "X-Requested-With": "XMLHttpRequest",
//             },
//             body: JSON.stringify(requestBody),
//         });

//         if (!response.ok) throw new Error("Failed to initialize chat");

//         const data = await response.json();

//         // Store room ID immediately
//         roomId = localStorage.getItem("chat_room_id") || null;
//         roomId = data.room_id;
//         localStorage.setItem("chat_room_id", roomId);

//         // Apply widget settings
//         const settings = data.widget?.settings || {};
//         WIDGET_CONFIG.themeColor = settings.primaryColor || WIDGET_CONFIG.themeColor;
//         WIDGET_CONFIG.logoUrl = settings.logo || WIDGET_CONFIG.logoUrl;
//         WIDGET_CONFIG.position = settings.position || WIDGET_CONFIG.position;
//         WIDGET_CONFIG.enableAttentionGrabber = settings.enableAttentionGrabber || false;
//         WIDGET_CONFIG.attentionGrabber = settings.attentionGrabber || "";
//         WIDGET_CONFIG.chatTitle = name || WIDGET_CONFIG.chatTitle;
//         WIDGET_CONFIG.placeholder = settings.placeholder || WIDGET_CONFIG.placeholder;
//         WIDGET_CONFIG.is_active = data.widget?.is_active ?? settings.is_active ?? true;

//         console.log("✅ Chat initialized with room:", roomId);
//         console.log("📍 User location:", data.user_location);
//         console.log("🔧 Widget active status:", WIDGET_CONFIG.is_active);
//         console.log("🔧 Full widget data:", data.widget);

//         // Check if widget is active before rendering
//         if (WIDGET_CONFIG.is_active === false) {
//             console.log("Widget is not active, not rendering");
//             return;
//         }

//         // Mark connection as ready for WebSocket
//         widgetState.connectionEstablished = true;

//         // Create widget container
//         const widgetContainer = document.createElement("div");
//         widgetContainer.id = "chat-widget";
//         document.body.appendChild(widgetContainer);

//         // Define bubble position before loading CSS/HTML
//         const bubblePosition = WIDGET_CONFIG.position === "left" ? "left" : "right";
//         const windowPosition = WIDGET_CONFIG.position === "left" ? "left" : "right";

//         const attentionGrabberHTML =
//             WIDGET_CONFIG.enableAttentionGrabber && WIDGET_CONFIG.attentionGrabber
//                 ? `<img src="${WIDGET_CONFIG.attentionGrabber}" alt="Attention Grabber" style="width: 100px; margin-bottom: 8px; display: block;" />`
//                 : "";

//         // Load CSS and HTML
//         async function loadCSS() {
//             const cssResponse = await fetch('http://localhost:8000/static/css/chat_widget.css');
//             const cssText = await cssResponse.text();

//             const processedCSS = cssText
//                 .replace(/\${WIDGET_CONFIG\.themeColor}/g, WIDGET_CONFIG.themeColor)
//                 .replace(/\${WIDGET_CONFIG\.bottomOffset}/g, WIDGET_CONFIG.bottomOffset)
//                 .replace(/\${WIDGET_CONFIG\.sideOffset}/g, WIDGET_CONFIG.sideOffset)
//                 .replace(/\${WIDGET_CONFIG\.bubbleSize}/g, WIDGET_CONFIG.bubbleSize)
//                 .replace(/\${parseInt\(WIDGET_CONFIG\.bubbleSize\) - 20}/g, parseInt(WIDGET_CONFIG.bubbleSize) - 20)
//                 .replace(/\${parseInt\(WIDGET_CONFIG\.bottomOffset\) \+ parseInt\(WIDGET_CONFIG\.bubbleSize\) \+ 10}/g, parseInt(WIDGET_CONFIG.bottomOffset) + parseInt(WIDGET_CONFIG.bubbleSize) + 10)
//                 .replace(/\${WIDGET_CONFIG\.windowWidth}/g, WIDGET_CONFIG.windowWidth)
//                 .replace(/\${WIDGET_CONFIG\.windowHeight}/g, WIDGET_CONFIG.windowHeight)
//                 .replace(/\${bubblePosition}/g, bubblePosition)
//                 .replace(/\${windowPosition}/g, windowPosition);

//             const styleElement = document.createElement('style');
//             styleElement.textContent = processedCSS;
//             document.head.appendChild(styleElement);
//         }

//         async function loadHTML() {
//             const htmlResponse = await fetch('http://localhost:8000/static/html/chat-widget.html');
//             const htmlText = await htmlResponse.text();

//             return htmlText
//                 .replace(/\${attentionGrabberHTML}/g, attentionGrabberHTML)
//                 .replace(/\${WIDGET_CONFIG\.logoUrl}/g, WIDGET_CONFIG.logoUrl)
//                 .replace(/\${WIDGET_CONFIG\.chatTitle}/g, WIDGET_CONFIG.chatTitle)
//                 .replace(/\${WIDGET_CONFIG\.placeholder}/g, WIDGET_CONFIG.placeholder)
//                 .replace(/\${bubblePosition}/g, bubblePosition);
//         }

//         await loadCSS();
//         const processedHTML = await loadHTML();
//         widgetContainer.innerHTML = processedHTML;

//         // Initialize DOM elements after HTML is loaded
//         const {
//             muteToggle,
//             emojiPickerContainer,
//             chatBubble,
//             chatWindow,
//             emojiButton,
//             input,
//             sendBtn,
//             formSubmit,
//             fileInput,
//             removeFileBtn,
//             filePreviewContainer,
//             filePreviewName,
//             messagesDiv,
//             formDiv,
//             footer
//         } = initializeDOMElements();

//         // Initialize AudioContext
//         function initAudioContext() {
//             if (audioContext) return;
//             try {
//                 audioContext = new (window.AudioContext || window.webkitAudioContext)();
//                 console.log("Audio context initialized");
//             } catch (e) {
//                 console.error("Web Audio API is not supported in this browser", e);
//             }
//         }
//         initAudioContext();

//         // Initialize widget behavior
//         function initializeWidgetBehavior() {
//             console.log("🔧 initializeWidgetBehavior() called");

//             if (chatWindow) {
//                 chatWindow.style.display = "none";
//                 widgetState.isOpen = false;
//                 console.log("✅ Widget closed on initialization");
//             }

//             setTimeout(() => {
//                 console.log("⏰ Showing notification badge after 2 seconds");
//                 showNotificationBadge();
//             }, 2000);
//         }

//         function showNotificationBadge() {
//             console.log("🔔 showNotificationBadge() called");

//             if (widgetState.notificationShown) {
//                 console.log("ℹ️ Notification already shown");
//                 return;
//             }

//             const notificationBadge = document.querySelector(".notification-badge");
//             if (notificationBadge) {
//                 console.log("✅ Found notification badge, showing it");
//                 notificationBadge.classList.add("show");
//                 widgetState.notificationShown = true;
//                 console.log("🎉 Notification badge shown successfully!");
//             } else {
//                 console.error("❌ Notification badge not found");
//             }
//         }

//         function hideNotificationBadge() {
//             console.log("🔕 hideNotificationBadge() called");
//             const notificationBadge = document.querySelector(".notification-badge");
//             if (notificationBadge) {
//                 notificationBadge.classList.remove("show");
//                 console.log("✅ Notification badge hidden");
//             }
//         }

//         // Set up mute toggle if element exists
//         if (muteToggle) {
//             muteToggle.textContent = notificationEnabled ? "🔊" : "🔇";
//             muteToggle.addEventListener("click", () => {
//                 notificationEnabled = !notificationEnabled;
//                 muteToggle.textContent = notificationEnabled ? "🔊" : "🔇";
//             });
//         }

//         // Set up emoji picker
//         if (emojiPickerContainer) {
//             const emojiScript = document.createElement("script");
//             emojiScript.src = "https://cdn.jsdelivr.net/npm/emoji-picker-element@^1/index.js";
//             emojiScript.type = "module";
//             document.head.appendChild(emojiScript);

//             emojiScript.onload = () => {
//                 const emojiPicker = document.createElement("emoji-picker");
//                 emojiPickerContainer.appendChild(emojiPicker);
//                 emojiPicker.addEventListener("emoji-click", (event) => {
//                     if (input) {
//                         input.value += event.detail.unicode;
//                         emojiPickerContainer.style.display = "none";
//                         notifyTyping();
//                     }
//                 });
//             };
//         }

//         // Set up chat bubble toggle
//         if (chatBubble && chatWindow) {
//             chatBubble.addEventListener("click", (event) => {
//                 event.stopPropagation();
//                 hideNotificationBadge();
//                 const isVisible = chatWindow.style.display === "flex";
//                 chatWindow.style.display = isVisible ? "none" : "flex";
//                 widgetState.isOpen = !isVisible;
//                 console.log(`Chat widget ${isVisible ? 'closed' : 'opened'}`);
//             });
//         }

//         // WebSocket connection
//         function connectWebSocket(roomId) {
//             if (socket && socket.readyState === WebSocket.OPEN) {
//                 console.log("WebSocket already connected");
//                 return;
//             }

//             if (socket) {
//                 socket.close();
//             }

//             console.log("🔌 Connecting WebSocket for room:", roomId);
//             socket = new WebSocket(`${WIDGET_CONFIG.wsUrl}${roomId}/`);

//             socket.onopen = () => {
//                 console.log("✅ WebSocket connected successfully");
//                 updateConnectionStatus(true);
//                 widgetState.connectionEstablished = true;
//             };

//             socket.onmessage = (event) => {
//                 try {
//                     const data = JSON.parse(event.data);
//                     handleIncomingMessage(data);
//                 } catch (e) {
//                     console.error("Failed to parse WebSocket message:", e);
//                 }
//             };

//             socket.onclose = (event) => {
//                 console.log("🔌 WebSocket disconnected, code:", event.code, "reason:", event.reason);
//                 updateConnectionStatus(false);
//                 widgetState.connectionEstablished = false;

//                 if (widgetState.isOpen && chatWindow && chatWindow.style.display === "flex") {
//                     appendSystemMessage("Disconnected. Please refresh to reconnect.");
//                 }
//             };

//             socket.onerror = (error) => {
//                 console.error("❌ WebSocket error:", error);
//                 updateConnectionStatus(false);
//                 widgetState.connectionEstablished = false;

//                 if (widgetState.isOpen && chatWindow && chatWindow.style.display === "flex") {
//                     appendSystemMessage("Chat error occurred.");
//                 }
//             };
//         }

//         function updateConnectionStatus(connected) {
//             const statusElements = document.querySelectorAll(".connection-status, .status-indicator");
//             statusElements.forEach((element) => {
//                 if (connected) {
//                     element.classList.add("connected");
//                     element.classList.remove("disconnected");
//                 } else {
//                     element.classList.add("disconnected");
//                     element.classList.remove("connected");
//                 }
//             });
//         }

//         // Message handling functions
//         function handleIncomingMessage(data) {
//             if (!messagesDiv || !formDiv || !footer) return;

//             if (data.show_form && data.form_type === "user_info") {
//                 formDiv.style.display = "block";
//                 footer.style.display = "none";
//                 messagesDiv.scrollTop = messagesDiv.scrollHeight;
//                 return;
//             }

//             if (data.form_data_received) {
//                 formDiv.style.display = "none";
//                 footer.style.display = "flex";
//                 return;
//             }

//             if (data.typing && data.sender !== "User") {
//                 const typingId = `typing-${data.sender}`;
//                 if (!document.getElementById(typingId)) {
//                     const typingElement = document.createElement("div");
//                     typingElement.id = typingId;
//                     typingElement.className = "message system";
//                     typingElement.innerHTML = `<i>${sanitizeHTML(data.sender)} is typing...</i>`;
//                     messagesDiv.appendChild(typingElement);
//                     messagesDiv.scrollTop = messagesDiv.scrollHeight;
//                     setTimeout(() => {
//                         const el = document.getElementById(typingId);
//                         if (el) el.remove();
//                     }, 2000);
//                 }
//                 return;
//             }

//             if (data.status === "seen" && sentMessages[data.message_id]) {
//                 updateMessageStatus(data.message_id, data.status);
//                 return;
//             }

//             if (data.error) {
//                 appendSystemMessage(`Error: ${sanitizeHTML(data.error)}`);
//                 return;
//             }

//             if (data.message || data.file_url) {
//                 appendMessage(
//                     data.sender,
//                     data.message,
//                     data.file_url,
//                     data.file_name,
//                     data.sender === "User" ? "user" : data.sender === "System" ? "system" : "agent",
//                     data.message_id,
//                     data.sender === "User" ? "delivered" : "delivered"
//                 );
//                 if (data.sender !== "User") {
//                     socket.send(JSON.stringify({
//                         status: "seen",
//                         message_id: data.message_id,
//                         sender: "User",
//                     }));
//                     playNotificationSound();
//                 }
//             }
//         }

//         function appendMessage(sender, message, fileUrl, fileName, className, messageId, status) {
//             if (!messagesDiv) return;

//             if (document.getElementById(`msg-${messageId}`)) {
//                 updateMessageStatus(messageId, status, message, fileUrl, fileName);
//                 return;
//             }

//             const div = document.createElement("div");
//             div.className = `message ${className}`;
//             div.id = `msg-${messageId}`;
//             const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
//             const ticks = sender === "User" ? getTicks(status) : "";

//             let content = message ? sanitizeHTML(message) : "";
//             if (fileUrl) {
//                 const isImage = /\.(jpg|jpeg|png|gif)$/i.test(fileName);
//                 content += `<div class="file-preview">${
//                     isImage 
//                         ? `<img src="${sanitizeHTML(fileUrl)}" alt="${sanitizeHTML(fileName)}" />`
//                         : `<a href="${sanitizeHTML(fileUrl)}" target="_blank" rel="noopener noreferrer">${sanitizeHTML(fileName)}</a>`
//                 }</div>`;
//             }

//             div.innerHTML = `${content}<span class="timestamp">${time} ${ticks}</span>`;
//             messagesDiv.appendChild(div);
//             messagesDiv.scrollTop = messagesDiv.scrollHeight;

//             if (sender === "User") {
//                 sentMessages[messageId] = true;
//             }
//         }

//         function appendSystemMessage(message) {
//             appendMessage("System", message, null, null, "system", `sys-${Date.now()}`, "delivered");
//         }

//         function updateMessageStatus(messageId, status, message = null, fileUrl = null, fileName = null) {
//             const messageDiv = document.getElementById(`msg-${messageId}`);
//             if (!messageDiv) return;

//             const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
//             let content = message !== null ? sanitizeHTML(message) : messageDiv.innerHTML.split('<span class="timestamp">')[0];
            
//             if (fileUrl) {
//                 const isImage = /\.(jpg|jpeg|png|gif)$/i.test(fileName);
//                 content += `<div class="file-preview">${
//                     isImage 
//                         ? `<img src="${sanitizeHTML(fileUrl)}" alt="${sanitizeHTML(fileName)}" />`
//                         : `<a href="${sanitizeHTML(fileUrl)}" target="_blank" rel="noopener noreferrer">${sanitizeHTML(fileName)}</a>`
//                 }</div>`;
//             }

//             messageDiv.innerHTML = `${content}<span class="timestamp">${time} ${getTicks(status)}</span>`;
//             if (messagesDiv) messagesDiv.scrollTop = messagesDiv.scrollHeight;
//         }

//         function getTicks(status) {
//             switch (status) {
//                 case "sent": return '<span class="tick">✓</span>';
//                 case "delivered": return '<span class="tick">✓✓</span>';
//                 case "seen": return '<span class="tick blue">✓✓</span>';
//                 default: return "";
//             }
//         }

//         // Message sending
//         function sendMessage() {
//             if (!input || !socket || !input.value.trim()) return;

//             const messageId = generateMessageId();
//             const messageText = input.value.trim();

//             socket.send(JSON.stringify({
//                 message: messageText,
//                 sender: "User",
//                 message_id: messageId,
//             }));
//             appendMessage("User", messageText, null, null, "user", messageId, "sent");
//             input.value = "";
//         }

//         if (input) {
//             input.addEventListener("keypress", (e) => {
//                 if (e.key === "Enter" && input.value.trim() && socket) {
//                     sendMessage();
//                 }
//             });
//         }

//         if (sendBtn) {
//             sendBtn.addEventListener("click", sendMessage);
//         }

//         // Typing notification
//         let typingTimeout;
//         function notifyTyping() {
//             if (!socket || !input) return;

//             const content = input.value.trim();
//             socket.send(JSON.stringify({
//                 typing: content.length > 0,
//                 content: content,
//                 sender: "User",
//             }));

//             clearTimeout(typingTimeout);
//             typingTimeout = setTimeout(() => {
//                 socket.send(JSON.stringify({
//                     typing: false,
//                     content: "",
//                     sender: "User",
//                 }));
//             }, 1000);
//         }
//         if (input) {
//             input.addEventListener("input", notifyTyping);
//         }

//         // Form submission
//         if (formSubmit) {
//             formSubmit.addEventListener("click", () => {
//                 const nameField = document.getElementById("form-name");
//                 const emailField = document.getElementById("form-email");
//                 const name = nameField?.value.trim() || "";
//                 const email = emailField?.value.trim() || "";

//                 if (!name || !email) {
//                     appendSystemMessage("Please enter both name and email.");
//                     return;
//                 }
//                 if (!isValidEmail(email)) {
//                     appendSystemMessage("Please enter a valid email address.");
//                     return;
//                 }
//                 if (!socket) return;

//                 const messageId = generateMessageId();
//                 socket.send(JSON.stringify({
//                     form_data: { name, email },
//                     sender: "User",
//                     message_id: messageId,
//                 }));

//                 if (nameField) nameField.value = "";
//                 if (emailField) emailField.value = "";
//                 appendSystemMessage("Information submitted successfully!");
//             });
//         }

//         // File upload handling
//         if (fileInput) {
//             fileInput.addEventListener("change", (e) => {
//                 const file = e.target.files[0];
//                 if (!file) return;

//                 const maxSize = 10 * 1024 * 1024;
//                 if (file.size > maxSize) {
//                     appendSystemMessage("File size too large. Maximum size is 10MB.");
//                     fileInput.value = "";
//                     return;
//                 }

//                 if (filePreviewContainer && filePreviewName) {
//                     filePreviewName.textContent = file.name;
//                     filePreviewContainer.style.display = "flex";
//                 }
//             });
//         }

//         if (removeFileBtn && filePreviewContainer && fileInput) {
//             removeFileBtn.addEventListener("click", () => {
//                 fileInput.value = "";
//                 filePreviewContainer.style.display = "none";
//             });
//         }

//         function uploadFile() {
//             if (!fileInput || !fileInput.files[0] || !socket) return;

//             const file = fileInput.files[0];
//             const messageId = generateMessageId();
//             const formData = new FormData();
//             formData.append("file", file);
//             formData.append("room_id", roomId);
//             formData.append("message_id", messageId);

//             fetch(`${WIDGET_CONFIG.apiUrl}/upload`, {
//                 method: "POST",
//                 body: formData,
//             })
//                 .then((response) => {
//                     if (!response.ok) throw new Error("Failed to upload file");
//                     return response.json();
//                 })
//                 .then((data) => {
//                     socket.send(JSON.stringify({
//                         file_url: data.file_url,
//                         file_name: file.name,
//                         sender: "User",
//                         message_id: messageId,
//                     }));
//                     appendMessage("User", null, data.file_url, file.name, "user", messageId, "sent");
//                     fileInput.value = "";
//                     if (filePreviewContainer) filePreviewContainer.style.display = "none";
//                 })
//                 .catch((error) => {
//                     console.error("Error uploading file:", error);
//                     appendSystemMessage("Failed to upload file. Please try again.");
//                 });
//         }

//         // Utility functions
//         function generateMessageId() {
//             return `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
//         }

//         function sanitizeHTML(text) {
//             if (!text) return "";
//             const div = document.createElement("div");
//             div.textContent = text;
//             return div.innerHTML;
//         }

//         function isValidEmail(email) {
//             const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
//             return emailRegex.test(email);
//         }

//         function playNotificationSound() {
//             if (!notificationEnabled || !audioContext) return;

//             try {
//                 const oscillator = audioContext.createOscillator();
//                 const gainNode = audioContext.createGain();

//                 oscillator.connect(gainNode);
//                 gainNode.connect(audioContext.destination);

//                 oscillator.frequency.setValueAtTime(800, audioContext.currentTime);
//                 oscillator.frequency.setValueAtTime(600, audioContext.currentTime + 0.1);

//                 gainNode.gain.setValueAtTime(0, audioContext.currentTime);
//                 gainNode.gain.linearRampToValueAtTime(0.3, audioContext.currentTime + 0.01);
//                 gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.3);

//                 oscillator.start(audioContext.currentTime);
//                 oscillator.stop(audioContext.currentTime + 0.3);
//             } catch (e) {
//                 console.error("Error playing notification sound:", e);
//             }
//         }

//         // Initialize widget behavior
//         initializeWidgetBehavior();

//         // Auto-connect WebSocket
//         if (roomId && widgetState.connectionEstablished) {
//             setTimeout(() => {
//                 console.log("🚀 Auto-connecting WebSocket...");
//                 connectWebSocket(roomId);
//             }, 2000);
//         }

//     } catch (err) {
//         console.warn("Error initializing chat:", err);
//     }
// });

// // Clean up on page unload
// window.addEventListener("beforeunload", () => {
//     if (socket) {
//         socket.close();
//     }
//     if (audioContext) {
//         audioContext.close();
//     }
// });