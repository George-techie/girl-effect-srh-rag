# Architecture

## The product architecture

Not every message passes through every stage. **That is the architecture** — the
branching is the design, not an implementation detail underneath it.

Only generation uses a hosted generative LLM. All routing, safeguarding, query
preparation and validation are deterministic; **embeddings run locally**, which
is compute rather than a rule and is why the encoder has a measurable cold start.

```mermaid
flowchart TD
    USER["<b>HER MESSAGE</b>"]:::her

    subgraph OBS["🔒 PRIVACY-SAFE OBSERVABILITY — route · safety · retrieval · LLM calls · latency · validator · journey stage · invariant failures · no message text"]
    direction TB

        VAL["<b>INPUT VALIDATION</b>"]:::det
        LEXS["<b>KENYAN LEXICON / LANGUAGE SIGNALS</b><br/><i>19 terms · 90 surface forms · risk tags</i>"]:::det

        DEC{"<b>DETERMINISTIC DECISION + SAFETY FLOOR</b><br/>safeguarding checked first, before any other family<br/><i>52/52 · recall 1.000 · precision 1.000</i>"}:::gate

        SG["<b>SAFEGUARDING</b>"]:::stop
        OOS["<b>OUT OF SCOPE</b>"]:::stop
        CHAT["<b>CHAT</b>"]:::model
        GRD["<b>FACTUAL / SUPPORT / ACCESS</b>"]:::det

        SGR["approved response<br/>/ help pathway<br/><b>0 LLM calls</b>"]:::stop
        OOSR["approved boundary<br/>response<br/><b>0 LLM calls</b>"]:::stop
        CHATR["conversational contract<br/><b>ONE LLM CALL</b><br/><i>claims nothing</i>"]:::model

        MT["<b>MULTI-TURN RESOLUTION</b><br/><i>only when context-dependent ·<br/>changes the query, not her message</i>"]:::det
        QP["<b>CONDITIONAL QUERY PREP</b><br/><i>factual / access, where a<br/>vocabulary gap was measured</i>"]:::det

        BGE["<b>BGE-M3 RETRIEVAL</b><br/>governed SRH corpus<br/><i>local encoder · 1,693 chunks</i>"]:::local
        TDL["<b>TRUSTED DATA LOOKUP</b><br/>verified services / contacts<br/><i>table read, never generated</i>"]:::gated

        GEN["<b>GROUNDED GENERATION</b><br/><b>ONE LLM CALL</b><br/><i>every claim cited</i>"]:::model
        DV["<b>DETERMINISTIC VALIDATION</b><br/><i>fabricated citation · invented number ·<br/>claimed experience</i>"]:::det
    end

    OUT["<b>HER REPLY</b>"]:::her

    USER --> VAL --> LEXS --> DEC

    DEC ==>|"harm · coercion · self-harm"| SG
    DEC -->|"deliberately not covered"| OOS
    DEC -->|"greeting · thanks · ambitions"| CHAT
    DEC -->|"a question to answer"| GRD

    SG ==> SGR
    OOS --> OOSR
    CHAT --> CHATR
    GRD --> MT --> QP
    QP --> BGE
    QP --> TDL
    BGE --> GEN
    TDL --> GEN
    GEN --> DV

    SGR ==> OUT
    OOSR --> OUT
    CHATR --> OUT
    DV --> OUT

    classDef her fill:#5B2340,stroke:#5B2340,color:#fff,font-weight:bold
    classDef det fill:#E8F4F3,stroke:#0E7A86,color:#123
    classDef gate fill:#C04B2F,stroke:#C04B2F,color:#fff,font-weight:bold
    classDef stop fill:#FBEAE4,stroke:#C04B2F,color:#123,font-weight:bold
    classDef model fill:#FFF4D6,stroke:#B8860B,color:#123,font-weight:bold
    classDef local fill:#E6F2E8,stroke:#2E7D4F,color:#123
    classDef gated fill:#F2F0EC,stroke:#7A736B,color:#123
```

| | |
|---|---|
| **rust** | the safeguarding gate, and every reply written from approved text |
| **pale teal** | deterministic — free, instant, auditable by reading it |
| **green** | local compute — the encoder. No token cost, but not a rule either |
| **gold** | a hosted LLM call. One, or none |

**Observability is not a stage.** It wraps the runtime and records what each
turn did — route, safety outcome, retrieval, LLM calls, latency, validator
issues, journey stage, invariant failures. It holds no message text by default.
It has already paid for itself twice: it surfaced a **39.5 s cold encoder load**
hiding behind a 5.4 s median, and the **service-access gap** — the Theory of
Change's terminal stage returning nothing.

---

## Session state is a supporting component, not a stage

```mermaid
flowchart LR
    SS["<b>SESSION STATE</b><br/>6 turns · resolved topic · disclosure flag<br/><i>in memory, one session, nothing written down</i>"]:::det

    A["multi-turn resolution<br/><i>gives a fragment its antecedent</i>"]:::det
    B["generation context<br/><i>so a reply does not re-introduce itself</i>"]:::model
    C["post-disclosure routing<br/><i>the disclosure flag</i>"]:::stop

    N["<b>Not built:</b> summariser · entity tracker ·<br/>persistent profile · vector store of past turns"]:::none

    SS --> A
    SS --> B
    SS --> C
    SS -.-> N

    classDef det fill:#E8F4F3,stroke:#0E7A86,color:#123
    classDef model fill:#FFF4D6,stroke:#B8860B,color:#123
    classDef stop fill:#FBEAE4,stroke:#C04B2F,color:#123,font-weight:bold
    classDef none fill:#F3F0EE,stroke:#9A9088,color:#555
```

No turn "passes through" session state. Three things consult it, and each one is
gated on a condition.

---

## Safeguarding to service access, without a model

The branch the use case turns on. She discloses, and later asks where to go —
and that second question is not a contraception question.

```mermaid
flowchart LR
    D["<b>safeguarding disclosure</b><br/><i>“if I really loved him<br/>I wouldn't make him use one”</i>"]:::stop
    F["<b>later:</b> “where can I go?”<br/><i>no subject of its own</i>"]:::her
    R["<b>post-disclosure help</b><br/><i>disclosure flag + dependent fragment</i>"]:::gate
    P["<b>approved help pathway</b><br/>health worker · trusted adult · helpline"]:::stop
    Z["<b>0 LLM calls · 0 ms</b>"]:::good

    D --> F --> R --> P --> Z

    classDef her fill:#5B2340,stroke:#5B2340,color:#fff,font-weight:bold
    classDef stop fill:#FBEAE4,stroke:#C04B2F,color:#123,font-weight:bold
    classDef gate fill:#C04B2F,stroke:#C04B2F,color:#fff,font-weight:bold
    classDef good fill:#E6F2E8,stroke:#2E7D4F,color:#123,font-weight:bold
```

Before this existed, that turn resolved against her earlier question about the
**implant**, searched implant passages, found nothing about *where*, and
refused — at the exact moment she asked for help. A rehearsal found it; no unit
test would have, because every component was behaving correctly.

---

## Build time and run time are separate

Ingestion happens once. Nothing at run time writes to the corpus.

```mermaid
flowchart LR
    subgraph BUILD["Build time — scripts/ingest.py"]
        direction LR
        P["8 governed PDFs<br/><i>corpus/raw</i>"]:::store
        RG["registry.py<br/><i>citation tag, role,<br/>authority per source</i>"]:::free
        LD["loaders.py"]:::free
        CL["cleaning.py"]:::free
        CHK2["chunking.py<br/><i>500/650/0, section-aware</i>"]:::free
        EM["bge-m3"]:::local
        DB[("ChromaDB")]:::store
        P --> LD --> CL --> CHK2 --> EM --> DB
        RG -.->|"metadata"| CHK2
    end

    subgraph RUN["Run time — every turn"]
        direction LR
        Q["her question"]:::iface
        E2["bge-m3"]:::local
        S["cosine, top-5"]:::free
        Q --> E2 --> S
    end

    DB -.->|"read only"| S

    classDef store fill:#F2F0EC,stroke:#7A736B,color:#123
    classDef free fill:#E8F4F3,stroke:#0E7A86,color:#123
    classDef local fill:#E6F2E8,stroke:#2E7D4F,color:#123
    classDef iface fill:#5B2340,stroke:#5B2340,color:#fff,font-weight:bold
```

Source labels shown to a girl are built from **metadata**, never from anything
the model wrote — which is what makes a fabricated source name impossible rather
than merely discouraged.

---

## The safety floor runs before retrieval

This is the single most important ordering decision in the build.

```mermaid
flowchart LR
    Q["“My periods have been<br/>irregular for three months”<br/><i>deliberately out of scope</i>"]:::her

    subgraph WRONG["If retrieval decided"]
        direction TB
        R1["retrieve"]:::free
        R2["similarity <b>0.668</b><br/><i>higher than most<br/>in-scope questions</i>"]:::bad
        R3["answered confidently,<br/>out of scope"]:::bad
        R1 --> R2 --> R3
    end

    subgraph RIGHT["What it does"]
        direction TB
        D1["decide, on her words"]:::decide
        D2["never searched"]:::good
        D3["declined, and told<br/>what it does cover"]:::good
        D1 --> D2 --> D3
    end

    Q --> WRONG
    Q --> RIGHT

    classDef her fill:#5B2340,stroke:#5B2340,color:#fff,font-weight:bold
    classDef free fill:#E8F4F3,stroke:#0E7A86,color:#123
    classDef decide fill:#0E7A86,stroke:#0E7A86,color:#fff,font-weight:bold
    classDef bad fill:#FBEAE4,stroke:#C04B2F,color:#123
    classDef good fill:#E6F2E8,stroke:#2E7D4F,color:#123
```

**Retrieval cannot decline.** It returns the nearest text, which is its job.
Asked *"am I too young to be thinking about protecting myself?"*, the second
result was *"I was raped and I am worried that no one will believe me."* That is
not a retrieval bug — it is the argument for a component above the retriever
whose only job is deciding whether to answer, running **before** the search,
because the similarity scores give it nothing to work with.

---

## Two output contracts

Which contract a reply is written under is decided by **provenance** — never
inferred from whether citations happen to be present.

```mermaid
flowchart TD
    T{"What kind of turn?"}:::decide

    G["<b>Grounded</b><br/>factual · access · support"]:::model
    C["<b>Conversational</b><br/>greeting · thanks · her ambitions"]:::model

    GS["Safe because<br/><b>every claim is cited</b>"]:::good
    CS["Safe because it<br/><b>makes no claim at all</b>"]:::good

    GF["uncited claim → <b>blocked</b><br/>marker pointing nowhere → <b>blocked</b>"]:::bad
    CF["any citation marker → <b>blocked</b><br/><i>a marker with no passage looks<br/>more verified than an uncited claim</i>"]:::bad

    T --> G --> GS --> GF
    T --> C --> CS --> CF

    P(["one persona file<br/><i>a girl cannot see which path her<br/>message took</i>"]):::obs
    P -.-> G
    P -.-> C

    classDef decide fill:#0E7A86,stroke:#0E7A86,color:#fff,font-weight:bold
    classDef model fill:#FFF4D6,stroke:#B8860B,color:#123,font-weight:bold
    classDef good fill:#E6F2E8,stroke:#2E7D4F,color:#123
    classDef bad fill:#FBEAE4,stroke:#C04B2F,color:#123
    classDef obs fill:#EFEAF2,stroke:#5B2340,color:#123
```

---

## Where the evidence comes from

```mermaid
flowchart LR
    PDF["8 governed PDFs<br/>WHO · UNFPA · UNICEF ·<br/>Kenya MoH · Girl Effect"]:::src
    CH["<b>1,693 chunks</b><br/>500/650/0, section-aware"]:::free
    DB[("ChromaDB<br/>cosine")]:::free
    TAG["citation tag · page ·<br/>section · document role"]:::free

    SVC[("Service directory<br/><b>unverified</b>")]:::bad

    PDF --> CH --> DB
    CH --> TAG
    DB -.->|"top-5 passages"| OUT["Generation"]:::model
    TAG -.->|"source labels built from<br/>metadata, never written<br/>by the model"| OUT
    SVC -.->|"gated: nothing surfaces<br/>until a person verifies it"| OUT

    classDef src fill:#5B2340,stroke:#5B2340,color:#fff,font-weight:bold
    classDef free fill:#E8F4F3,stroke:#0E7A86,color:#123
    classDef model fill:#FFF4D6,stroke:#B8860B,color:#123,font-weight:bold
    classDef bad fill:#FBEAE4,stroke:#C04B2F,color:#123
```

**Zero of the 1,693 chunks contains a phone number**, so any number in a
generated answer is invented by definition — and the validator treats a
phone-shaped string as fatal. Contacts are a table read, never generated, and
the table is gated on human verification.

---

## What each component had to prove

| Component | Kept or cut | The measurement |
|---|---|---|
| Decision layer | **kept** | 52/52, safeguarding recall and precision both 1.000 |
| Safety floor before retrieval | **kept** | an out-of-scope question retrieved at 0.668, above most in-scope ones |
| Deterministic validator | **kept** | catches fabricated citations and invented phone numbers, free |
| Query preparation | **kept** | Adequate@5 0.880 → 0.960, zero regressions, zero tokens |
| Conversation state | **kept** | a follow-up about the implant retrieved *female sterilization* without it |
| Observability | **kept** | three defects in one afternoon, all found by hand |
| LLM evidence judge | **cut** | +6 unhelpful refusals to prevent one unsafe case |
| LLM output judge | **cut** | refused a girl's compliment, twice |
| LLM turn planner | **cut** | rules beat it at 52/52 |
| LLM query rewriter | **not built** | a string table already got 0.960 for nothing |
| Source role preference | **rejected** | moved youth material up without improving what answers could support |
| Automatic restatement | **refused** | helped factual turns, actively harmed support and out-of-scope ones |

Full reasoning, each with what would reverse it: [`decisions.md`](decisions.md).
