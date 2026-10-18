from __future__ import annotations

from .schemas import Comparison, Estimate, Requirement


def compare(prev_reqs: list[Requirement], new_reqs: list[Requirement], prev_est: Estimate, new_est: Estimate,
            from_v: int, to_v: int) -> Comparison:
    P = {r.id: r for r in prev_reqs}
    N = {r.id: r for r in new_reqs}
    unchanged, modified, added, removed, oos = [], [], [], [], []
    approval: list[str] = []
    for rid, n in N.items():
        p = P.get(rid)
        if p is None:
            if n.status == "out_of_scope":
                oos.append(f"{rid}: {n.text} (new request, explicitly out of scope)")
            elif n.status == "in_scope":
                added.append(f"{rid}: {n.text}")
                approval.append(f"Added requirement {rid} (scope and cost increase)")
            continue
        if n.status == "removed" and p.status == "in_scope":
            removed.append(f"{rid}: {p.text}")
            approval.append(f"Removed requirement {rid} (scope and cost decrease must be agreed)")
        elif n.status == "out_of_scope" and p.status == "in_scope":
            oos.append(f"{rid}: {p.text} (moved out of scope)")
            approval.append(f"Requirement {rid} moved out of scope")
        elif n.text != p.text and n.status == "in_scope":
            modified.append({"id": rid, "before": p.text, "after": n.text})
            approval.append(f"Modified requirement {rid}")
        elif n.status == p.status == "in_scope":
            unchanged.append(f"{rid}: {p.text}")
    prev_h, new_h = prev_est.total_hours, new_est.total_hours
    if new_h > prev_h:
        approval.append(f"Estimate increased by {new_h - prev_h:g} h (from {prev_h:g} h to {new_h:g} h)")
    return Comparison(from_version=from_v, to_version=to_v, unchanged=unchanged, modified=modified, added=added, removed=removed,
                      out_of_scope_changes=oos, previous_total_hours=prev_h, new_total_hours=new_h,
                      additional_hours=round(new_h - prev_h, 2), requires_client_approval=approval)
