document.addEventListener("DOMContentLoaded", function () {
    // Extract widget_id from the script URL
    let scriptSrc;
    const scripts = document.getElementsByTagName("script");
    const script = Array.from(scripts).find(s => s.src.includes("direct_chat.js"));
    if (script) {
        scriptSrc = script.src;
    } else {
        console.error("Unable to find direct_chat.js script tag");
        return;
    }

    const urlParams = new URLSearchParams(scriptSrc.split('?')[1]);
    const widgetId = urlParams.get('widget_id');

    if (!widgetId) {
        console.error("Widget ID not found in script URL");
        return;
    }

    console.log(`Extracted widget_id: ${widgetId}`);

    // Validate widget_id format (for debugging)
    const widgetIdRegex = /^[0-9a-f]{8}-[0-9a-f]{4,5}$/;
    if (!widgetIdRegex.test(widgetId)) {
        console.warn(
            `Widget ID "${widgetId}" does not match the expected format ` +
            `(xxxxxxxx-xxxx or xxxxxxxx-xxxxx, where x is a hexadecimal character). ` +
            `This may cause the POST request to fail.`
        );
    }

    // Configuration
    const WIDGET_CONFIG = {
        apiUrl: "http://localhost:8000/chat/user-chat/",
        wsUrl: "ws://localhost:8000/ws/chat/",
    };

    let roomId = localStorage.getItem("chat_room_id");
    let socket;
    const sentMessages = {};
    let systemMessageCount = 0; // Counter for system messages

    // Inject form HTML into the chat container (but keep it hidden initially)
    const chatContainer = document.getElementById("chat-container");
    if (!chatContainer) {
        console.error("Chat container (#chat-container) not found");
        return;
    }

    const chatForm = document.createElement("div");
    chatForm.id = "chat-form";
    chatForm.style.display = "none"; // Hide the form initially
    chatForm.innerHTML = `
        <div class="form-group">
            <label for="form-name">Name:</label>
            <input id="form-name" type="text" placeholder="Enter your name" required />
        </div>
        <div class="form-group">
            <label for="form-email">Email:</label>
            <input id="form-email" type="email" placeholder="Enter your email" required />
        </div>
        <button id="form-submit" class="submit-btn">Submit</button>
    `;
    const chatMessages = document.getElementById("chat-messages");
    if (chatMessages) {
        chatContainer.insertBefore(chatForm, chatMessages.nextSibling);
    } else {
        console.error("Chat messages container (#chat-messages) not found");
        return;
    }

    // Initially enable the chat input and send button
    const input = document.getElementById("chat-input");
    const sendBtn = document.getElementById("send-button");
    if (!input || !sendBtn) {
        console.error("Chat input (#chat-input) or send button (#send-button) not found");
        return;
    }

    // Add styling for the form and messages
    const style = document.createElement("style");
    style.innerHTML = `
        #chat-form {
            padding: 15px;
            background: #f9f9f9;
            border: 1px solid #ddd;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .form-group {
            margin-bottom: 10px;
        }
        .form-group label {
            display: block;
            font-weight: 500;
            margin-bottom: 5px;
            color: #333;
            font-size: 14px;
        }
        .form-group input {
            width: 100%;
            padding: 8px;
            border: 1px solid #ccc;
            border-radius: 5px;
            font-size: 14px;
        }
        .form-group input:focus {
            border-color: #007bff;
            outline: none;
            box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.2);
        }
        .submit-btn {
            padding: 10px 20px;
            background-color: #007bff;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
        }
        .submit-btn:hover {
            background-color: #0056b3;
        }
        .message {
            margin: 5px 0;
            padding: 8px 12px;
            border-radius: 5px;
            max-width: 80%;
            word-wrap: break-word;
        }
        .user {
            background-color: #007bff;
            color: white;
            margin-left: auto;
            text-align: right;
        }
        .agent {
            background-color: #e5e5e5;
            color: #333;
            margin-right: auto;
            text-align: left;
        }
        .system {
            background-color: #f8d7da;
            color: #721c24;
            margin: 0 auto;
            text-align: center;
        }
        .timestamp {
            display: block;
            font-size: 10px;
            color: #999;
            margin-top: 2px;
        }
    `;
    document.head.appendChild(style);

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

            if (data.error) {
                appendSystemMessage(`Error: ${sanitizeHTML(data.error)}`);
            } else if (data.form_data_received) {
                if (formDiv) {
                    formDiv.style.display = "none";
                    input.disabled = false;
                    sendBtn.disabled = false;
                    appendSystemMessage("Form submitted successfully. You can now chat.");
                }
            } else if (data.message) {
                const sender = data.sender;
                const className = sender === "User" ? "user" : sender === "System" ? "system" : "agent";
                appendMessage(sender, data.message, className, data.message_id, sender === "User" ? "delivered" : "delivered");

                // Check if the message is from the system and increment the counter
                if (sender === "System") {
                    systemMessageCount++;
                    console.log(`System message count: ${systemMessageCount}`);

                    // Show the form after the second system message
                    if (systemMessageCount === 2 && formDiv) {
                        formDiv.style.display = "block";
                        input.disabled = true;
                        sendBtn.disabled = true;
                        messagesDiv.scrollTop = messagesDiv.scrollHeight;
                    }
                }

                if (sender !== "User") {
                    socket.send(
                        JSON.stringify({
                            status: "seen",
                            message_id: data.message_id,
                            sender: "User",
                        })
                    );
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
    function appendMessage(sender, message, className, messageId, status) {
        const messagesDiv = document.getElementById("chat-messages");
        if (!messagesDiv) {
            console.error("Chat messages container (#chat-messages) not found");
            return;
        }

        const existingMessage = document.getElementById(`msg-${messageId}`);
        if (existingMessage) {
            console.log(`Message ${messageId} already exists`);
            return;
        }

        const div = document.createElement("div");
        div.className = `message ${className}`;
        div.id = `msg-${messageId}`;
        const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        div.innerHTML = `
            <span>${sanitizeHTML(message)}</span>
            <span class="timestamp">${time}</span>
        `;
        messagesDiv.appendChild(div);
        messagesDiv.scrollTop = messagesDiv.scrollHeight; // Auto-scroll to bottom
        if (sender === "User") {
            sentMessages[messageId] = true;
        }
    }

    // Append system message
    function appendSystemMessage(message) {
        appendMessage("System", message, "system", `sys-${Date.now()}`, "delivered");
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
                appendMessage("User", formattedMessage, "user", messageId, "sent");
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

    // Send message
    if (input && sendBtn) {
        input.addEventListener("keypress", (e) => {
            if (e.key === "Enter" && input.value.trim() && socket && !input.disabled) {
                sendMessage();
            }
        });

        sendBtn.addEventListener("click", () => {
            if (input.value.trim() && socket && !input.disabled) {
                sendMessage();
            }
        });

        function sendMessage() {
            const messageId = generateMessageId();
            socket.send(
                JSON.stringify({
                    message: input.value,
                    sender: "User",
                    message_id: messageId,
                })
            );
            appendMessage("User", input.value, "user", messageId, "sent");
            input.value = "";
        }
    }

    // Start the chat
    initializeChat();
});