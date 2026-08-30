# Service directory

**Contacts are a table read, never generated.** No corpus chunk contains a phone
number, so any number in a generated answer came from the model's memory — and
the validator treats a phone-shaped string in generated text as fatal. This file
is the only legitimate source of a contact detail in the system.

Eight services, covering all eight routes the pipeline can ask for. Compiled
from the organisations' own published information and signed off by a named
person with a date, which is what the `source`, `verified_by` and `verified_at`
columns exist to record.

```bash
python scripts/check_services.py     # what she gets on each route
```

## The gate

A row reaches a girl only when `status` is exactly `verified`. That is a real
mechanism rather than a formality: a directory whose column says `verified_at`
is worthless if the dates in it were invented, and a plausible wrong number
given to a girl in crisis is the highest-consequence output this system can
produce.

Adding a row without provenance means it sits in the file and never reaches
anyone, which is the correct outcome and is covered by a test.

## The columns

| Column | What goes in it | Required |
|---|---|---|
| `service_id` | Short stable code, e.g. `KE_GBV_1195`. Never reused | ✅ |
| `name` | What she should call it, e.g. *National GBV Helpline* | ✅ |
| `service_type` | e.g. *helpline*, *clinic*, *counselling*, *youth centre* | ✅ |
| `routes` | Which situations it answers — see below. Pipe-separated | ✅ |
| `contact_type` | `phone`, `sms`, `whatsapp`, `phone_whatsapp`, `ussd`, `web`, `walk_in` | ✅ |
| `contact` | The number or address exactly as she would use it | ✅ |
| `coverage` | *Kenya*, a county, or a town | ✅ |
| `is_free` | `yes` / `no` / blank if unknown. **Blank is fine — a wrong "free" costs her airtime she may not have** | |
| `anonymous_ok` | `yes` / `no` / blank. Whether she must give her name | |
| `opening_hours` | e.g. *24/7*, *Mon–Fri 8am–5pm*. Blank if unknown | |
| `eligibility` | Age limits, marital status, anything that could turn her away | |
| `what_they_do` | **One sentence, in plain words, written for her** — shown under the number | ✅ |
| `source` | Where it came from | ✅ |
| `source_url` | Link if there is one | |
| `verified_by` | Who checked it | ✅ |
| `verified_at` | Date checked, `YYYY-MM-DD` | ✅ |
| `status` | `verified` | ✅ |

## Routes

| Route | When it fires | Reached from |
|---|---|---|
| `contraception` | she asks where to get family planning | access turn |
| `hiv_sti` | testing, PrEP, treatment | access turn naming HIV, an STI or testing |
| `pregnancy_support` | she is pregnant and needs someone | access turn naming pregnancy |
| `youth_friendly` | somewhere that will not judge her age | access turn |
| `sexual_violence` | rape, assault, coercion | safeguarding, urgent tier |
| `intimate_partner_violence` | being hurt by a partner | safeguarding, urgent tier |
| `self_harm_risk` | thoughts of ending her life | safeguarding, the one route where contacts arrive unprompted |
| `emotional_support` | someone to talk to | safeguarding, concern tier |

## What matters when adding a row

**A text channel beats a voice one.** A girl on a shared phone, in a room with
family, often cannot make a call. The system ranks text-capable rows first for
exactly this reason, so an SMS or WhatsApp number is worth more than another
hotline.

**Say what she has to give up.** `anonymous_ok` and `eligibility` decide whether
she can actually use a service. A name-and-number list quietly assumes no
barriers exist.

**Leave a cell blank rather than guessing.** Blank means unknown and the system
simply will not claim it. A guess becomes a claim.

**One sentence in `what_they_do`, in her register.** *"They talk to anyone
experiencing violence and help you think about what's safest"* — not *"a
multi-sectoral GBV response mechanism"*.
