"""Pin town shops to a recorded game.

The engine draws each new shop from the same daily RNG that spawns weeds (one draw per empty tile), so an
agent replacing one side of a recorded game changes which shops open. That silently moves the game to a
different town. For any evaluation against a frozen tape, replay the recording once to recover its shop
sequence, then force that sequence while the candidate plays.
"""
import json, os

ROOT = os.path.dirname(os.path.abspath(__file__))
_PIN = {"shops": None}


def recorded_shops(ep):
    """Shop list at the start of every day of the recorded game (cached next to the tape)."""
    cache = os.path.join(ROOT, "tapes", f"{ep}.shops.json")
    if os.path.exists(cache):
        return json.load(open(cache))
    import fastsim, tapes
    t = tapes.load(ep)
    _PIN["shops"] = None
    days = []

    def snap(obs):
        if obs["step"] % 24 == 0:
            days.append(list(obs["town"]["unlocked_shops"]))

    a0, a1 = tapes.TapeAgent(ep, 0), tapes.TapeAgent(ep, 1)

    def w0(obs, cfg=None):
        snap(obs)
        return a0(obs, cfg)

    fastsim.play(w0, a1, t["seed"])
    json.dump(days, open(cache, "w"))
    return days


def install(K):
    """Wrap the engine's end-of-day so that, when a pin is set, the shop list follows the recording."""
    if getattr(K, "_shop_pin_installed", False):
        return
    orig = K._end_of_day

    def end_of_day(state, env, day):
        orig(state, env, day)
        rec = _PIN["shops"]
        if rec is not None and day + 1 < len(rec):
            state[0].observation.town["unlocked_shops"][:] = list(rec[day + 1])

    K._end_of_day = end_of_day
    K._shop_pin_installed = True


def pin(shops):
    _PIN["shops"] = shops


def unpin():
    _PIN["shops"] = None
