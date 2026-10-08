import { useEffect, useRef, useState } from "react";
import { sendChatMessage } from "../api.js";

const SESSION_STORAGE_KEY = "reviewerfinder.chatSessionId";

export default function ChatPage() {
  const [sessionId, setSessionId] = useState(() => localStorage.getItem(SESSION_STORAGE_KEY));
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);

  const threadEndRef = useRef(null);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSubmit(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || sending) return;

    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");
    setSending(true);
    setError(null);

    try {
      const resp = await sendChatMessage(sessionId, text);
      setSessionId(resp.session_id);
      localStorage.setItem(SESSION_STORAGE_KEY, resp.session_id);
      setMessages((m) => [...m, { role: "assistant", content: resp.reply }]);
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  }

  function handleNewConversation() {
    localStorage.removeItem(SESSION_STORAGE_KEY);
    setSessionId(null);
    setMessages([]);
    setError(null);
  }

  return (
    <main className="page">
      <div className="eyebrow">Ask about stored papers &amp; scholars</div>
      <h1>Chat</h1>
      <p className="page-lede">
        Answers questions about papers and scholars already stored by ScholarFinder, using tools
        that look up your data directly (exact/fuzzy name or title lookup, eligibility re-checks
        against the same deterministic rule engine the search pipeline uses). It does not
        semantically search across paper text by meaning — only by these specific lookups.
      </p>

      <div className="chat-thread">
        {messages.length === 0 && (
          <div className="empty-state">
            Try: "is scholar A123456789 fit to review paper 3?" or "list the top candidates for
            paper 1".
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`chat-bubble ${m.role}`}>
            <span className="chat-bubble-role">{m.role === "user" ? "you" : "assistant"}</span>
            <p>{m.content}</p>
          </div>
        ))}
        {sending && (
          <div className="loading-line">
            <span className="spinner" aria-hidden="true" />
            Thinking…
          </div>
        )}
        <div ref={threadEndRef} />
      </div>

      {error && <div className="banner error">{error}</div>}

      <form className="chat-input-row" onSubmit={handleSubmit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question…"
          disabled={sending}
        />
        <button type="submit" className="btn" disabled={sending || !input.trim()}>
          Send
        </button>
      </form>

      <p className="chat-footnote">
        <button type="button" className="btn secondary small" onClick={handleNewConversation}>
          New conversation
        </button>{" "}
        Starts a new conversation thread; previous ones are not deleted.
      </p>
    </main>
  );
}
