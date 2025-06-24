// Full widget JS with:
// - fixed center image as chat background
// - scrollable messages
// - emoji picker
// - file upload
// - user message broadcasting retained

(function () {
    const CHAT_LOG_PREFIX = "[💬 ChatWidget]";

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", main);
    } else {
        main();
    }

    function injectStyles() {
        const style = document.createElement("style");
        style.innerHTML = `
            body {
                margin: 0;
                padding: 0;
                background-color: #f4f4f4;
            }

            #chat-container {
                max-width: 800px;
                margin: 0 auto;
                height: 90vh;
                border: 1px solid #ccc;
                border-radius: 8px;
                background: white;
                display: flex;
                flex-direction: column;
                position: relative;
                overflow: hidden;
                box-shadow: 0 0 8px rgba(0, 0, 0, 0.1);
            }

            #chat-messages {
                flex: 1;
                padding: 20px;
                overflow-y: auto;
                background: url('https://emailbulkshoot.s3.ap-southeast-2.amazonaws.com/assests+for+Email+Automation/Techserve%404x.png') no-repeat center center;
                background-size: contain;
            }

            .bubble-wrapper {
                display: flex;
                margin: 8px;
                clear: both;
            }
            .bubble-wrapper.user {
                justify-content: flex-end;
            }
            .bubble-wrapper.agent {
                justify-content: flex-start;
            }
            .bubble-wrapper.system {
                justify-content: center;
            }

            .message {
                max-width: 75%;
            }

            .bubble {
                padding: 10px 14px;
                border-radius: 16px;
                position: relative;
                box-shadow: 0 1px 4px rgba(0,0,0,0.1);
                word-wrap: break-word;
            }

            .bubble-content {
                font-size: 14px;
            }

            .timestamp {
                font-size: 11px;
                text-align: right;
                margin-top: 5px;
                opacity: 0.5;
            }

            .message.user .bubble {
                background-color: #007bff;
                color: white;
                border-bottom-right-radius: 0;
            }
            .message.agent .bubble {
                background-color: #e7f6e7;
                color: black;
                border-bottom-left-radius: 0;
            }
            .message.system .bubble {
                background-color: #fff3cd;
                color: #856404;
                border-radius: 12px;
            }

            #chat-controls {
                display: flex;
                gap: 8px;
                padding: 10px;
                border-top: 1px solid #ddd;
                background-color: #f9f9f9;
            }

            #chat-input {
                flex: 1;
                padding: 10px;
                border-radius: 5px;
                border: 1px solid #ccc;
            }

            #emoji-button,
            #file-button,
            #send-button {
                padding: 0 12px;
                background: white;
                border: 1px solid #ccc;
                border-radius: 5px;
                cursor: pointer;
            }

            #emoji-picker {
                position: absolute;
                bottom: 60px;
                left: 10px;
                background: white;
                border: 1px solid #ccc;
                padding: 5px;
                display: none;
                z-index: 10;
                border-radius: 6px;
            }
        `;
        document.head.appendChild(style);
    }

    function appendEmojiPicker(input) {
        const picker = document.createElement('div');
        picker.id = "emoji-picker";
        const emojis = ["😀", "😂", "😎", "👍", "🎉", "❤️", "🤖"];
        emojis.forEach(e => {
            const span = document.createElement("span");
            span.textContent = e;
            span.style.cursor = "pointer";
            span.style.fontSize = "18px";
            span.style.margin = "5px";
            span.onclick = () => {
                input.value += e;
                picker.style.display = "none";
            };
            picker.appendChild(span);
        });
        document.body.appendChild(picker);
        return picker;
    }

    function broadcastAttachment(inputElement, socket) {
        inputElement.addEventListener("change", () => {
            const file = inputElement.files[0];
            if (file) {
                const msgId = `msg-${Date.now()}-${Math.random().toString(36).substring(2, 8)}`;
                const text = `📎 ${file.name}`;
                socket.send(JSON.stringify({ sender: "User", message: text, message_id: msgId }));
                appendMessage("User", text, "user", msgId);
            }
        });
    }

    function main() {
        console.group(`${CHAT_LOG_PREFIX} Initialization`);

        injectStyles();  // ✅ Inject bubble CSS

        let scriptSrc;
        const scripts = document.getElementsByTagName("script");
        const script = Array.from(scripts).find(s => s.src.includes("direct_chat.js"));

        if (script) {
            scriptSrc = script.src;
            console.log("📦 Script loaded from:", scriptSrc);
        } else {
            console.error(`${CHAT_LOG_PREFIX} ❌ direct_chat.js script tag not found`);
            console.groupEnd();
            return;
        }

        const urlParams = new URLSearchParams(scriptSrc.split('?')[1]);
        const widgetId = urlParams.get('widget_id');

        if (!widgetId) {
            console.error(`${CHAT_LOG_PREFIX} ❌ widget_id not found in script URL`);
            console.groupEnd();
            return;
        }

        console.log("🆔 Extracted widget_id:", widgetId);

        const WIDGET_CONFIG = {
            apiUrl: "http://localhost:8000/chat/user-chat/",
            wsUrl: "ws://localhost:8000/ws/chat/",
        };

        const chatContainer = document.getElementById("chat-container");
        const chatMessages = document.getElementById("chat-messages");
        const input = document.getElementById("chat-input");
        const sendBtn = document.getElementById("send-button");

        if (!chatContainer || !chatMessages || !input || !sendBtn) {
            console.error(`${CHAT_LOG_PREFIX} ❌ Required DOM elements missing`);
            console.groupEnd();
            return;
        }

        console.log("✅ Required DOM elements found");
        console.groupEnd();

        let socket;
        let roomId = localStorage.getItem("chat_room_id");
        const sentMessages = {};
        let systemMessageCount = 0;

        console.groupCollapsed(`${CHAT_LOG_PREFIX} Fetching IP`);
        fetch("https://api.ipify.org?format=json")
            .then(res => res.json())
            .then(data => {
                console.log("🌐 Detected IP:", data.ip);
                initializeChat(data.ip);
                console.groupEnd();
            })
            .catch(err => {
                console.error("❌ IP Fetch Error:", err);
                appendSystemMessage("Unable to get your IP address. Chat may not function.");
                console.groupEnd();
            });

        function initializeChat(ip) {
            if (roomId) {
                console.log(`${CHAT_LOG_PREFIX} 📂 Using cached room_id:`, roomId);
                connectWebSocket(roomId);
                return;
            }

            console.group(`${CHAT_LOG_PREFIX} Creating Chat Room`);
            fetch(WIDGET_CONFIG.apiUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ widget_id: widgetId, ip }),
            })
                .then(res => {
                    if (!res.ok) {
                        return res.json().then(data => {
                            console.error("❌ Room creation failed:", data);
                            throw new Error(data.error || "Room creation failed");
                        });
                    }
                    return res.json();
                })
                .then(data => {
                    roomId = data.room_id;
                    localStorage.setItem("chat_room_id", roomId);
                    console.log("✅ Room created with ID:", roomId);
                    connectWebSocket(roomId);
                    console.groupEnd();
                })
                .catch(err => {
                    console.error("❌ Chat Init Failed:", err);
                    appendSystemMessage("Chat failed to start. Please refresh or try again.");
                    console.groupEnd();
                });
        }

        function connectWebSocket(roomId) {
            socket = new WebSocket(`${WIDGET_CONFIG.wsUrl}${roomId}/`);

            socket.onopen = () => console.log(`${CHAT_LOG_PREFIX} 🔌 WebSocket connected`);
            socket.onclose = e => {
                console.warn(`${CHAT_LOG_PREFIX} ⚠️ WebSocket closed:`, e);
                appendSystemMessage("Chat disconnected. Please refresh.");
            };
            socket.onerror = e => {
                console.error(`${CHAT_LOG_PREFIX} 🚨 WebSocket error:`, e);
                appendSystemMessage("WebSocket connection error.");
            };

            socket.onmessage = event => {
                console.groupCollapsed(`${CHAT_LOG_PREFIX} 📩 New message received`);
                console.log("Raw:", event.data);

                try {
                    const data = JSON.parse(event.data);
                    console.log("Parsed:", data);

                    const formDiv = document.getElementById("chat-form");

                    if (data.error) {
                        appendSystemMessage(data.error);
                    } else if (data.form_data_received) {
                        formDiv.style.display = "none";
                        input.disabled = false;
                        sendBtn.disabled = false;
                        appendSystemMessage("Form submitted. You can now chat.");
                    } else if (data.message) {
                        const sender = data.sender;
                        let className = "agent";
                        if (sender.toLowerCase() === "user") className = "user";
                        else if (sender.toLowerCase() === "wish-bot" || sender.toLowerCase() === "system") className = "system";

                        appendMessage(sender, data.message, className, data.message_id);

                        if (sender.toLowerCase() === "system") {
                            systemMessageCount++;
                            if (systemMessageCount === 2) {
                                formDiv.style.display = "block";
                                input.disabled = true;
                                sendBtn.disabled = true;
                            }
                        }

                        if (sender.toLowerCase() !== "user") {
                            socket.send(JSON.stringify({
                                status: "seen",
                                message_id: data.message_id,
                                sender: "User"
                            }));
                        }
                    }
                } catch (e) {
                    console.error(`${CHAT_LOG_PREFIX} ❌ JSON Parse Error:`, e);
                }
                console.groupEnd();
            };
        }

        function appendMessage(sender, message, className, messageId) {
            if (document.getElementById(`msg-${messageId}`)) return;

            const div = document.createElement("div");
            div.className = `message ${className}`;
            div.id = `msg-${messageId}`;

            const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

            div.innerHTML = `
                <div class="bubble">
                    <div class="bubble-content">${sanitizeHTML(message)}</div>
                    <div class="timestamp">${time}</div>
                </div>
            `;

            const wrapper = document.createElement("div");
            wrapper.className = `bubble-wrapper ${className}`;
            wrapper.appendChild(div);
            chatMessages.appendChild(wrapper);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        function appendSystemMessage(msg) {
            appendMessage("System", msg, "system", `sys-${Date.now()}`);
        }

        function sanitizeHTML(str) {
            const div = document.createElement("div");
            div.textContent = str;
            return div.innerHTML;
        }

        function generateMessageId() {
            return `msg-${Date.now()}-${Math.random().toString(36).substring(2, 8)}`;
        }

        sendBtn.addEventListener("click", sendMessage);
        input.addEventListener("keypress", e => {
            if (e.key === "Enter" && !input.disabled) sendMessage();
        });

        function sendMessage() {
            const text = input.value.trim();
            if (!text || !socket) return;
            const msgId = generateMessageId();
            socket.send(JSON.stringify({ message: text, sender: "User", message_id: msgId }));
            appendMessage("User", text, "user", msgId);
            input.value = "";
        }

        // Optional: Form Handling
        const chatForm = document.createElement("div");
        chatForm.id = "chat-form";
        chatForm.style.display = "none";
        chatForm.innerHTML = `
            <div class="form-group">
                <label for="form-name">Name:</label>
                <input id="form-name" type="text" required placeholder="Your name" />
            </div>
            <div class="form-group">
                <label for="form-email">Email:</label>
                <input id="form-email" type="email" required placeholder="Your email" />
            </div>
            <button id="form-submit" class="submit-btn">Submit</button>
        `;
        chatContainer.insertBefore(chatForm, chatMessages.nextSibling);

        document.getElementById("form-submit")?.addEventListener("click", () => {
            const name = document.getElementById("form-name").value.trim();
            const email = document.getElementById("form-email").value.trim();

            console.group(`${CHAT_LOG_PREFIX} ✍️ Form Submission`);
            console.log("👤 Name:", name);
            console.log("📧 Email:", email);

            if (!name || !email) {
                console.warn("⚠️ Missing form fields");
                appendSystemMessage("Please fill in both name and email.");
                console.groupEnd();
                return;
            }

            if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
                appendSystemMessage("Invalid email format.");
                return;
            }

            const msgId = generateMessageId();
            socket.send(JSON.stringify({
                sender: "User",
                form_data: { name, email },
                message_id: msgId,
            }));
            appendMessage("User", `Name: ${name}, Email: ${email}`, "user", msgId);
            console.groupEnd();
        });
    }
})();
