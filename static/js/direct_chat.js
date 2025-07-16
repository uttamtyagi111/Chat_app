// Full widget JS with:
// - fixed center image as chat background (with adjustable opacity)
// - scrollable messages
// - emoji picker
// - file upload with AWS S3 integration
// - user message broadcasting retained
// - Dynamic input box resizing
// - WhatsApp-like send button, emoji, and file attachment positioning
// - Send button integrated inside the text input box

(function () {
    const CHAT_LOG_PREFIX = "[💬 ChatWidget]";

    // Ensure main function runs after the DOM is fully loaded
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", main);
    } else {
        main();
    }

function injectStyles() {
    const style = document.createElement("style");
    style.innerHTML = `
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 0; /* Remove body padding to allow fixed positioning of chat container */
            background-color: #f4f4f4;
            /* No need for body flex centering when chat container is fixed */
        }

        #chat-container {
            max-width: 800px;
            width: min(800px, 90vw); /* Responsive width, capped at 800px */
            height: 90vh; /* Fixed height relative to viewport */
            border: 1px solid #ccc;
            border-radius: 8px;
            background: white; /* Base background for the container */
            display: flex;
            flex-direction: column;
            position: fixed; /* Makes the chat container fixed on the screen */
            top: 50%; /* Center vertically */
            left: 50%; /* Center horizontally */
            transform: translate(-50%, -50%); /* Adjust for exact centering */
            overflow: hidden; /* Hide any container-level scrollbars */
            box-shadow: 0 0 8px rgba(0, 0, 0, 0.1);
            z-index: 1000; /* Ensure it's on top of other page content */
        }

        #chat-header {
            padding: 15px 20px;
            background-color: #075E54; /* WhatsApp header green */
            color: white;
            font-size: 18px;
            font-weight: bold;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            flex-shrink: 0; /* Prevent header from shrinking */
        }

        #chat-messages {
            flex: 1; /* Allows messages to take up available space and push controls to bottom */
            padding: 10px 15px;
            overflow-y: auto; /* Enables vertical scrolling for messages ONLY */
            /* Background image with reduced opacity overlay, fixed relative to viewport */
            background:
                linear-gradient(rgba(255, 255, 255, 0.4), rgba(255, 255, 255, 0.4)),
                url('https://emailbulkshoot.s3.ap-southeast-2.amazonaws.com/assests+for+Email+Automation/Techserve%404x.png') no-repeat center center;
            background-size: contain;
            background-attachment: fixed; /* VERY IMPORTANT: Makes background image fixed relative to viewport */
            display: flex;
            flex-direction: column; /* Messages stack vertically */
        }

        .bubble-wrapper {
            display: flex;
            margin: 8px 0;
            clear: both;
            width: 100%;
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
            margin-bottom: 2px;
        }

        .bubble {
            padding: 10px 12px;
            border-radius: 8px;
            position: relative;
            box-shadow: 0 1px 1px rgba(0,0,0,0.08);
            word-wrap: break-word;
        }

        .bubble-content {
            font-size: 14px;
            line-height: 1.4;
        }

        .timestamp {
            font-size: 10px;
            text-align: right;
            margin-top: 4px;
            opacity: 0.6;
            color: #555;
        }

        /* WhatsApp-like colors */
        .message.user .bubble {
            background-color: #DCF8C6; /* Light green for user messages */
            color: #111;
            border-bottom-right-radius: 2px; /* Sharp corner for user */
        }

        .message.agent .bubble {
            background-color: #FFFFFF; /* White for agent messages */
            border: 1px solid #ECE5DD; /* Light border */
            color: #000;
            border-bottom-left-radius: 2px; /* Sharp corner for agent */
        }

        .message.system .bubble {
            background-color: #E0F2F1; /* Light teal for system messages */
            color: #00796B;
            border-radius: 12px;
            text-align: center;
            font-style: italic;
        }

        #chat-controls {
            display: flex;
            align-items: flex-end; /* Align items to the bottom */
            padding: 8px 10px;
            border-top: 1px solid #ddd;
            background-color: #f0f0f0; /* Lighter background for controls */
            position: relative;
            flex-shrink: 0; /* Prevent controls from shrinking */
        }

        /* Wrapper for the input field and the send button */
        .input-area-wrapper {
            flex: 1; /* Takes remaining space in chat-controls */
            position: relative; /* For positioning the send button */
            display: flex; /* To contain input and button */
            align-items: flex-end; /* Align contents to bottom */
            background-color: white; /* Matches input field background */
            border-radius: 20px; /* Rounded corners for the entire input area */
            border: 1px solid #ccc; /* Border for the entire input area */
            margin-right: 8px; /* Space from emoji/file buttons */
            overflow: hidden; /* Ensure button stays within bounds if positioned near edge */
        }

        #chat-input {
            flex: 1; /* Input takes up most space within the wrapper */
            padding: 10px 45px 10px 15px; /* Add right padding for the button */
            border: none; /* Remove individual border, wrapper handles it */
            border-radius: 0; /* Remove individual border-radius */
            background: transparent; /* Transparent background, wrapper provides color */
            min-height: 20px;
            max-height: 120px; /* Max height before scrollbar appears */
            resize: none; /* Disable manual resize */
            overflow-y: auto; /* Enable scrollbar when content exceeds max-height */
            font-size: 15px;
            line-height: 1.4;
        }

        #send-button {
            position: absolute;
            right: 8px; /* Position from the right edge of the wrapper */
            bottom: 8px; /* Position from the bottom edge of the wrapper */
            width: 32px; /* Smaller, icon-like size */
            height: 32px;
            background-color: #075E54; /* WhatsApp send button green */
            color: white;
            border: none;
            border-radius: 50%; /* Still circular, but smaller */
            font-size: 18px; /* Smaller icon */
            cursor: pointer;
            display: flex;
            justify-content: center;
            align-items: center;
            flex-shrink: 0; /* Prevent shrinking */
            padding: 0; /* Remove default padding */
        }
        #send-button:hover {
            background-color: #054C44;
        }

        #emoji-button,
        #file-button {
            display: flex;
            justify-content: center;
            align-items: center;
            width: 38px; /* Icon button size */
            height: 38px;
            border-radius: 50%;
            background: #f0f0f0; /* Match controls background */
            border: none;
            cursor: pointer;
            font-size: 20px;
            color: #555;
            margin-right: 8px;
            flex-shrink: 0;
        }
        #emoji-button:hover,
        #file-button:hover {
            background-color: #e0e0e0;
        }

        #emoji-picker {
            position: absolute;
            bottom: 65px; /* Position above the chat controls */
            right: 10px; /* Align with the right side */
            background: white;
            border: 1px solid #ccc;
            padding: 10px;
            display: none; /* Initially hidden, to be toggled by JS */
            z-index: 10;
            border-radius: 6px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            grid-template-columns: repeat(auto-fill, minmax(30px, 1fr)); /* For a nice emoji grid when visible */
            gap: 5px;
        }
        #emoji-picker span {
            cursor: pointer;
            font-size: 22px;
            text-align: center;
            padding: 3px;
            border-radius: 3px;
        }
        #emoji-picker span:hover {
            background-color: #f0f0f0;
        }

        /* File upload progress styles */
        .file-upload-progress {
            background-color: #f0f0f0;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 10px;
            margin: 5px 0;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .file-upload-progress .progress-bar {
            flex: 1;
            height: 6px;
            background-color: #e0e0e0;
            border-radius: 3px;
            overflow: hidden;
        }

        .file-upload-progress .progress-fill {
            height: 100%;
            background-color: #075E54;
            transition: width 0.3s ease;
        }

        .file-link {
            color: #075E54;
            text-decoration: none;
            font-weight: bold;
        }

        .file-link:hover {
            text-decoration: underline;
        }

        /* Loading spinner for file upload */
        .upload-spinner {
            border: 2px solid #f3f3f3;
            border-top: 2px solid #075E54;
            border-radius: 50%;
            width: 16px;
            height: 16px;
            animation: spin 1s linear infinite;
            margin-right: 8px;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        /* Form styling (optional, adjust as needed) */
        #chat-form {
            padding: 20px;
            border-top: 1px solid #eee;
            background-color: #f8f8f8;
            display: flex;
            flex-direction: column;
            gap: 10px;
            flex-shrink: 0; /* Prevent form from shrinking */
        }
        #chat-form label {
            font-weight: bold;
            margin-bottom: 5px;
            display: block;
        }
        #chat-form input[type="text"],
        #chat-form input[type="email"] {
            width: calc(100% - 22px);
            padding: 10px;
            border: 1px solid #ccc;
            border-radius: 5px;
            font-size: 16px;
        }
        #form-submit {
            padding: 10px 20px;
            background-color: #25D366; /* WhatsApp green for submit */
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            align-self: flex-end;
        }
        #form-submit:hover {
            background-color: #1DA851;
        }
    `;
    document.head.appendChild(style);
}

    // Pass chatControls to appendEmojiPicker for correct positioning
    function appendEmojiPicker(input, chatControls) {
        const picker = document.createElement("div");
        picker.id = "emoji-picker";
        const emojis = [
            "😀", "😂", "😎", "👍", "🎉", "❤️", "🤖", "👋", "👏", "🔥",
            "💡", "🤔", "🥳", "👍", "👎", "👌", "🙏", "💻", "📱", "✉️",
            "📞", "⚙️", "📈", "📊", "📆", "🔒", "🔓",
        ]; // More emojis
        emojis.forEach((e) => {
            const span = document.createElement("span");
            span.textContent = e;
            span.onclick = () => {
                input.value += e;
                input.dispatchEvent(new Event("input")); // Trigger input event for resize
                picker.style.display = "none";
            };
            picker.appendChild(span);
        });
        chatControls.appendChild(picker); // Append picker to chat-controls for better positioning
        return picker;
    }

    // File upload function that integrates with AWS S3 upload API
    async function uploadFile(file, widgetId) {
        const formData = new FormData();
        formData.append('file', file);
        
        const UPLOAD_API_URL = 'http://localhost:8000/chat/user-chat/upload-file/';
        
        try {
            const response = await fetch(UPLOAD_API_URL, {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Upload failed');
            }
            
            const result = await response.json();
            return result;
        } catch (error) {
            console.error('File upload error:', error);
            throw error;
        }
    }

    // Show upload progress
    function showUploadProgress(fileName, progressContainer) {
        const progressDiv = document.createElement('div');
        progressDiv.className = 'file-upload-progress';
        progressDiv.innerHTML = `
            <div class="upload-spinner"></div>
            <span>Uploading ${fileName}...</span>
            <div class="progress-bar">
                <div class="progress-fill" style="width: 0%"></div>
            </div>
        `;
        
        progressContainer.appendChild(progressDiv);
        return progressDiv;
    }

    // Handle file attachment with upload
    function handleFileAttachment(inputElement, socket, widgetId, chatMessages) {
        inputElement.addEventListener("change", async () => {
            const file = inputElement.files[0];
            if (!file) return;
            
            console.log(`${CHAT_LOG_PREFIX} 📎 File selected:`, file.name, `(${(file.size / 1024).toFixed(2)} KB)`);
            
            // Show upload progress
            const progressDiv = showUploadProgress(file.name, chatMessages);
            chatMessages.scrollTop = chatMessages.scrollHeight;
            
            try {
                // Simulate progress (since we can't track real progress with fetch)
                const progressBar = progressDiv.querySelector('.progress-fill');
                let progress = 0;
                const progressInterval = setInterval(() => {
                    progress += 10;
                    progressBar.style.width = `${Math.min(progress, 90)}%`;
                    if (progress >= 90) {
                        clearInterval(progressInterval);
                    }
                }, 100);
                
                // Upload file to S3
                const uploadResult = await uploadFile(file, widgetId);
                
                // Complete progress
                clearInterval(progressInterval);
                progressBar.style.width = '100%';
                
                // Remove progress indicator after a short delay
                setTimeout(() => {
                    progressDiv.remove();
                }, 1000);
                
                // Generate message with file info
                const msgId = `msg-${Date.now()}-${Math.random()
                    .toString(36)
                    .substring(2, 8)}`;
                
                const fileMessage = {
                    sender: "User",
                    message: `📎 <a href="${uploadResult.file_url}" target="_blank" class="file-link">${uploadResult.file_name}</a> (${(file.size / 1024).toFixed(2)} KB)`,
                    message_id: msgId,
                    file_url: uploadResult.file_url,
                    file_name: uploadResult.file_name,
                    file_size: file.size
                };
                
                // Send file message through WebSocket
                socket.send(JSON.stringify(fileMessage));
                
                // Display file message in chat
                appendMessage("User", fileMessage.message, "user", msgId);
                
                console.log(`${CHAT_LOG_PREFIX} ✅ File uploaded successfully:`, uploadResult.file_url);
                
            } catch (error) {
                console.error(`${CHAT_LOG_PREFIX} ❌ File upload failed:`, error);
                
                // Remove progress indicator
                progressDiv.remove();
                
                // Show error message
                appendSystemMessage(`Failed to upload file: ${error.message}`);
            }
            
            // Clear file input
            inputElement.value = null;
        });
    }

    function main() {
        console.group(`${CHAT_LOG_PREFIX} Initialization`);

        injectStyles(); // Call the function to inject all the CSS

        let scriptSrc;
        const scripts = document.getElementsByTagName("script");
        const script = Array.from(scripts).find((s) =>
            s.src.includes("direct_chat.js")
        );

        if (script) {
            scriptSrc = script.src;
            console.log("📦 Script loaded from:", scriptSrc);
        } else {
            console.error(
                `${CHAT_LOG_PREFIX} ❌ direct_chat.js script tag not found`
            );
            console.groupEnd();
            return;
        }

        const urlParams = new URLSearchParams(scriptSrc.split("?")[1]);
        const widgetId = urlParams.get("widget_id");

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

        // Replace the existing h2 with a new header for WhatsApp look
        const existingH2 = chatContainer.querySelector('h2');
        if (existingH2) {
            existingH2.remove();
        }
        const chatHeader = document.createElement("div");
        chatHeader.id = "chat-header";
        chatHeader.textContent = "Chat with Us"; // Or a dynamic title
        chatContainer.insertBefore(chatHeader, chatMessages);

        // Create chat controls container (the overall bar at the bottom)
        const chatControls = document.createElement("div");
        chatControls.id = "chat-controls";
        chatContainer.appendChild(chatControls); // Append to main container

        // Create emoji button
        const emojiButton = document.createElement("button");
        emojiButton.id = "emoji-button";
        emojiButton.innerHTML = "😀"; // Emoji icon
        chatControls.appendChild(emojiButton); // Append to chatControls

        // Create file button
        const fileButton = document.createElement("button");
        fileButton.id = "file-button";
        fileButton.innerHTML = "📎"; // Paperclip icon
        chatControls.appendChild(fileButton); // Append to chatControls

        // Create a wrapper for the input and send button to position send button inside
        const inputAreaWrapper = document.createElement("div");
        inputAreaWrapper.className = "input-area-wrapper"; // Use a class for this
        chatControls.appendChild(inputAreaWrapper); // Append to chatControls

        // Move the original input and send button into this new wrapper
        inputAreaWrapper.appendChild(input);
        inputAreaWrapper.appendChild(sendBtn);

        // Create and append the hidden file input
        const fileInput = document.createElement("input");
        fileInput.type = "file";
        fileInput.id = "file-upload-input";
        fileInput.style.display = "none";
        // Accept common file types
        fileInput.accept = "image/*,video/*,audio/*,.pdf,.doc,.docx,.txt,.csv,.xlsx,.zip,.rar";
        document.body.appendChild(fileInput); // Append to body or a less constrained area if it's hidden anyway

        // Create and append the emoji picker (relative to chatControls, so position within its bounds)
        const emojiPicker = appendEmojiPicker(input, chatControls);

        // Event listeners for emoji and file buttons
        emojiButton.addEventListener("click", () => {
            emojiPicker.style.display =
                emojiPicker.style.display === "grid" ? "none" : "grid"; // Toggle grid display
        });

        fileButton.addEventListener("click", () => {
            fileInput.click(); // Trigger click on hidden file input
        });

        // Dynamic input height adjustment
        input.addEventListener("input", () => {
            input.style.height = "auto"; // Reset height to recalculate
            input.style.height = input.scrollHeight + "px";
            chatMessages.scrollTop = chatMessages.scrollHeight; // Scroll to bottom when input expands
        });
        // Initial adjustment on load
        input.style.height = input.scrollHeight + "px";

        console.log("✅ Required DOM elements found and structured");
        console.groupEnd();

        let socket;
        let roomId = localStorage.getItem("chat_room_id");
        const sentMessages = {};
        let systemMessageCount = 0;

        console.groupCollapsed(`${CHAT_LOG_PREFIX} Fetching IP`);
        fetch("https://api.ipify.org?format=json")
            .then((res) => res.json())
            .then((data) => {
                console.log("🌐 Detected IP:", data.ip);
                initializeChat(data.ip);
                console.groupEnd();
            })
            .catch((err) => {
                console.error("❌ IP Fetch Error:", err);
                appendSystemMessage(
                    "Unable to get your IP address. Chat may not function."
                );
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
                body: JSON.stringify({ widget_id: widgetId, ip, user_agent: navigator.userAgent  }),
            })
                .then((res) => {
                    if (!res.ok) {
                        return res.json().then((data) => {
                            console.error("❌ Room creation failed:", data);
                            throw new Error(data.error || "Room creation failed");
                        });
                    }
                    return res.json();
                })
                .then((data) => {
                    roomId = data.room_id;
                    localStorage.setItem("chat_room_id", roomId);
                    console.log("✅ Room created with ID:", roomId);
                    connectWebSocket(roomId);
                    console.groupEnd();
                })
                .catch((err) => {
                    console.error("❌ Chat Init Failed:", err);
                    appendSystemMessage(
                        "Chat failed to start. Please refresh or try again."
                    );
                    console.groupEnd();
                });
        }

        function connectWebSocket(roomId) {
            socket = new WebSocket(`${WIDGET_CONFIG.wsUrl}${roomId}/`);

            socket.onopen = () => {
                console.log(`${CHAT_LOG_PREFIX} 🔌 WebSocket connected`);
                // Initialize file attachment handling with upload functionality
                handleFileAttachment(fileInput, socket, widgetId, chatMessages);
            };
            socket.onclose = (e) => {
                console.warn(`${CHAT_LOG_PREFIX} ⚠️ WebSocket closed:`, e);
                appendSystemMessage("Chat disconnected. Please refresh.");
            };
            socket.onerror = (e) => {
                console.error(`${CHAT_LOG_PREFIX} 🚨 WebSocket error:`, e);
                appendSystemMessage("WebSocket connection error.");
            };

            socket.onmessage = (event) => {
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
                        emojiButton.disabled = false; // Re-enable emoji button
                        fileButton.disabled = false; // Re-enable file button
                        appendSystemMessage("Form submitted. You can now chat.");
                    } else if (data.message) {
                        const sender = data.sender;
                        let className = "agent";
                        if (sender.toLowerCase() === "user") className = "user";
                        else if (
                            sender.toLowerCase() === "wish-bot" ||
                            sender.toLowerCase() === "system"
                        )
                            className = "system";

                        appendMessage(sender, data.message, className, data.message_id);

                        if (sender.toLowerCase() === "system") {
                            systemMessageCount++;
                            if (systemMessageCount === 2) {
                                formDiv.style.display = "flex"; // Use flex for form layout
                                input.disabled = true;
                                sendBtn.disabled = true;
                                emojiButton.disabled = true; // Disable emoji button
                                fileButton.disabled = true; // Disable file button
                            }
                        }

                        if (sender.toLowerCase() !== "user") {
                            socket.send(
                                JSON.stringify({
                                    status: "seen",
                                    message_id: data.message_id,
                                    sender: "User",
                                })
                            );
                        }
                    }
                } catch (e) {
                    console.error(`${CHAT_LOG_PREFIX} ❌ JSON Parse Error:`, e);
                }
                console.groupEnd();
            };
        }

        function appendMessage(sender, message, className, messageId) {
            // Prevent duplicate messages if already rendered (e.g., from echo)
            if (document.getElementById(`msg-${messageId}`)) return;

            const div = document.createElement("div");
            div.className = `message ${className}`;
            div.id = `msg-${messageId}`;

            const time = new Date().toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
            });

            div.innerHTML = `
                <div class="bubble">
                    <div class="bubble-content">${message}</div>
                    <div class="timestamp">${time}</div>
                </div>
            `;

            const wrapper = document.createElement("div");
            wrapper.className = `bubble-wrapper ${className}`;
            wrapper.appendChild(div);
            chatMessages.appendChild(wrapper);
            chatMessages.scrollTop = chatMessages.scrollHeight; // Scroll to bottom
        }

        function appendSystemMessage(msg) {
            appendMessage("System", sanitizeHTML(msg), "system", `sys-${Date.now()}`);
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
        input.addEventListener("keypress", (e) => {
            if (e.key === "Enter" && !input.disabled && !e.shiftKey) {
                // Allow Shift+Enter for new line in input
                e.preventDefault(); // Prevent default Enter behavior (new line)
                sendMessage();
            }
        });

        function sendMessage() {
            const text = input.value.trim();
            if (!text || !socket) return;
            const msgId = generateMessageId();
            socket.send(
                JSON.stringify({ message: text, sender: "User", message_id: msgId })
            );
            appendMessage("User", sanitizeHTML(text), "user", msgId);
            input.value = "";
            input.style.height = "auto"; // Reset height after sending
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        // Optional: Form Handling
        const chatForm = document.createElement("div");
        chatForm.id = "chat-form";
        chatForm.style.display = "none"; // Hidden by default
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
        // Insert the form before the chat controls section
        chatContainer.insertBefore(chatForm, chatControls);

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
            socket.send(
                JSON.stringify({
                    sender: "User",
                    form_data: { name, email },
                    message_id: msgId,
                })
            );
            appendMessage("User", `Name: ${name}, Email: ${email}`, "user", msgId);
            console.groupEnd();
        });
    }
})();