import datetime
import json
import os

import streamlit as st

from src.assistant import chat_api_call, execute_tool_call

CHATS_DIR = "chats"

MODELS = {
    "Nemotron Nano 30B (fast)": "nvidia/nemotron-3-nano-30b-a3b:free",
    "Nemotron Super 120B (higher quality)": "nvidia/nemotron-3-super-120b-a12b:free",
    "Gemma 4 31B (Google, free)": "google/gemma-4-31b-it:free",
}

st.set_page_config(page_title="JARVIS", page_icon="🤖")

# Sharp minimalist grayscale theme, from the "Sharp minimalistic Streamlit UI"
# design (claude.ai/design project) - layout variant 1a "classic sidebar"
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

html, body, [class*="st-"] { font-family: 'Space Grotesk', sans-serif; }
* { border-radius: 0 !important; }

/* keep Streamlit's icon font working (icons render as ligatures) */
[data-testid="stIconMaterial"], [class*="material-symbols"] {
    font-family: 'Material Symbols Rounded' !important;
}

[data-testid="stAppViewContainer"] { background: #0d0d0f; }
[data-testid="stHeader"] { background: #0d0d0f; }
[data-testid="stSidebar"] { background: #111113; border-right: 1px solid #1e1e22; }

/* mono uppercase widget labels */
[data-testid="stWidgetLabel"] p {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    letter-spacing: .08em;
    text-transform: uppercase;
    color: #8a8a90 !important;
}

/* buttons: sharp, hairline border, mono */
.stButton > button {
    background: #17171a;
    border: 1px solid #35353b;
    color: #c8c8cc;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    font-weight: 600;
}
.stButton > button:hover {
    border-color: #e8e8ea;
    color: #e8e8ea;
    background: #17171a;
}
[data-testid="stSidebar"] .stButton > button { justify-content: flex-start; }

/* inputs and selects: dark well with hairline border */
[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
[data-testid="stTextInput"] div[data-baseweb="input"],
[data-testid="stChatInput"] {
    background: #0b0b0d;
    border: 1px solid #35353b;
}
[data-testid="stChatInput"] textarea { background: transparent; }

/* chat messages: bordered cards, no avatars */
[data-testid="stChatMessage"] {
    background: #111113;
    border: 1px solid #26262b;
    padding: 16px 18px;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background: #141416;
}
[data-testid="stChatMessage"] [data-testid*="stChatMessageAvatar"] { display: none; }

/* tool results (st.info) and errors: flat bordered strips */
[data-testid="stAlert"] {
    background: #0b0b0d;
    border: 1px solid #26262b;
    color: #c8c8cc;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
}

/* captions (tool calls, chat dates): small mono */
[data-testid="stCaptionContainer"] {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px !important;
    letter-spacing: .06em;
    color: #66666c !important;
}

::selection { background: #3a3a40; color: #fff; }
</style>
""",
    unsafe_allow_html=True,
)

EYEBROW = (
    "font:600 11px 'JetBrains Mono',monospace; letter-spacing:.16em; "
    "text-transform:uppercase; color:#66666c; margin-bottom:6px;"
)


def load_all_chats():
    if not os.path.isdir(CHATS_DIR):
        return []
    chats = []
    for filename in os.listdir(CHATS_DIR):
        if filename.endswith(".json"):
            try:
                with open(os.path.join(CHATS_DIR, filename), encoding="utf-8") as f:
                    chats.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                continue  # skip corrupt files rather than breaking the sidebar
    chats.sort(key=lambda c: c.get("created_at", ""), reverse=True)
    return chats


def save_current_chat():
    history = st.session_state.conversation_history
    if not history:
        return
    if st.session_state.chat_id is None:
        now = datetime.datetime.now()
        st.session_state.chat_id = now.strftime("%Y%m%d_%H%M%S_%f")
        st.session_state.chat_created_at = now.isoformat(timespec="seconds")
        first_user_msg = next(
            (m["content"] for m in history if m.get("role") == "user"), "New chat"
        )
        title = first_user_msg.strip()
        st.session_state.chat_title = title[:40] + ("…" if len(title) > 40 else "")
    os.makedirs(CHATS_DIR, exist_ok=True)
    chat = {
        "id": st.session_state.chat_id,
        "title": st.session_state.chat_title,
        "messages": history,
        "created_at": st.session_state.chat_created_at,
    }
    path = os.path.join(CHATS_DIR, f"{st.session_state.chat_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(chat, f, ensure_ascii=False, indent=1)


def chat_matches(chat, query):
    query = query.lower()
    if query in chat.get("title", "").lower():
        return True
    return any(query in str(m.get("content") or "").lower() for m in chat["messages"])


def start_new_chat():
    st.session_state.conversation_history = []
    st.session_state.chat_id = None
    st.session_state.chat_title = None
    st.session_state.chat_created_at = None


if "conversation_history" not in st.session_state:
    start_new_chat()

# --- Sidebar: new chat, search, saved chat list ---
with st.sidebar:
    st.markdown(
        '<div style="display:flex; align-items:center; gap:11px; margin:4px 0 14px;">'
        '<span style="width:22px; height:22px; border:1px solid #4a4a52; display:flex; '
        "align-items:center; justify-content:center; font:700 12px 'JetBrains Mono',monospace; "
        'color:#e8e8ea;">J</span>'
        '<span style="font:600 14px \'Space Grotesk\',sans-serif; letter-spacing:.14em; '
        'color:#e8e8ea;">JARVIS</span></div>'
        '<div style="height:1px; background:#1e1e22; margin-bottom:18px;"></div>',
        unsafe_allow_html=True,
    )

    model_label = st.selectbox("Model", list(MODELS.keys()), index=0)
    st.session_state.model = MODELS[model_label]

    st.markdown(f'<div style="{EYEBROW} margin-top:18px;">Chats</div>', unsafe_allow_html=True)
    if st.button("+ New Chat", use_container_width=True):
        start_new_chat()
        st.rerun()

    search = st.text_input("Search chats", placeholder="Search...")

    for chat in load_all_chats():
        if search and not chat_matches(chat, search):
            continue
        is_current = chat["id"] == st.session_state.chat_id
        label = ("● " if is_current else "") + chat["title"]
        if st.button(label, key=f"chat_{chat['id']}", use_container_width=True):
            st.session_state.conversation_history = chat["messages"]
            st.session_state.chat_id = chat["id"]
            st.session_state.chat_title = chat["title"]
            st.session_state.chat_created_at = chat["created_at"]
            st.rerun()
        st.caption(chat["created_at"].replace("T", " "))

# --- Main chat area (unchanged behavior) ---
st.markdown(
    f'<div style="{EYEBROW}">assistant / jarvis.py</div>'
    '<div style="font:600 26px/1 \'Space Grotesk\',sans-serif; color:#f2f2f4; '
    'margin-bottom:24px;">JARVIS</div>',
    unsafe_allow_html=True,
)


def render_message(msg):
    role = msg.get("role")
    if role == "user":
        with st.chat_message("user"):
            st.write(msg["content"])
    elif role == "assistant":
        with st.chat_message("assistant"):
            for call in msg.get("tool_calls") or []:
                st.caption(f"🔧 Calling {call['function']['name']}({call['function']['arguments']})")
            if msg.get("content"):
                st.write(msg["content"])
    elif role == "tool":
        with st.chat_message("assistant"):
            st.info(msg["content"])


# replay the whole conversation on every rerun
for msg in st.session_state.conversation_history:
    render_message(msg)

if user_input := st.chat_input("Ask me anything..."):
    history = st.session_state.conversation_history
    history.append({"role": "user", "content": user_input})
    render_message(history[-1])
    save_current_chat()

    with st.spinner("Thinking..."):
        message, error = chat_api_call(history, model=st.session_state.model)

    if error:
        history.pop()  # drop the failed turn so a retry starts clean
        save_current_chat()
        st.error(error)
    else:
        history.append(message)
        render_message(message)

        for call in message.get("tool_calls") or []:
            output = execute_tool_call(call)
            tool_msg = {
                "role": "tool",
                "tool_call_id": call["id"],
                "name": call["function"]["name"],
                "content": str(output),
            }
            history.append(tool_msg)
            render_message(tool_msg)

        save_current_chat()
        st.rerun()  # refresh so a brand-new chat shows up in the sidebar immediately
