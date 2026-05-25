from app.models.game import GOD_ROLES, GameState, Role, WinRule, WOLF_ROLES


def check_win_condition(state: GameState) -> str | None:
    alive = [player for player in state.players if player.status.value == "alive"]
    wolves = [player for player in alive if player.role in WOLF_ROLES]
    good_players = [player for player in alive if player.role not in WOLF_ROLES]
    gods = [player for player in alive if player.role in GOD_ROLES]
    villagers = [player for player in alive if player.role == Role.VILLAGER]

    if not wolves:
        return "village"

    if state.rules.win_rule == WinRule.SLAUGHTER_SIDE:
        if not gods or not villagers:
            return "werewolf"
        return None

    if state.rules.win_rule == WinRule.TOTAL_ELIMINATION:
        if not good_players:
            return "werewolf"
        return None

    if len(wolves) >= len(good_players):
        return "werewolf"
    return None
