from collections import defaultdict
from datetime import datetime

from .media_utils import distance_in_meters


CATEGORY_WEIGHTS = {
    "Pothole": 4.5,
    "Garbage": 3.6,
    "Drainage": 4.2,
    "Water": 4.0,
    "Streetlight": 3.2,
    "Other": 2.8,
}

SLA_HOURS = {
    "Pothole": 72,
    "Garbage": 48,
    "Drainage": 36,
    "Water": 24,
    "Streetlight": 72,
    "Other": 96,
}


def group_duplicate_hotspots(issues, comment_counts: dict[int, int], radius_meters: int = 250):
    open_issues = [issue for issue in issues if issue.status != "Resolved"]
    visited = set()
    hotspots = []

    for issue in open_issues:
        if issue.id in visited:
            continue

        cluster = [issue]
        visited.add(issue.id)
        for candidate in open_issues:
            if candidate.id in visited:
                continue
            if candidate.category != issue.category:
                continue
            if None in (issue.latitude, issue.longitude, candidate.latitude, candidate.longitude):
                continue

            distance = distance_in_meters(issue.latitude, issue.longitude, candidate.latitude, candidate.longitude)
            if distance <= radius_meters:
                cluster.append(candidate)
                visited.add(candidate.id)

        hotspot = {
            "anchor_issue": issue,
            "issues": cluster,
            "count": len(cluster),
            "comment_support": sum(comment_counts.get(item.id, 0) for item in cluster),
        }
        hotspots.append(hotspot)

    return sorted(hotspots, key=lambda item: (item["count"], item["comment_support"]), reverse=True)


def compute_density_bonus(issue, hotspots):
    for hotspot in hotspots:
        if any(member.id == issue.id for member in hotspot["issues"]):
            return max(hotspot["count"] - 1, 0) * 0.8
    return 0.0


def compute_issue_severity(issue, comment_count: int, hotspots):
    age_hours = max((datetime.utcnow() - issue.created_at).total_seconds() / 3600, 0)
    category_weight = CATEGORY_WEIGHTS.get(issue.category, 3.0)
    age_score = min(age_hours / 24, 5)
    support_score = min(comment_count * 0.7, 5)
    density_score = compute_density_bonus(issue, hotspots)
    resolved_penalty = -2 if issue.status == "Resolved" else 0
    raw_score = category_weight + age_score + support_score + density_score + resolved_penalty
    return round(max(raw_score, 0), 1)


def build_issue_severity(issue, comment_count: int, hotspots):
    return compute_issue_severity(issue, comment_count, hotspots)


def build_ward_leaderboard(issues):
    wards = defaultdict(lambda: {"ward": "Unassigned", "resolved": 0, "open": 0, "total_resolution_hours": 0.0})

    for issue in issues:
        ward_name = issue.ward or "Unassigned"
        entry = wards[ward_name]
        entry["ward"] = ward_name

        if issue.status == "Resolved":
            entry["resolved"] += 1
            if issue.resolved_at:
                hours = max((issue.resolved_at - issue.created_at).total_seconds() / 3600, 0)
                entry["total_resolution_hours"] += hours
        else:
            entry["open"] += 1

    leaderboard = []
    for entry in wards.values():
        resolved = entry["resolved"]
        open_count = entry["open"]
        avg_hours = entry["total_resolution_hours"] / resolved if resolved else 0
        score = (resolved * 5) - (open_count * 2) - (avg_hours / 24 if avg_hours else 0)
        leaderboard.append(
            {
                "ward": entry["ward"],
                "resolved": resolved,
                "open": open_count,
                "avg_resolution_hours": round(avg_hours, 1) if resolved else None,
                "score": round(score, 1),
            }
        )

    return sorted(leaderboard, key=lambda item: item["score"], reverse=True)


def build_heatmap_data(issues, comment_counts):
    heatmap_points = []
    for issue in issues:
        # Only include open/pending issues for heatmap visualization
        if issue.status == "Resolved":
            continue
        if issue.latitude is None or issue.longitude is None:
            continue

        weight = compute_issue_severity(issue, comment_counts.get(issue.id, 0), [])
        # Scale weight for better heatmap intensity (0-100 range)
        heatmap_intensity = min(weight * 8, 100)
        heatmap_points.append(
            {
                "id": issue.id,
                "title": issue.title,
                "category": issue.category,
                "lat": issue.latitude,
                "lng": issue.longitude,
                "weight": weight,
                "intensity": heatmap_intensity,
                "status": issue.status,
            }
        )

    return heatmap_points


def build_sla_status(issue, severity_score: float):
    allowed_hours = SLA_HOURS.get(issue.category, 96)
    if severity_score >= 10:
        allowed_hours = max(int(allowed_hours * 0.5), 12)
    elif severity_score >= 7:
        allowed_hours = max(int(allowed_hours * 0.75), 18)

    elapsed_hours = max((datetime.utcnow() - issue.created_at).total_seconds() / 3600, 0)
    overdue = issue.status != "Resolved" and elapsed_hours > allowed_hours

    return {
        "allowed_hours": allowed_hours,
        "elapsed_hours": round(elapsed_hours, 1),
        "overdue": overdue,
    }


def build_verification_summary(verifications):
    totals = {"solved": 0, "not_solved": 0}
    for verification in verifications:
        if verification.verdict in totals:
            totals[verification.verdict] += 1
    return totals
