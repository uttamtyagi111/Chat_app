
// ✅ Merged chat widget with bubble + modal + WebSocket init support
// ✅ Fully self-contained and ready for injection into any site

(function initChatWidget() {
  // Extract widget_id from script tag URL
  let scriptSrc;
  if (document.currentScript && document.currentScript.src) {
    scriptSrc = document.currentScript.src;
  } else {
    const scripts = document.getElementsByTagName("script");
    const script = Array.from(scripts).find((s) => s.src.includes("chat_widget.js"));
    if (script) {
      scriptSrc = script.src;
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

  // === Configuration ===
  const isLocal = location.hostname === "localhost" || location.hostname === "127.0.0.1";
  const CONFIG = {
    apiUrl: isLocal ? "http://localhost:8000/chat/user-chat/" : "http://your-server/chat/user-chat/",
    wsUrl: isLocal ? "ws://localhost:8000/ws/chat/" : "ws://your-server/ws/chat/",
    fileUploadUrl: isLocal ? "http://localhost:8000/chat/user-chat/upload-file/" : "http://your-server/chat/user-chat/upload-file/",
    themeColor: document.currentScript.getAttribute("data-theme-color") || "#10B981",
    logoUrl: document.currentScript.getAttribute("data-logo-url") || "",
    position: document.currentScript.getAttribute("data-position") || "right",
  };

  // === Inject bubble only ===
  const bubble = document.createElement("div");
  bubble.id = "chat-bubble";
  Object.assign(bubble.style, {
    position: "fixed",
    bottom: "20px",
    [CONFIG.position]: "20px",
    backgroundColor: CONFIG.themeColor,
    borderRadius: "50%",
    width: "60px",
    height: "60px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
    cursor: "pointer",
    zIndex: "9999"
  });

  if (CONFIG.logoUrl) {
    const img = document.createElement("img");
    img.src = CONFIG.logoUrl;
    img.alt = "Chat Logo";
    Object.assign(img.style, {
      width: "60%",
      height: "60%",
      objectFit: "contain"
    });
    bubble.appendChild(img);
  } else {
    bubble.textContent = "💬";
    bubble.style.fontSize = "24px";
    bubble.style.color = "#fff";
  }
  document.body.appendChild(bubble);

  // === Defer modal + logic load until bubble clicked ===
  bubble.addEventListener("click", function () {
    if (document.getElementById("chat-window")) {
      document.getElementById("chat-window").style.display = "flex";
      return;
    }

    const script = document.createElement("script");
    script.src = "http://localhost:8000/static/js/chat_widget.js?widget_id=" + widgetId;
    script.async = true;
    script.setAttribute("data-theme-color", CONFIG.themeColor);
    script.setAttribute("data-logo-url", CONFIG.logoUrl);
    document.body.appendChild(script);
  });
})();
