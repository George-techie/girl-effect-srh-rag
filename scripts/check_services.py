"""What the service directory currently gives a girl, and what it does not.

    python scripts/check_services.py

Run it after editing `data/services/services.csv`. It reads the table exactly
the way the pipeline does, shows what she would actually see on each route, and
names the rows that are being withheld and why.

Nothing is surfaced until `status` is `verified`. This script is how you see
what that gate is currently holding back.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import services

#: The routes the pipeline asks for, and where each one is used.
ROUTES = [
    ("self_harm_risk", "self-harm disclosure — the only route where contacts "
                       "arrive unprompted"),
    ("sexual_violence", "violence or reproductive coercion disclosed"),
    ("intimate_partner_violence", "hurt by a partner"),
    ("emotional_support", "any other disclosure, and the fallback route"),
    ("contraception", "she asks where to get family planning"),
    ("youth_friendly", "she wants somewhere that will not judge her age"),
    ("hiv_sti", "testing, PrEP, treatment"),
    ("pregnancy_support", "she is pregnant and needs someone"),
]


def main() -> int:
    verified = services._load()
    print("=" * 76)
    print(f"SERVICE DIRECTORY — {len(verified)} verified row(s)")
    print(f"{services.SERVICES_CSV}")
    print("=" * 76)

    # --- what is being withheld ---------------------------------------------
    withheld = []
    if services.SERVICES_CSV.exists():
        with services.SERVICES_CSV.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                if not (row.get("contact") or "").strip():
                    continue
                if (row.get("status") or "").strip().lower() != services.VERIFIED:
                    withheld.append(row)

    if withheld:
        print(f"\nWITHHELD — {len(withheld)} row(s) with a contact but no verification")
        for row in withheld:
            missing = [c for c in ("source", "verified_by", "verified_at")
                       if not (row.get(c) or "").strip()]
            print(f"  {row.get('name', '?'):32} {row.get('contact', ''):20}"
                  f"  status={row.get('status') or 'blank'!r}")
            if missing:
                print(f"      needs: {', '.join(missing)}")
        print("\n  These do not reach a girl. Fill source, verified_by and")
        print("  verified_at, set status to 'verified', and re-run this.")

    # --- what she would see --------------------------------------------------
    print("\nWHAT SHE GETS, PER ROUTE")
    print("-" * 76)
    for route, when in ROUTES:
        found = services.for_route(route)
        mark = f"{len(found)} service(s)" if found else "nothing"
        print(f"\n  {route:28} {mark}")
        print(f"  {'':28} {when}")
        for service in found:
            for line in service.render().splitlines():
                print(f"      {line}")

    # --- the honest summary --------------------------------------------------
    covered = sum(1 for r, _ in ROUTES if services.for_route(r))
    print("\n" + "=" * 76)
    print(f"{covered} of {len(ROUTES)} routes have at least one verified service.")
    if not verified:
        print("\nNothing is verified, so no contact is shown anywhere. The")
        print("safeguarding replies still name the KIND of person who helps -- a")
        print("health worker, a teacher she trusts, a helpline -- which is useful")
        print("on its own and is what she gets today.")
        print("\nThe highest-value routes to fill first are the safeguarding ones:")
        print("self_harm_risk, sexual_violence, intimate_partner_violence. Those")
        print("are where having nothing verified costs the most.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
