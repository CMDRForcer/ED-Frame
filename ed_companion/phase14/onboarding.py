"""Version policy for onboarding, including pre-versioned completed profiles."""

ONBOARDING_VERSION = 1
LEGACY_ONBOARDING_VERSION = 1


def onboarding_state(config, *, preview_skip=False, current_version=ONBOARDING_VERSION):
    try:
        version = max(0, int(config.get("onboarding_version", LEGACY_ONBOARDING_VERSION)))
    except (TypeError, ValueError, OverflowError):
        version = LEGACY_ONBOARDING_VERSION
    complete = bool(config.get("onboarding_complete", False))
    return (bool(preview_skip or (complete and version >= current_version)), version)
