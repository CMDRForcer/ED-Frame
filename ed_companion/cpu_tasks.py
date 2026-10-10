"""Picklable pure projections; no QObject, profile mutation, network or writes."""


def journal_projection(events):
    from ed_companion.journal import project_vehicle_state, project_latest_srv_mining_session
    from ed_companion.phase14.state_commander import powerplay_journal_overview
    from ed_companion.missions import active_missions, community_goals_overview
    from ed_companion.exploration import exploration_ledger
    vehicle = project_vehicle_state(events)
    vehicle["latestMiningSession"] = project_latest_srv_mining_session(events)
    return {"powerplay": powerplay_journal_overview(events), "vehicle": vehicle,
            "missions": active_missions(events), "communityGoals": community_goals_overview(events),
            "exploration": exploration_ledger(events)}


def commander_projection(overview, events, snapshots):
    from ed_companion.phase14.commander_projection import prepare_commander_projection
    return prepare_commander_projection(overview, events, snapshots)


def powerplay_merge(existing, rows, limit):
    from ed_companion.navigation.mining_powerplay import merge_powerplay_observations
    return merge_powerplay_observations(existing, rows, limit=limit)
