"""Trusted Aunti — demo.

The interface is the previous build's, unchanged: same theme, same illustration,
same bubbles. What changed is behind it. That version called a nine-stage graph
with five model roles and two LLM judges; this one calls

    decide  →  retrieve  →  generate  →  check

with one model call, reached only on the turns the decision layer sends to it.

Run: streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from src.conversation import Conversation
from src import config, pipeline
from src.decision import rules
from src.ui import theme

st.set_page_config(page_title="Trusted Aunti", page_icon="💛",
                   layout="centered", initial_sidebar_state="collapsed")
st.markdown(theme.css(), unsafe_allow_html=True)

#: Four openers, one per thing the corpus actually covers. Contraception and
#: HIV are the two largest tracks; access is where the Theory of Change ends;
#: and the fourth is the empowerment link the WHO evidence brief carries.
STARTERS = [
    "Can family planning make me infertile?",
    "Do condoms stop HIV too?",
    "Where can I get family planning?",
    "Will waiting help me finish school?",
]


# --- sidebar: for a reviewer, not for her -----------------------------------
with st.sidebar:
    st.caption("Demo controls")
    show_trace = st.toggle("Show how it decided", value=False)

    st.divider()
    st.caption(f"Generation · `{config.MODELS['generation']}`")
    st.caption(f"Retrieval · `{config.EMBEDDING_MODEL}`, local")
    st.caption("Decision · rules + Kenyan lexicon, no model")

    st.divider()
    if st.button("Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.conversation = Conversation()
        st.rerun()

    # The scope note lives here rather than under every message. Three
    # disclaimers on one screen say "we do not trust this" more loudly than
    # they say anything useful.
    st.caption(
        "Proof of concept, not a health service. Safeguarding examples used in "
        "evaluation are synthetic."
    )


st.markdown(theme.appbar(), unsafe_allow_html=True)
st.markdown(theme.hero(), unsafe_allow_html=True)
st.markdown(
    theme.trust_row(((" 🔒", "Privacy Lock"), ("📚", "Vetted Sources"))),
    unsafe_allow_html=True,
)

if "messages" not in st.session_state:
    st.session_state.messages = []

# The conversation the pipeline reads. Separate from `messages`, which is what
# the page draws: this one is bounded to six turns and carries the routing path
# per turn, and it is what makes "and does it hurt?" mean anything.
if "conversation" not in st.session_state:
    st.session_state.conversation = Conversation()

thread = st.container()
with thread:
    if not st.session_state.messages:
        st.markdown(
            theme.welcome_card(
                "<strong>Karibu 💛</strong> Ask me anything about contraception, "
                "staying safe, or getting to a clinic — in "
                "<strong>English, Swahili, or Sheng</strong>."
            ),
            unsafe_allow_html=True,
        )

    for i, msg in enumerate(st.session_state.messages):
        if msg["role"] == "user":
            st.markdown(theme.bubble(msg["text"], "user"), unsafe_allow_html=True)
            continue

        care = msg.get("path") == rules.SAFEGUARDING
        st.markdown(theme.bubble(msg["text"], "bot", care=care),
                    unsafe_allow_html=True)

        if msg.get("sources"):
            st.markdown(
                theme.chips([f"{s['tag']} · p.{s['page']}" for s in msg["sources"]]),
                unsafe_allow_html=True,
            )

        # Staged safeguarding: the opening arrives unprompted, the rest is
        # offered. She chooses whether to receive it, which keeps the first
        # message short enough to read while distressed.
        if msg.get("followup") and not msg.get("followup_shown"):
            if st.button("Who can help?", key=f"fu{i}", use_container_width=True):
                msg["followup_shown"] = True
                st.session_state.messages.append(
                    {"role": "bot", "text": msg["followup"],
                     "path": rules.SAFEGUARDING})
                st.rerun()

        if show_trace and msg.get("trace"):
            t = msg["trace"]
            with st.expander("How it decided", expanded=False):
                st.markdown(f"**Path** · `{t.get('path')}` — {t.get('why', '')}")
                if t.get("matched"):
                    st.caption(f"matched: {t['matched']}")
                st.markdown(
                    f"**Cost** · {t.get('llm_calls', 0)} LLM call"
                    f"{'' if t.get('llm_calls') == 1 else 's'} · "
                    f"{t.get('latency_ms', 0)} ms"
                )
                for r in t.get("retrieved", []):
                    st.caption(
                        f"{r['similarity']:.3f} · {r['tag']} p.{r['page']} · "
                        f"{r['role']} · {r['section'][:56]}"
                    )
                if t.get("issues"):
                    st.markdown("**Checks**")
                    for issue in t["issues"]:
                        st.caption(f"– {issue}")
                if t.get("insufficient"):
                    st.caption("generator declared the passages insufficient")
                if t.get("error"):
                    st.caption(f"error: {t['error']}")


# --- starters ---------------------------------------------------------------
if not st.session_state.messages:
    st.markdown('<div class="starters"></div>', unsafe_allow_html=True)
    for row in (0, 2):
        cols = st.columns(2)
        for offset in (0, 1):
            i = row + offset
            if cols[offset].button(STARTERS[i], key=f"s{i}",
                                   use_container_width=True):
                st.session_state.pending = STARTERS[i]
                st.rerun()


# --- input ------------------------------------------------------------------
typed = st.chat_input("Ask safely in English, Swahili, or Sheng…")
message = typed or st.session_state.pop("pending", None)

if message:
    st.session_state.messages.append({"role": "user", "text": message})
    with st.spinner(" "):
        reply = pipeline.answer(
            message, conversation=st.session_state.conversation)
    st.session_state.messages.append({
        "role": "bot",
        "text": reply.text,
        "path": reply.path,
        "sources": reply.sources,
        "followup": reply.followup,
        "trace": reply.trace,
    })
    st.rerun()
