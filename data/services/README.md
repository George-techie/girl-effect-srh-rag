# Service directory — for filling in

Contacts are a **table read, never generated**. Zero of the 1,693 corpus chunks
contains a phone number, so any number in a generated answer is invented by
definition, and the validator treats a phone-shaped string as fatal. This file
is the only legitimate source of a contact detail in the system.

**Nothing here reaches a girl until `status` is `verified`.** The two rows
currently present were carried over from the previous build with no provenance,
so they are marked `unverified` and the pipeline will refuse to surface them.
That is deliberate: a table whose column says `verified_at` is worthless if the
dates in it were invented.

Fill in [`services.csv`](services.csv), or the Word version at
[`docs/service_directory_to_fill.docx`](../../docs/service_directory_to_fill.docx),
whichever is easier.

## The columns

| Column | What goes in it | Required |
|---|---|---|
| `service_id` | Short stable code, e.g. `KE_GBV_1195`. Never reused | ✅ |
| `name` | What she should call it, e.g. *National GBV Helpline* | ✅ |
| `service_type` | e.g. *helpline*, *clinic*, *counselling*, *youth centre* | ✅ |
| `routes` | Which situations it answers — see the list below. Pipe-separated | ✅ |
| `contact_type` | `phone`, `sms`, `whatsapp`, `phone_whatsapp`, `ussd`, `web`, `walk_in` | ✅ |
| `contact` | The number or address exactly as she would use it | ✅ |
| `coverage` | *Kenya*, a county, or a town | ✅ |
| `is_free` | `yes` / `no` / blank if unknown. **Blank is fine — a wrong "free" costs her airtime she may not have** | |
| `anonymous_ok` | `yes` / `no` / blank. Whether she must give her name | |
| `opening_hours` | e.g. *24/7*, *Mon–Fri 8am–5pm*. Blank if unknown | |
| `eligibility` | Age limits, marital status, anything that could turn her away | |
| `what_they_do` | **One sentence, in plain words, written for her** — this is shown under the number | ✅ |
| `source` | Where you got it: an organisation's own page, a directory, a phone call | ✅ |
| `source_url` | Link if there is one | |
| `verified_by` | Your name | ✅ |
| `verified_at` | Date you checked, `YYYY-MM-DD` | ✅ |
| `status` | `verified` once checked. Leave `unverified` otherwise | ✅ |

## Routes to cover

These are the situations the system can route to. A row can serve several —
separate them with `|`.

| Route | When it fires | Priority |
|---|---|---|
| `contraception` | She asks where to get family planning | **high** — this is the use case |
| `youth_friendly` | She wants somewhere that will not judge her age or marital status | **high** |
| `hiv_sti` | Testing, PrEP, treatment | high |
| `sexual_violence` | Rape, assault, coercion | **high** — safeguarding |
| `intimate_partner_violence` | Being hurt by a partner | **high** — safeguarding |
| `self_harm_risk` | Thoughts of ending her life | **high** — safeguarding, the only urgent route |
| `pregnancy_support` | She is pregnant and needs someone | medium |
| `emotional_support` | Someone to talk to | medium |

## What matters most when filling it

**A text channel beats a voice one.** A girl on a shared phone, in a room with
family, often cannot make a call. The system ranks text-capable rows first for
that reason, so SMS and WhatsApp numbers are worth more than an extra hotline.

**Say what she has to give up.** `anonymous_ok` and `eligibility` are the
columns that decide whether she can actually use a service. A name-and-number
list quietly assumes no barriers exist.

**Leave a cell blank rather than guessing.** Blank means unknown and the system
simply will not claim it. A guess becomes a claim.

**One sentence in `what_they_do`, in her register.** Not the organisation's
mission statement. *"They talk to anyone experiencing violence and help you
think about what's safest"* — not *"a multi-sectoral GBV response mechanism"*.

## The two rows already there

`Befrienders Kenya +254 722 178 177` and `Kenya Red Cross 1199` were copied from
the previous build. They may well be right — but no source, date or checker was
recorded, so they stay `unverified` until someone confirms them. If you verify
them, fill `source`, `verified_by` and `verified_at` and set `status`.
