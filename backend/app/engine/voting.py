from app.models.game import VoteRecord


def count_votes(votes: list[VoteRecord], weight_by_voter: dict[str, float] | None = None) -> dict[str, float]:
    counts: dict[str, float] = {}
    for vote in votes:
        if vote.target == "abstain":
            continue
        weight = (weight_by_voter or {}).get(vote.voter, 1.0)
        counts[vote.target] = counts.get(vote.target, 0.0) + weight
    return counts


def tally_votes(votes: list[VoteRecord], weight_by_voter: dict[str, float] | None = None) -> tuple[str | None, list[str], dict[str, float]]:
    counts = count_votes(votes, weight_by_voter)
    if not counts:
        return None, [], counts

    max_votes = max(counts.values())
    top = [name for name, count in counts.items() if count == max_votes]
    if len(top) == 1:
        return top[0], top, counts
    return None, top, counts
