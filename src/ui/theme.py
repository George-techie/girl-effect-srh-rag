"""Chat UI styling and brand assets.

Kept separate from application logic so the visual design can be reworked
without touching how the system behaves. Colours are named tokens — restyling
means editing `TOKENS`, not hunting through CSS.

Design intent, which matters more than the palette:

* **Phone-shaped, not desktop.** Girl Effect ships to WhatsApp, MoyaApp and
  Telegram. A demo in a desktop web form misrepresents the product; a narrow
  column with a real message thread is what a user actually experiences.
* **Safeguarding responses look different.** A disclosure receiving identical
  visual treatment to a period question would be wrong. The support response
  gets its own warmer surface — a visible change of register. Deliberately not
  red: red reads as an error, and an error state is the wrong thing to show
  someone who has just told you they are being hurt.
* **Sources present, not shouted.** Trust comes from citations being available,
  not from burying the answer under attribution.
* **A visible proof-of-concept marker.** The interface carries Girl Effect
  branding, so it states plainly that it is a prototype. A screenshot taken out
  of context should not be mistakable for a live service.
"""

from __future__ import annotations

import base64
import html
import re
from functools import lru_cache
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent.parent / "assets"

# Palette taken from the Girl Effect primary mark: maroon with the amber that
# appears in their secondary lockup.
TOKENS = {
    # Surfaces
    "page_bg": "#F3F4F6",
    "phone_bg": "#FFFFFF",
    "header_bg": "#57273F",
    "header_ink": "#FFFFFF",

    # Bubbles
    "bot_bubble": "#FFFFFF",
    "bot_ink": "#1F1F23",
    "user_bubble": "#57273F",
    "user_ink": "#FFFFFF",

    # Safeguarding — warm, not alarming.
    "care_bubble": "#FDF6EC",
    "care_border": "#D89A2E",
    "care_ink": "#3E2F1C",

    # Suggested replies. Same amber family as the safeguarding bubble, one step
    # warmer so they read as something to tap rather than something to read.
    #
    # Plain white made them look like empty input fields sitting under a white
    # answer bubble — the one element on screen that is an invitation was the
    # least visible thing on it. The whole point of offering them is the girl who
    # is not sure she is allowed to ask a second question.
    "reply_bg": "#FCF1DC",
    "reply_bg_hover": "#F8E6C2",
    "reply_border": "#E6BC6A",
    "reply_ink": "#57273F",

    # Support
    "amber": "#F5A623",
    "muted": "#6B6B72",
    "line": "#E2DCD8",
    "chip_bg": "#F1ECF0",
    "chip_ink": "#57273F",

    # App chrome. The accent is the deep teal from the approved mockup —
    # Girl Effect's secondary, and the colour that carries the whole screen.
    # The maroon stays where it already earns its place: the user's own bubbles
    # and the safeguarding surface.
    "bar_bg": "#FFFFFF",
    "bar_ink": "#1F2937",
    "teal": "#004B5B",
    "teal_deep": "#003A47",
    "teal_soft": "#E6F3F5",
    "teal_line": "#B2DDE2",
    "hairline": "#E5E7EB",
    "avatar_bg": "#F8D57E",

    # Starter tiles. Four distinct pastels, because one colour repeated four
    # times reads as a form and four colours read as a choice. Nudged toward the
    # Girl Effect palette — the amber and coral are already the brand's, and the
    # mint and pink are their cool counterweights.
    "tile_teal": "#004B5B",
    "tile_amber": "#E09F3E",
    "tile_coral": "#F08A7A",
    "tile_mint": "#A9CFC4",
    "tile_ink": "#22303A",
}


@lru_cache(maxsize=8)
def asset_data_uri(filename: str) -> str | None:
    """Inline an asset as a data URI.

    Streamlit's HTML blocks cannot reference local files, so assets are
    embedded. Returns None when the file is absent, and every caller degrades
    gracefully rather than rendering a broken image.
    """
    path = ASSETS / filename
    if not path.exists():
        return None
    suffix = path.suffix.lower()
    mime = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".svg": "image/svg+xml",
    }.get(suffix, "image/png")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def find_hero() -> str | None:
    """The hero photograph, whatever extension it was saved with."""
    for name in ("hero_girls.jpg", "hero_girls.jpeg", "hero_girls.png",
                 "hero_girls.webp"):
        uri = asset_data_uri(name)
        if uri:
            return uri
    return None


def css() -> str:
    t = TOKENS
    return f"""
<style>
  .stApp {{ background: {t['page_bg']}; }}
  #MainMenu, footer, header {{ visibility: hidden; }}

  /* The message surface lives on the container itself. An inner wrapper div
     cannot work here: Streamlit renders each st.markdown call as its own
     element, so a div opened in one call and closed in another is auto-closed
     immediately, leaving an empty styled box between the hero and the thread. */
  .block-container {{
    max-width: 480px;
    padding: 1.5rem 1rem 3rem !important;
    margin: 0 auto;
    background: {t['phone_bg']};
  }}

  /* Streamlit inserts a gap between every vertical block. At default spacing
     that reads as a paragraph break between chat bubbles rather than a thread. */
  .block-container [data-testid="stVerticalBlock"] {{ gap: .35rem !important; }}

  /* ---- brand header ----------------------------------------------------
     A hairline-ruled row rather than a filled bar: the brand states itself and
     the rule closes it, which leaves the artwork below as the first coloured
     thing on the screen instead of the second. */
  .brand-header {{
    display: flex; align-items: center; justify-content: space-between;
    padding-bottom: 10px;
    border-bottom: 1px solid {t['hairline']};
    margin-bottom: 15px;
  }}
  .brand-logo {{
    display: flex; align-items: center; gap: 8px;
    font-weight: 700; font-size: 1.2rem;
    color: {t['teal']};
  }}
  .brand-logo img {{ height: 22px; width: auto; display: block; }}
  .status-badge {{
    background: {t['teal']}; color: #fff;
    font-size: .75rem; font-weight: 600;
    padding: 4px 10px; border-radius: 12px;
    white-space: nowrap;
  }}

  /* ---- hero ------------------------------------------------------------
     Uncropped. `height: auto` lets the illustration keep its own proportions
     instead of being cut to a banner — the artwork is the warmest thing on the
     screen and there is no reason to lose a third of it. */
  .hero-container {{
    width: 100%;
    border-radius: 16px;
    overflow: hidden;
    margin-bottom: 16px;
    box-shadow: 0 4px 12px rgba(0,0,0,.08);
    line-height: 0;
  }}
  .hero-container img {{ width: 100%; height: auto; display: block; }}

  /* ---- privacy badges --------------------------------------------------- */
  .badge-bar {{ display: flex; gap: 10px; margin-bottom: 18px; }}
  .privacy-badge {{
    flex: 1;
    background: {t['teal_soft']};
    color: {t['teal']};
    border: 1px solid {t['teal_line']};
    padding: 8px 12px; border-radius: 20px;
    font-size: .85rem; font-weight: 600;
    display: flex; align-items: center; justify-content: center; gap: 6px;
  }}

  /* ---- welcome card ----------------------------------------------------- */
  .welcome-card {{
    background: #fff;
    border: 1px solid {t['hairline']};
    border-radius: 16px;
    padding: 16px; margin-bottom: 20px;
    box-shadow: 0 2px 6px rgba(0,0,0,.04);
    display: flex; gap: 12px;
  }}
  .avatar-circle {{
    width: 40px; height: 40px; flex-shrink: 0;
    border-radius: 50%;
    background: {t['avatar_bg']};
    display: flex; align-items: center; justify-content: center;
    font-size: 1.2rem;
  }}
  .welcome-text {{
    font-size: .95rem; color: {t['bar_ink']}; line-height: 1.4;
  }}

  /* ---- thread --------------------------------------------------------- */
  .strip {{ height: 4px; background: linear-gradient(90deg,
    {t['amber']} 0%, #E8734A 52%, {t['header_bg']} 100%); }}

  /* Bubbles carry their own horizontal inset, so no wrapper is needed. */
  .row {{ display: flex; margin: 0 12px 10px; }}
  .row.user {{ justify-content: flex-end; }}
  .row.bot {{ align-items: flex-end; }}
  .row:first-of-type {{ margin-top: 15px; }}

  /* Her face beside her words. Without it a reply is text from a system; with
     it there is someone at the other end, which is the whole point of naming
     her. Aligned to the bottom of the bubble so a long answer does not leave
     the avatar floating beside its first line. */
  .avatar {{
    width: 30px; height: 30px; flex: 0 0 30px;
    margin: 0 8px 1px 0;
  }}
  .avatar svg {{
    width: 100%; height: 100%; display: block;
    filter: drop-shadow(0 1px 2px rgba(87,39,63,.20));
  }}

  .bubble {{
    max-width: 84%;
    padding: 10px 13px;
    border-radius: 16px;
    font-size: 14.5px;
    line-height: 1.5;
    word-wrap: break-word;
    box-shadow: 0 1px 1.5px rgba(0,0,0,.07);
  }}
  /* Paragraphs are real elements with tight margins. Using pre-wrap on the
     whole bubble rendered the blank line between paragraphs as a full empty
     line, which left large gaps in the longer support responses. */
  .bubble p {{ margin: 0 0 8px; }}
  .bubble p:last-child {{ margin-bottom: 0; }}
  /* Numbered options. The number sits outside the text column so the wrapped
     second line aligns under the words rather than under the digit — on a
     narrow phone bubble almost every item wraps, and hanging indentation is
     what keeps the list scannable once they do. */
  .bubble ol {{ margin: 0 0 8px; padding-left: 1.25em; }}
  .bubble ol:last-child {{ margin-bottom: 0; }}
  .bubble li {{ margin: 0 0 7px; padding-left: .15em; }}
  .bubble li:last-child {{ margin-bottom: 0; }}
  .bubble li::marker {{ font-weight: 700; color: {t['teal']}; }}
  .bubble strong {{ font-weight: 700; }}

  .bubble.bot  {{ background: {t['bot_bubble']};  color: {t['bot_ink']};  border-bottom-left-radius: 5px; }}
  .bubble.user {{ background: {t['user_bubble']}; color: {t['user_ink']}; border-bottom-right-radius: 5px; }}

  .bubble.care {{
    background: {t['care_bubble']};
    color: {t['care_ink']};
    border: 1px solid {t['care_border']};
    border-left: 3px solid {t['care_border']};
    border-bottom-left-radius: 5px;
    max-width: 92%;
  }}
  .care-label {{
    font-size: 10px; font-weight: 700; letter-spacing: .7px;
    text-transform: uppercase; color: #A8721F;
    margin-bottom: 6px;
  }}

  /* ---- sources -------------------------------------------------------- */
  .sources {{ margin: -4px 12px 12px 16px; display: flex; flex-wrap: wrap; gap: 4px; }}
  .chip {{
    background: {t['chip_bg']}; color: {t['chip_ink']};
    font-size: 10.5px; padding: 3px 8px; border-radius: 10px;
    border: 1px solid {t['line']};
  }}

  /* ---- suggested replies ---------------------------------------------- */
  /* Every tappable suggestion in the thread: conversation quick replies, the
     opening starters, and the staged safeguarding follow-ups. Deliberately one
     style for all three — they are the same gesture, and a girl should not have
     to learn that this amber pill continues the conversation while that white
     one does something else.

     Scoped to .block-container so the sidebar's developer controls keep
     Streamlit's default chrome and stay visibly not part of the product. */
  /* Three selectors for one thing, deliberately. Streamlit renames its internal
     hooks between releases — 1.58 moved the button's test id from
     `stButton` to `stBaseButton-secondary` — and a chat whose suggested replies
     silently revert to plain white on a minor version bump is worse than a
     slightly redundant rule. `!important` for the same reason: the emotion
     classes Streamlit generates are hashed per build, so specificity is not
     something this stylesheet can reason about. */
  .block-container [data-testid="stButton"] button,
  .block-container .stButton button,
  .block-container button[data-testid^="stBaseButton"] {{
    background: {t['reply_bg']} !important;
    color: {t['reply_ink']} !important;
    border: 1px solid {t['reply_border']} !important;
    border-radius: 18px !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    line-height: 1.35 !important;
    padding: 7px 12px !important;
    min-height: 38px;
    white-space: normal !important;   /* wrap, not clip — Sheng labels run long */
    box-shadow: 0 1px 1.5px rgba(0,0,0,.05);
    transition: background .12s ease, border-color .12s ease;
  }}
  .block-container [data-testid="stButton"] button:hover,
  .block-container .stButton button:hover,
  .block-container button[data-testid^="stBaseButton"]:hover {{
    background: {t['reply_bg_hover']} !important;
    border-color: {t['care_border']} !important;
    color: {t['reply_ink']} !important;
  }}
  .block-container [data-testid="stButton"] button:focus:not(:active),
  .block-container .stButton button:focus:not(:active),
  .block-container button[data-testid^="stBaseButton"]:focus:not(:active) {{
    border-color: {t['care_border']} !important;
    color: {t['reply_ink']} !important;
    box-shadow: 0 0 0 2px rgba(216,154,46,.28) !important;
  }}
  .block-container [data-testid="stButton"] button:active,
  .block-container .stButton button:active,
  .block-container button[data-testid^="stBaseButton"]:active {{
    background: {t['care_border']} !important;
    border-color: {t['care_border']} !important;
    color: #fff !important;
  }}
  /* Streamlit wraps the label in its own markdown container, which sets its own
     colour and would otherwise win over the button's. */
  .block-container [data-testid="stButton"] button p,
  .block-container .stButton button p,
  .block-container button[data-testid^="stBaseButton"] p {{
    color: inherit !important;
    font-size: inherit !important;
    font-weight: inherit !important;
    margin: 0;
  }}

  /* The global gap:0 that makes bubbles read as one thread also welds the
     reply buttons together. Columns get their spacing back. */
  .block-container [data-testid="stHorizontalBlock"] {{
    gap: 6px !important;
    margin: 0 12px 10px;
  }}

  /* ---- starter tiles ----------------------------------------------------
     Two colours by column rather than four by position: teal on the left,
     amber on the right. Column-based means it survives a Streamlit change that
     renumbers rows, which the previous position-based version would not. */
  .starters {{ height: 0; margin: 0; padding: 0; }}

  .starters ~ [data-testid="stHorizontalBlock"] button {{
    width: 100%;
    border-radius: 14px !important;
    padding: 12px 14px !important;
    font-weight: 600 !important;
    font-size: .9rem !important;
    border: none !important;
    box-shadow: 0 2px 4px rgba(0,0,0,.05) !important;
    transition: all .2s ease;
  }}
  .starters ~ [data-testid="stHorizontalBlock"]
    div[data-testid="column"]:nth-child(1) button {{
      background: {t['tile_teal']} !important; color: #fff !important; }}
  .starters ~ [data-testid="stHorizontalBlock"]
    div[data-testid="column"]:nth-child(2) button {{
      background: {t['tile_amber']} !important; color: #fff !important; }}
  .starters ~ [data-testid="stHorizontalBlock"] button p {{
    color: inherit !important; font-size: inherit !important;
    font-weight: inherit !important;
  }}
  .starters ~ [data-testid="stHorizontalBlock"] button:hover {{
    filter: brightness(1.08); color: #fff !important;
  }}

  /* ---- input ------------------------------------------------------------ */
  .stChatInput textarea::placeholder {{ color: #9AA5AC !important; }}
  /* Teal send button, as the mockup has it — the one control on the input row
     and the only place the eye needs to land. */
  .stChatInput button {{
    background: {t['teal']} !important;
    border-radius: 10px !important;
    color: #fff !important;
  }}

  .disclaimer {{
    font-size: 10.5px; color: {t['muted']}; text-align: center;
    padding: 10px 20px 4px; line-height: 1.45;
  }}
  .disclaimer strong {{ color: {t['header_bg']}; }}

  .stChatInput {{ max-width: 480px; margin: 0 auto; border-radius: 24px; }}
  .stChatInput textarea {{ font-size: 14.5px !important; }}

  /* --- typing indicator ----------------------------------------------------
     Three dots that rise in sequence. Deliberately slow — a fast bounce reads
     as a loading spinner, a slow one reads as somebody thinking. */
  .bubble.typing {{
    display: inline-flex; align-items: center; gap: 5px;
    padding-top: 16px; padding-bottom: 16px;
  }}
  .bubble.typing .dot {{
    width: 7px; height: 7px; border-radius: 50%;
    background: currentColor; opacity: .35;
    animation: aunti-typing 1.25s ease-in-out infinite;
  }}
  .bubble.typing .dot:nth-child(2) {{ animation-delay: .18s; }}
  .bubble.typing .dot:nth-child(3) {{ animation-delay: .36s; }}
  @keyframes aunti-typing {{
    0%, 70%, 100% {{ transform: translateY(0);    opacity: .3; }}
    35%           {{ transform: translateY(-4px); opacity: .8; }}
  }}

  /* The cursor on a reply that is still arriving. */
  .caret {{
    display: inline-block; width: 2px; height: 1em; margin-left: 2px;
    background: currentColor; opacity: .55; vertical-align: -0.15em;
    animation: aunti-caret 1s steps(2, start) infinite;
  }}
  @keyframes aunti-caret {{
    0%, 50% {{ opacity: .55; }} 50.01%, 100% {{ opacity: 0; }}
  }}

  @media (prefers-reduced-motion: reduce) {{
    .bubble.typing .dot, .caret {{ animation: none; opacity: .5; }}
  }}
</style>
"""


#: The persona, as she is named on screen. Kept here rather than in app.py so the
#: display name has one source — it appears in the masthead, on the opening
#: bubble and in the page title, and three copies would eventually disagree.
PERSONA_NAME = "Trusted Aunti"

#: Button labels that mean "show me the contacts", in every register they are
#: offered in. Matched by exact string because these are labels the product
#: writes, not text the user typed — so there is nothing to interpret.
SERVICE_ACTIONS = frozenset({
    "Talk to someone", "Ongea na mtu",
    "Talk to a professional", "Ongea na professional",
    "Who can help?", "Ni nani anaweza saidia?",
    "Who can I talk to?", "Ni nani naweza ongea naye?",
})
PERSONA_MARK = "💛"

#: Trusted Aunti, drawn rather than photographed.
#:
#: Inline SVG rather than an image file for three reasons: it needs no asset to
#: ship or licence, it scales without blurring on any screen, and it recolours
#: from the same palette as everything else — so the avatar cannot drift out of
#: brand the way a dropped-in PNG does.
#:
#: Deliberately illustrated and deliberately not photoreal. A photograph of a
#: specific woman implies a specific person is reading, which is the one thing
#: this service must not imply. A drawing reads as a character, and a character
#: is what she is.
PERSONA_AVATAR = """
<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Trusted Aunti">
  <defs>
    <clipPath id="ta-clip"><circle cx="32" cy="32" r="31"/></clipPath>
    <linearGradient id="ta-bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#F6C96B"/><stop offset="100%" stop-color="#E8A93C"/>
    </linearGradient>
  </defs>
  <g clip-path="url(#ta-clip)">
    <rect width="64" height="64" fill="url(#ta-bg)"/>
    <path d="M11 27c0-13 9-21 21-21s21 8 21 21c0 3-1 5-3 5-3-6-9-10-18-10s-15 4-18 10c-2 0-3-2-3-5z" fill="#57273F"/>
    <path d="M46 12c5 2 8 6 9 10-3-1-6-4-9-10z" fill="#7A3A57"/>
    <path d="M20 28c0-7 5-12 12-12s12 5 12 12v6c0 7-5 13-12 13s-12-6-12-13z" fill="#8D5524"/>
    <ellipse cx="27" cy="33" rx="1.9" ry="2.2" fill="#2B1810"/>
    <ellipse cx="37" cy="33" rx="1.9" ry="2.2" fill="#2B1810"/>
    <circle cx="27.7" cy="32.3" r=".7" fill="#fff" opacity=".9"/>
    <circle cx="37.7" cy="32.3" r=".7" fill="#fff" opacity=".9"/>
    <path d="M27 39.5c1.6 1.8 3.1 2.6 5 2.6s3.4-.8 5-2.6" stroke="#2B1810" stroke-width="1.7" stroke-linecap="round" fill="none"/>
    <path d="M12 64c1-9 9-14 20-14s19 5 20 14z" fill="#B4543A"/>
    <path d="M32 50c-2 4-4 6-6 7 2 4 10 4 12 0-2-1-4-3-6-7z" fill="#FBF8F6"/>
  </g>
  <circle cx="32" cy="32" r="30.5" fill="none" stroke="rgba(87,39,63,.22)" stroke-width="1.5"/>
</svg>
"""



def appbar(trust: str = "Vetted. Privacy-First.") -> str:
    """Brand row: mark, name, trust badge, closed by a hairline."""
    logo = asset_data_uri("girl_effect_mark.png") or asset_data_uri(
        "girl_effect_logo.png")
    mark = f'<img src="{logo}" alt="Girl Effect">' if logo else "🌐"
    return f"""
    <div class="brand-header">
      <div class="brand-logo">{mark} &#129293; {html.escape(PERSONA_NAME)}</div>
      <div class="status-badge">{html.escape(trust)}</div>
    </div>
    """


def hero() -> str:
    """The artwork, uncropped.

    `height: auto` rather than a fixed banner height. The illustration is the
    warmest thing on the screen and there is no reason to cut a third of it off
    to make a header shape.
    """
    photo = find_hero()
    if not photo:
        return ""
    return (
        '<div class="hero-container">'
        f'<img src="{photo}" alt="Trusted Aunti community illustration">'
        "</div>"
    )


def trust_row(items: tuple[tuple[str, str], ...]) -> str:
    """Privacy and provenance, stated before she types rather than after."""
    badges = "".join(
        f'<div class="privacy-badge">{ico} {html.escape(label)}</div>'
        for ico, label in items
    )
    return f'<div class="badge-bar">{badges}</div>'


def welcome_card(text_html: str, avatar: str = "👩🏾") -> str:
    """The opening message, as a card rather than a chat bubble.

    `text_html` is trusted markup — it is authored here, not user input, and it
    carries the emphasis the line needs.
    """
    return f"""
    <div class="welcome-card">
      <div class="avatar-circle">{avatar}</div>
      <div class="welcome-text">{text_html}</div>
    </div>
    """


_BOLD = re.compile(r"\*\*(\S.*?)\*\*", re.S)

#: A list item, either numbered or dashed. Numbered is what the prompt now asks
#: for; the dash form stays recognised because older turns still in a thread were
#: written before that instruction existed.
_ITEM = re.compile(r"^\s*(?:\d+[.)]|[-•*])\s+(.*)$")


def _paragraphs(text: str) -> list[str]:
    """Split into blocks, keeping a numbered list together as one block.

    Models put a blank line between list items, which is correct markdown and
    was being read here as three separate paragraphs. Each became its own
    ``<ol>``, so a three-item list rendered as **1. 1. 1.** — she sees the
    system cannot count, in the middle of an answer about contraception.

    Consecutive item blocks are merged so the list is numbered once.
    """
    blocks = [p.strip() for p in text.split("\n\n") if p.strip()]
    merged: list[str] = []
    for block in blocks:
        starts_item = bool(_ITEM.match(block.splitlines()[0]))
        previous_ends_item = bool(
            merged and _ITEM.match(merged[-1].splitlines()[-1]))
        if starts_item and previous_ends_item:
            merged[-1] += "\n" + block
        else:
            merged.append(block)
    return merged


def _inline(text: str) -> str:
    """Escape, then honour the one piece of markdown the system actually emits.

    Bubbles are raw HTML, so Streamlit never runs its markdown pass over them and
    ``**Mama Siri**`` reached the screen with the asterisks showing. The service
    card is where it matters most: the organisation name is the thing she scans
    for in a crisis, and it was the one word rendered as punctuation.

    Escape first, convert second. The only tags in the output are the ones
    written here, so no model draft and no directory row can inject markup.
    """
    escaped = html.escape(text)
    return _BOLD.sub(r"<strong>\1</strong>", escaped).replace("\n", "<br>")


def _block(paragraph: str) -> str:
    """One paragraph, rendered as prose or as a numbered list.

    Answers containing several parallel options were arriving as raw ``- `` lines
    inside a paragraph, so the hyphens showed and every item carried the same
    visual weight. On a phone that forces her to read the whole list to find the
    one item that applies to her, which usually means she reads none of it.

    A lead-in sentence sitting above the items in the same paragraph stays a
    paragraph — the model writes "some things that genuinely help:" and that is
    not an item.
    """
    lines = paragraph.split("\n")
    lead: list[str] = []
    items: list[str] = []
    for line in lines:
        match = _ITEM.match(line)
        if match:
            items.append(match.group(1).strip())
        elif items:
            # A wrapped continuation of the item above, not a new one.
            items[-1] += " " + line.strip()
        else:
            lead.append(line)

    out = ""
    prose = "\n".join(lead).strip()
    if prose:
        out += f"<p>{_inline(prose)}</p>"
    if items:
        cells = "".join(f"<li>{_inline(i)}</li>" for i in items)
        out += f"<ol>{cells}</ol>"
    return out


def bubble(
    text: str, side: str = "bot", care: bool = False, *, name: str | None = None
) -> str:
    """Render a message. Blank lines become paragraphs, not empty lines.

    `name` puts a persona label above the text. Used on the opening bubble only —
    on every message it would read as a signature rather than an introduction,
    and the whole point of a chat surface is that you know who you are talking to
    without being told each time.
    """
    classes = "bubble " + ("care" if care else side)
    if care:
        label = '<div class="care-label">Support</div>'
    elif name:
        label = f'<div class="who-label">{html.escape(name)}</div>'
    else:
        label = ""

    paragraphs = _paragraphs(text)
    body = "".join(_block(p) for p in paragraphs)
    # Her face beside her words. Without it a reply is text from a system; with
    # it there is someone at the other end, which is the whole point of naming
    # her. Only on her side — she does not need to be shown her own face.
    avatar = f'<div class="avatar">{PERSONA_AVATAR}</div>' if side == "bot" else ""
    return (
        f'<div class="row {side}">{avatar}'
        f'<div class="{classes}">{label}{body}</div></div>'
    )


def typing() -> str:
    """Three dots, in her bubble, while the reply is being worked out.

    A blank spinner says the page is busy. This says *someone is answering you*,
    which is the same thing a person sees in every messaging app they use and
    reads as presence rather than as loading. It matters most on the turns that
    cannot stream: a grounded answer has to be generated and validated in full
    before any of it is safe to show, and this is what fills that gap honestly.
    """
    return (
        f'<div class="row bot"><div class="avatar">{PERSONA_AVATAR}</div>'
        '<div class="bubble bot typing">'
        '<span class="dot"></span><span class="dot"></span><span class="dot"></span>'
        '</div></div>'
    )


def streaming_bubble(text: str) -> str:
    """A partial reply, with a cursor, while it is still arriving."""
    paragraphs = _paragraphs(text)
    body = "".join(_block(p) for p in paragraphs)
    return (
        f'<div class="row bot"><div class="avatar">{PERSONA_AVATAR}</div>'
        f'<div class="bubble bot">{body}<span class="caret"></span></div></div>'
    )


def chips(labels: list[str]) -> str:
    if not labels:
        return ""
    items = "".join(f'<span class="chip">{html.escape(l)}</span>' for l in labels)
    return f'<div class="sources">{items}</div>'
