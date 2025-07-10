// Initialize all global variables at the top
let audioContext = null;
let socket = null;
let notificationEnabled = true;
const sentMessages = {};
let roomId = null;
let cachedClientIP = null;

// Widget state management
let widgetState = {
    isOpen: false,
    notificationShown: false,
    connectionEstablished: false,
    pageLoadTime: Date.now(),
};

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

document.addEventListener("DOMContentLoaded", async function () {
    // Initialize DOM elements after widget is created
    function initializeDOMElements() {
        return {
            muteToggle: document.getElementById("mute-toggle"),
            emojiPickerContainer: document.getElementById("emoji-picker"),
            chatBubbleContainer: document.getElementById("chat-bubble-container"),
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
            footer: document.getElementById("chat-footer")
        };
    }

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
        roomId = localStorage.getItem("chat_room_id") || null;
        roomId = data.room_id;
        localStorage.setItem("chat_room_id", roomId);

        // Apply widget settings
        const settings = data.widget?.settings || {};
        WIDGET_CONFIG.themeColor = settings.primaryColor || WIDGET_CONFIG.themeColor;
        WIDGET_CONFIG.logoUrl = settings.logo || WIDGET_CONFIG.logoUrl;
        WIDGET_CONFIG.position = settings.position || WIDGET_CONFIG.position;
        WIDGET_CONFIG.enableAttentionGrabber = settings.enableAttentionGrabber || false;
        WIDGET_CONFIG.attentionGrabber = settings.attentionGrabber || "";
        WIDGET_CONFIG.chatTitle = name || WIDGET_CONFIG.chatTitle;
        WIDGET_CONFIG.placeholder = settings.placeholder || WIDGET_CONFIG.placeholder;
        WIDGET_CONFIG.is_active = data.widget?.is_active ?? settings.is_active ?? true;

        console.log("✅ Chat initialized with room:", roomId);
        console.log("📍 User location:", data.user_location);
        console.log("🔧 Widget active status:", WIDGET_CONFIG.is_active);
        console.log("🔧 Full widget data:", data.widget);

        // Check if widget is active before rendering
        if (WIDGET_CONFIG.is_active === false) {
            console.log("Widget is not active, not rendering");
            return;
        }

        // Mark connection as ready for WebSocket
        widgetState.connectionEstablished = true;

        // Create widget container
        const widgetContainer = document.createElement("div");
        widgetContainer.id = "chat-widget";
        document.body.appendChild(widgetContainer);

        // Define bubble position before loading CSS/HTML
        const bubblePosition = WIDGET_CONFIG.position === "left" ? "left" : "right";
        const windowPosition = WIDGET_CONFIG.position === "left" ? "left" : "right";

        const attentionGrabberHTML =
            WIDGET_CONFIG.enableAttentionGrabber && WIDGET_CONFIG.attentionGrabber
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
        const {
            muteToggle,
            emojiPickerContainer,
            chatBubble,
            chatWindow,
            emojiButton,
            input,
            sendBtn,
            formSubmit,
            fileInput,
            removeFileBtn,
            filePreviewContainer,
            filePreviewName,
            messagesDiv,
            formDiv,
            footer
        } = initializeDOMElements();

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

        // Initialize widget behavior
        function initializeWidgetBehavior() {
            console.log("🔧 initializeWidgetBehavior() called");

            if (chatWindow) {
                chatWindow.style.display = "none";
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
        if (muteToggle) {
            muteToggle.textContent = notificationEnabled ? "🔊" : "🔇";
            muteToggle.addEventListener("click", () => {
                notificationEnabled = !notificationEnabled;
                muteToggle.textContent = notificationEnabled ? "🔊" : "🔇";
            });
        }

        // Set up emoji picker
        if (emojiPickerContainer) {
            const emojiScript = document.createElement("script");
            emojiScript.src = "https://cdn.jsdelivr.net/npm/emoji-picker-element@^1/index.js";
            emojiScript.type = "module";
            document.head.appendChild(emojiScript);

            emojiScript.onload = () => {
                const emojiPicker = document.createElement("emoji-picker");
                emojiPickerContainer.appendChild(emojiPicker);
                emojiPicker.addEventListener("emoji-click", (event) => {
                    if (input) {
                        input.value += event.detail.unicode;
                        emojiPickerContainer.style.display = "none";
                        notifyTyping();
                    }
                });
            };
        }

        // Set up chat bubble toggle
        if (chatBubble && chatWindow) {
            chatBubble.addEventListener("click", (event) => {
                event.stopPropagation();
                hideNotificationBadge();
                const isVisible = chatWindow.style.display === "flex";
                chatWindow.style.display = isVisible ? "none" : "flex";
                widgetState.isOpen = !isVisible;
                console.log(`Chat widget ${isVisible ? 'closed' : 'opened'}`);
            });
        }

        // WebSocket connection
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

            socket.onopen = () => {
                console.log("✅ WebSocket connected successfully");
                updateConnectionStatus(true);
                widgetState.connectionEstablished = true;
            };

            socket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    handleIncomingMessage(data);
                } catch (e) {
                    console.error("Failed to parse WebSocket message:", e);
                }
            };

            socket.onclose = (event) => {
                console.log("🔌 WebSocket disconnected, code:", event.code, "reason:", event.reason);
                updateConnectionStatus(false);
                widgetState.connectionEstablished = false;

                if (widgetState.isOpen && chatWindow && chatWindow.style.display === "flex") {
                    appendSystemMessage("Disconnected. Please refresh to reconnect.");
                }
            };

            socket.onerror = (error) => {
                console.error("❌ WebSocket error:", error);
                updateConnectionStatus(false);
                widgetState.connectionEstablished = false;

                if (widgetState.isOpen && chatWindow && chatWindow.style.display === "flex") {
                    appendSystemMessage("Chat error occurred.");
                }
            };
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
            if (!messagesDiv || !formDiv || !footer) return;

            if (data.show_form && data.form_type === "user_info") {
                formDiv.style.display = "block";
                footer.style.display = "none";
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
                return;
            }

            if (data.form_data_received) {
                formDiv.style.display = "none";
                footer.style.display = "flex";
                return;
            }

            if (data.typing && data.sender !== "User") {
                const typingId = `typing-${data.sender}`;
                if (!document.getElementById(typingId)) {
                    const typingElement = document.createElement("div");
                    typingElement.id = typingId;
                    typingElement.className = "message system";
                    typingElement.innerHTML = `<i>${sanitizeHTML(data.sender)} is typing...</i>`;
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
                    data.sender === "User" ? "user" : data.sender === "System" ? "system" : "agent",
                    data.message_id,
                    data.sender === "User" ? "delivered" : "delivered"
                );
                if (data.sender !== "User") {
                    socket.send(JSON.stringify({
                        status: "seen",
                        message_id: data.message_id,
                        sender: "User",
                    }));
                    playNotificationSound();
                }
            }
        }

        function appendMessage(sender, message, fileUrl, fileName, className, messageId, status) {
            if (!messagesDiv) return;

            if (document.getElementById(`msg-${messageId}`)) {
                updateMessageStatus(messageId, status, message, fileUrl, fileName);
                return;
            }

            const div = document.createElement("div");
            div.className = `message ${className}`;
            div.id = `msg-${messageId}`;
            const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
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

            div.innerHTML = `${content}<span class="timestamp">${time} ${ticks}</span>`;
            messagesDiv.appendChild(div);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;

            if (sender === "User") {
                sentMessages[messageId] = true;
            }
        }

        function appendSystemMessage(message) {
            appendMessage("System", message, null, null, "system", `sys-${Date.now()}`, "delivered");
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
            if (messagesDiv) messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        function getTicks(status) {
            switch (status) {
                case "sent": return '<span class="tick">✓</span>';
                case "delivered": return '<span class="tick">✓✓</span>';
                case "seen": return '<span class="tick blue">✓✓</span>';
                default: return "";
            }
        }

        // Message sending
        function sendMessage() {
            if (!input || !socket || !input.value.trim()) return;

            const messageId = generateMessageId();
            const messageText = input.value.trim();

            socket.send(JSON.stringify({
                message: messageText,
                sender: "User",
                message_id: messageId,
            }));
            appendMessage("User", messageText, null, null, "user", messageId, "sent");
            input.value = "";
        }

        if (input) {
            input.addEventListener("keypress", (e) => {
                if (e.key === "Enter" && input.value.trim() && socket) {
                    sendMessage();
                }
            });
        }

        if (sendBtn) {
            sendBtn.addEventListener("click", sendMessage);
        }

        // Typing notification
        let typingTimeout;
        function notifyTyping() {
            if (!socket || !input) return;

            const content = input.value.trim();
            socket.send(JSON.stringify({
                typing: content.length > 0,
                content: content,
                sender: "User",
            }));

            clearTimeout(typingTimeout);
            typingTimeout = setTimeout(() => {
                socket.send(JSON.stringify({
                    typing: false,
                    content: "",
                    sender: "User",
                }));
            }, 1000);
        }
        if (input) {
            input.addEventListener("input", notifyTyping);
        }

        // Form submission
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
                socket.send(JSON.stringify({
                    form_data: { name, email },
                    sender: "User",
                    message_id: messageId,
                }));

                if (nameField) nameField.value = "";
                if (emailField) emailField.value = "";
                appendSystemMessage("Information submitted successfully!");
            });
        }

        // File upload handling
        if (fileInput) {
            fileInput.addEventListener("change", (e) => {
                const file = e.target.files[0];
                if (!file) return;

                const maxSize = 10 * 1024 * 1024;
                if (file.size > maxSize) {
                    appendSystemMessage("File size too large. Maximum size is 10MB.");
                    fileInput.value = "";
                    return;
                }

                if (filePreviewContainer && filePreviewName) {
                    filePreviewName.textContent = file.name;
                    filePreviewContainer.style.display = "flex";
                }
            });
        }

        if (removeFileBtn && filePreviewContainer && fileInput) {
            removeFileBtn.addEventListener("click", () => {
                fileInput.value = "";
                filePreviewContainer.style.display = "none";
            });
        }

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
                    fileInput.value = "";
                    if (filePreviewContainer) filePreviewContainer.style.display = "none";
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

        // Auto-connect WebSocket
        if (roomId && widgetState.connectionEstablished) {
            setTimeout(() => {
                console.log("🚀 Auto-connecting WebSocket...");
                connectWebSocket(roomId);
            }, 2000);
        }

    } catch (err) {
        console.warn("Error initializing chat:", err);
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