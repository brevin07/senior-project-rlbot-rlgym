from __future__ import annotations

from math import exp, sqrt
from statistics import mean, pstdev
from bisect import bisect_left
from typing import Any, Dict, List, Tuple

from rocketcoach.live_analysis.grading_context import (
    frame_context,
    infer_gamemode,
    rank_band,
    summarize_event_window,
)


MECHANIC_ALIASES = {
    "flicking_carry_offense": "flicking",
}

# Bumped each time detection logic, scoring weights, or output schema changes so
# the store knows which cached payloads are stale and need re-grading.
GRADING_VERSION = "mechanic_v9_flick_grounded_aerial_transition"

MIN_REPORTED_MECHANIC_CONFIDENCE = 0.30

# Graded mechanics — these get scored, confidence-rated, and coached.
MECHANICS = [
    "kickoff",
    "shadow_defense",
    "challenge",
    "fifty_fifty_control",
    "aerial_offense",
    "aerial_defense",
    "flicking",
    "carrying_dribbling",
]

# Flag-only mechanics — detected and shown as timeline markers but not graded or coached.
FLAG_MECHANICS: List[str] = []
SPECIAL_AERIAL_TAGS = [
    "flip_reset",
    "ceiling_shot",
    "double_tap",
]

MECH_SHORT = {
    "kickoff": "KO",
    "shadow_defense": "SHD",
    "challenge": "CHAL",
    "fifty_fifty_control": "5050",
    "aerial_offense": "AOF",
    "aerial_defense": "ADF",
    "flicking": "FLK",
    "carrying_dribbling": "DRB",
    # Flag mechanics — labels only
    "flip_reset": "FLR",
    "ceiling_shot": "CLG",
    "double_tap": "DBT",
}

MECH_TITLE = {
    "kickoff": "Kickoff",
    "shadow_defense": "Shadow Defense",
    "challenge": "Challenge",
    "fifty_fifty_control": "50/50 Control",
    "aerial_offense": "Aerial Offense",
    "aerial_defense": "Aerial Defense",
    "flicking": "Flicks",
    "carrying_dribbling": "Carries / Dribbles",
    # Flag mechanics — labels only
    "flip_reset": "Flip Reset",
    "ceiling_shot": "Ceiling Shot",
    "double_tap": "Double Tap",
}

MECH_COACHING = {
    "kickoff": {
        "description": "Kickoff measures how well you win or neutralize the first touch and protect your team from an instant counter.",
        "why_it_matters": "A clean kickoff decides early possession, boost routes, and whether your team starts under pressure.",
        "common_mistake": "Players often arrive late, hit off-center, or recover too slowly after the first touch.",
        "training_cue": "Arrive square, hit through the middle of the ball, and land ready to cover the next bounce.",
        "good": (
            "You arrived on time and directed the first touch into a playable outcome.",
            "Keep hitting through the center and recovering immediately so your team owns the next touch.",
        ),
        "neutral": (
            "The kickoff stayed playable, but you did not create a clear advantage after contact.",
            "Tighten the entry angle and your recovery so the ball dies where you can follow it first.",
        ),
        "bad": (
            "You lost the center of the ball and gave the opponent the better exit off kickoff.",
            "Drive through the middle sooner and land facing the next touch so the kickoff stays neutral or favorable.",
        ),
    },
    "shadow_defense": {
        "description": "Shadow Defense measures whether you stay goal-side, control space, and delay the attacker without overcommitting.",
        "why_it_matters": "Good shadow defense buys time for recovery and forces the attacker into a rushed or weaker play.",
        "common_mistake": "Players either give too much space and invite a setup, or dive in before they can win the challenge.",
        "training_cue": "Match the attacker earlier, stay goal-side, and hold a distance that lets you react to flicks or cuts.",
        "good": (
            "You stayed goal-side and kept the attacker from getting a clean shooting lane.",
            "Keep mirroring their speed and wait for the touch that lets you challenge safely.",
        ),
        "neutral": (
            "Your positioning slowed the play, but you still left the attacker a little too much freedom.",
            "Hold a tighter line so you can pressure the ball sooner without diving in.",
        ),
        "bad": (
            "You gave too much space and let the attacker set up freely.",
            "Match their speed sooner and hold a tighter line so you can pressure without overcommitting.",
        ),
    },
    "challenge": {
        "description": "Challenge measures how safely and effectively you contest the ball when another player can meet it.",
        "why_it_matters": "Strong challenges stop counters, force weak touches, and turn contested balls into possessions your team can read.",
        "common_mistake": "Players challenge from the side, jump in without cover, or lose the 50 straight into danger.",
        "training_cue": "Turn in earlier, stay goal-side when needed, and hit with the nose of your car through the center of the contest.",
        "good": (
            "You met the ball from a strong angle and kept the contest neutral or favorable for your team.",
            "Keep arriving through the center so the challenge stays safe even if you do not win it cleanly.",
        ),
        "neutral": (
            "You got into the contest, but the challenge did not give your team much control afterward.",
            "Square up a little earlier so the ball exits into space you or a teammate can reach first.",
        ),
        "bad": (
            "You met the ball from a weak angle and got beaten through the 50.",
            "Turn in earlier and make contact with the nose of your car so the challenge stays neutral or rolls to your side.",
        ),
    },
    "fifty_fifty_control": {
        "description": "50/50 Control measures whether your contact absorbs, deadens, or directs a contested ball into a playable result.",
        "why_it_matters": "Winning the exit of a 50 turns chaotic contact into possession instead of another emergency touch.",
        "common_mistake": "Players flip through the ball too hard, hit off-center, or land without a plan for the next bounce.",
        "training_cue": "Stay grounded when possible, center your car behind the ball, and absorb the challenge into space you can follow.",
        "good": (
            "You absorbed the contact well and kept the ball in a controllable spot after the 50.",
            "Keep centering your car and preparing the landing so you own the follow-up too.",
        ),
        "neutral": (
            "The contest did not hurt you, but the ball still bounced into a race instead of clear control.",
            "Soften the touch more and aim the 50 into a lane you can reach first.",
        ),
        "bad": (
            "Your touch did not absorb the challenge, so the ball spilled away.",
            "Stay grounded, center your car behind the ball, and aim to deaden the touch into space you can follow.",
        ),
    },
    "aerial_offense": {
        "description": "Aerial Offense measures whether your airborne touches create threat, forward pressure, or a useful follow-up.",
        "why_it_matters": "Good offensive aerials turn hard reads into shots, passes, or second touches before the defense can reset.",
        "common_mistake": "Players reach the ball late, settle for weak contact, or float out of the play after the hit.",
        "training_cue": "Read the ball earlier, meet it with forward intent, and recover so you can pressure the second ball.",
        "good": (
            "You met the ball with intent and turned the aerial into real attacking pressure.",
            "Keep attacking the ball early and recovering forward so the play stays dangerous.",
        ),
        "neutral": (
            "You made the touch in the air, but it did not create enough pressure after contact.",
            "Attack the ball a little earlier so the hit carries pace or direction the defense has to respect.",
        ),
        "bad": (
            "You reached the ball in the air, but the touch did not create enough threat afterward.",
            "Read the takeoff sooner and hit through the ball with forward intent so the aerial leads to pressure, not just contact.",
        ),
    },
    "aerial_defense": {
        "description": "Aerial Defense measures whether your airborne defensive touches actually remove danger from your half.",
        "why_it_matters": "A good aerial clear can stop a shot, break pressure, and buy your team time to recover shape.",
        "common_mistake": "Players save the ball but center it, clear too softly, or lose control of their landing afterward.",
        "training_cue": "Beat the ball to the dangerous lane, clear wide when needed, and recover out of the play quickly.",
        "good": (
            "You removed danger well and sent the ball into a safer lane after the aerial.",
            "Keep prioritizing the safe clear first, then add distance once the threat is gone.",
        ),
        "neutral": (
            "You made the defensive touch, but the clear did not fully relieve pressure.",
            "Use a wider or earlier contact so the save leaves less of a rebound for the opponent.",
        ),
        "bad": (
            "You got a touch, but the ball stayed too dangerous after the defensive aerial.",
            "Beat the ball a little earlier and clear wider so the save removes pressure instead of recycling it.",
        ),
    },
    "flicking": {
        "description": "Flicks measures how well you convert control into a threatening release with lift, pace, and timing.",
        "why_it_matters": "A clean flick punishes defenders who wait too long and turns dribble control into a real scoring threat.",
        "common_mistake": "Players flick late, from an unstable carry, or without enough upward pop to threaten the goal.",
        "training_cue": "Balance the dribble first, flick earlier, and pop up through the ball before the defender settles.",
        "good": (
            "You turned control into a threatening release with good timing and enough lift.",
            "Keep forcing the defender to respect the flick by popping early from a balanced carry.",
        ),
        "neutral": (
            "The setup was there, but the release did not have quite enough threat to punish the defender.",
            "Pop the ball a little earlier and keep the dribble more centered before the flick.",
        ),
        "bad": (
            "You had control, but the flick came late and without enough lift.",
            "Pop the ball earlier from a balanced dribble so the flick has more height and forces a harder save.",
        ),
    },
    "carrying_dribbling": {
        "description": "Carries / Dribbles measures whether you keep close control under pressure and turn that control into a useful next action.",
        "why_it_matters": "Stable dribbles create options: flick, cut, pass, or low-50 before the defender decides the play for you.",
        "common_mistake": "Players carry too loosely, let pressure close the space, or fail to convert control into a threat.",
        "training_cue": "Keep the ball close enough to react, protect it with your car, and turn the dribble into a decision before pressure collapses.",
        "good": (
            "You kept the ball close and turned the carry into a playable attacking option.",
            "Keep protecting the ball with your car and decide early whether the next touch is a flick, cut, or low 50.",
        ),
        "neutral": (
            "You had control for a moment, but the dribble did not turn into enough of a threat afterward.",
            "Keep the ball a little tighter and choose the next action before the defender closes the gap.",
        ),
        "bad": (
            "You had control, but the carry did not stay tight enough to threaten the defender.",
            "Keep the ball closer to your hood and turn the dribble into a flick, cut, or low 50 before pressure arrives.",
        ),
    },
}

KICKOFF_CENTER_MAX_DIST = 240.0
KICKOFF_BALL_SPEED_MAX = 120.0
KICKOFF_WINDOW_TIMEOUT = 4.0
KICKOFF_ATTEMPT_DIST = 1800.0
KICKOFF_ATTEMPT_CLOSING_SPEED = 600.0   # was 900 — lower-rank players approach without full boost
KICKOFF_ATTEMPT_SUSTAIN_S = 0.25
KICKOFF_TOUCH_MAX_S = 2.2
KICKOFF_DIRECT_ALIGNMENT_MIN = 0.72
KICKOFF_DIRECT_MAX_ALIGNMENT_MIN = 0.86
KICKOFF_DIRECT_MAX_CLOSING_MIN = 900.0
KICKOFF_DIRECT_MIN_POSITIVE_SAMPLES = 2
KICKOFF_RECENT_LOOKBACK_S = 0.9
KICKOFF_RECENT_MEAN_ALIGNMENT_MIN = 0.55
KICKOFF_RECENT_MIN_DISTANCE = 1800.0
KICKOFF_TOUCH_SEARCH_MAX_S = 30.0
KICKOFF_TOUCH_CONF_MIN = 0.35
KICKOFF_SPAWN_XY_TOL = 380.0
KICKOFF_SPAWN_Z_MAX = 120.0
KICKOFF_SPAWN_POINTS = [
    (0.0, 4608.0),
    (256.0, 3840.0),
    (2048.0, 2560.0),
]


def _canonical_mid(mid: str) -> str:
    m = str(mid or "").strip()
    return MECHANIC_ALIASES.get(m, m)


def _norm3(x: float, y: float, z: float) -> float:
    return sqrt(x * x + y * y + z * z)


def _dot3(ax: float, ay: float, az: float, bx: float, by: float, bz: float) -> float:
    return ax * bx + ay * by + az * bz


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _clamp01(v: float) -> float:
    return _clamp(v, 0.0, 1.0)


def _mechanic_copy(mid: str) -> Dict[str, str]:
    return dict(MECH_COACHING.get(_canonical_mid(mid), {}))


def _quality_bucket(score_0_1: float) -> str:
    if score_0_1 >= 0.72:
        return "good"
    if score_0_1 >= 0.45:
        return "neutral"
    return "bad"


def _coach_template(mid: str, score_0_1: float) -> str:
    meta = _mechanic_copy(mid)
    bucket = _quality_bucket(score_0_1)
    title = MECH_TITLE.get(_canonical_mid(mid), mid)
    score_100 = round(_clamp01(score_0_1) * 100.0, 1)
    pair = meta.get(bucket)
    if isinstance(pair, tuple) and len(pair) == 2:
        return f"{title} {score_100}/100. {pair[0]} {pair[1]}"
    return f"{title} {score_100}/100. This play changed the next touch. Refine your setup, contact, and recovery so the outcome stays easier to control."


def _deterministic_choice(options: List[str], seed: str) -> str:
    if not options:
        return ""
    idx = sum(ord(ch) for ch in str(seed or "")) % len(options)
    return options[idx]


def _coach_sentence_bank(
    mid: str,
    score_0_1: float,
    event: Dict[str, Any],
    observed: Dict[str, Any],
    issue_tags: List[str],
    improvement_tags: List[str],
) -> str:
    title = MECH_TITLE.get(_canonical_mid(mid), mid)
    score_100 = round(_clamp01(score_0_1) * 100.0, 1)
    pressure = str(observed.get("pressure_level", "medium"))
    support = bool(observed.get("support_available"))
    last_man = bool(observed.get("last_man"))
    danger_delta = _safe_float(observed.get("danger_delta", 0.0))
    possession_delta = _safe_float(observed.get("possession_delta", 0.0))
    dist = _safe_float(observed.get("player_ball_distance", 0.0))
    seed = "|".join(
        [
            str(mid),
            str(event.get("event_type", "")),
            str(event.get("reason", "")),
            str(round(_safe_float(event.get("time", 0.0)), 2)),
            ",".join(sorted(issue_tags)),
            ",".join(sorted(improvement_tags)),
            pressure,
            "cover" if support else "nocover",
            "lastman" if last_man else "rotation",
            str(round(danger_delta, 2)),
            str(round(possession_delta, 2)),
            str(round(dist, -1)),
        ]
    )
    bucket = _quality_bucket(score_0_1)

    def line(options: List[str]) -> str:
        return _deterministic_choice(options, seed)

    if mid == "challenge":
        if "easy_counter" in issue_tags or danger_delta > 0.18:
            options = [
                "You challenged from a weak side angle and the ball escaped into danger. Turn in earlier and drive through the center so the 50 stays neutral or rolls safe.",
                "The contest got through you and became a counter the other way. Stay goal-side before you commit and hit with the nose of your car through the middle of the ball.",
                "You went into the challenge without controlling the loss lane, so the ball broke behind you. Protect the inside path first and make the contact more centered.",
                "The exit of the challenge left you out of the play and your team scrambling. Pick the angle that kills the counter, not the one that only tries to win the 50.",
                "You engaged before the ball was winnable and the attacker read through you. Wait half a beat longer and challenge only when the loss lane is still covered.",
            ]
        elif last_man and not support:
            options = [
                "You forced the challenge without safe cover behind you, so the risk was higher than the reward. Delay half a beat and make the attacker give up the ball first.",
                "This challenge happened as last man without teammate support. Keep your goal-side angle longer so a lost 50 does not turn straight into pressure.",
                "As the last defender, this challenge needed more patience than force. Stay between ball and net longer and only commit when the exit stays recoverable.",
                "Without cover behind you, even a neutral challenge is a dangerous trade. Shadow longer and force the attacker to give up the ball by running out of space.",
                "You committed with no one to clean up the rebound. Delay the challenge and hold the inside line until help arrives or the attacker makes the mistake.",
            ]
        elif possession_delta > 0.10 and bucket == "good":
            options = [
                "You met the ball from a strong angle and kept the exit playable for your team. Keep arriving through the center so the challenge stays safe and useful.",
                "You challenged with a stable line and turned the contest into possession. Repeat that same earlier turn-in and nose-first contact.",
                "The challenge produced the best outcome available: the ball came out on your side. Keep reading the contest early so you can control the exit like this more often.",
                "Clean challenge — you won the lane, hit through the ball, and set up the next touch. Lock in that earlier turn-in so this becomes a habit under pressure.",
            ]
        elif bucket == "neutral":
            options = [
                "You got into the contest, but the exit stayed too loose to really help your team. Square up a little earlier so the ball spills into your lane instead of a race.",
                "The challenge was close, but you did not control the outcome after contact. Hit more through the middle so the 50 dies where you can follow it.",
                "You reached the challenge, but the ball still came out as a scramble. Arrive more square and think about where you want the ball to stop, not just where to hit it.",
                "Contact happened, but neither side really won the 50 cleanly. Commit the nose of your car through the center so the exit belongs to you next time.",
                "The challenge landed, but the follow-up was a coin flip. Decide where you want the ball to go before the hit, not after.",
            ]
        else:
            options = [
                "You met the ball from a weak angle and got beaten through the 50. Turn in earlier and make contact with the nose of your car so the challenge stays neutral or rolls to your side.",
                "You arrived late into the contest and the ball squeezed through you. Close the angle sooner and drive more directly through the ball to control the 50.",
                "The challenge happened after the attacker had already won the line. Turn earlier and close the gap before the ball gets to the side of your car.",
                "You engaged from the back foot, so the challenge never had a chance. Read the ball's path sooner and meet it with forward momentum instead of a reaching touch.",
                "The contact was off-center and the opponent broke through clean. Square up the approach and plant the nose of your car into the ball path before they do.",
            ]
        return line(options)

    if mid == "shadow_defense":
        if "lost_goal_side" in issue_tags:
            options = [
                "You gave up goal-side position, so the attacker had the easier path into your half. Recover between ball and net sooner before you think about challenging.",
                "You stopped mirroring from the safe side of the play and lost the defensive line. Keep yourself between the attacker and your goal until the ball is truly winnable.",
                "Goal-side broke down and the attacker had a free lane. Track back earlier and only commit once your car sits between ball and net.",
                "You drifted out of the defensive line and left the shooting lane open. Prioritize getting goal-side again before you think about the challenge.",
            ]
        elif dist > 1400 or "buy_time" in improvement_tags:
            options = [
                "You gave too much space and let the attacker set up freely. Match their speed sooner and hold a tighter line so you can pressure without overcommitting.",
                "The attacker got too comfortable because your shadow distance stayed too loose. Sit a little closer so you can challenge the touch instead of the shot.",
                "You shadowed from too far away, which let the dribbler pick the next move first. Close the cushion sooner while keeping your car goal-side.",
                "Too much cushion means the attacker picks the shot. Tighten the gap so their next touch is the challenge, not the setup.",
                "The space you gave turned into a free read for the attacker. Close two car lengths of distance while staying goal-side.",
            ]
        elif bucket == "good":
            options = [
                "You stayed goal-side and kept the attacker from getting a clean lane. Keep matching their pace and wait for the touch that lets you challenge safely.",
                "Your spacing bought time without giving up the shot for free. Keep that same tighter line and force the play wide before you commit.",
                "Solid shadow — the attacker never got a comfortable touch. Keep mirroring at that same distance so they have to make the mistake, not you.",
                "You held the line and the attacker had no easy next move. Keep reading their speed and waiting for the touch that gives you the safe challenge.",
            ]
        else:
            options = [
                "Your positioning slowed the play, but it still left the attacker too much freedom. Hold a tighter shadow line so you can pressure the ball earlier.",
                "You delayed the attack, but not enough to really limit the options. Close the gap sooner while staying goal-side so you can challenge with control.",
                "You were in the right area, but the spacing still gave the attacker an easy setup. Mirror their pace earlier and take away the comfortable touch.",
                "The shadow delayed the play but didn't deny it. Match the attacker's speed sooner so they lose the option to choose the attack.",
                "You were goal-side, but not close enough to actually force anything. Trim the gap so the attacker has to respect you on every touch.",
            ]
        return line(options)

    if mid == "fifty_fifty_control":
        if "lost_into_danger" in issue_tags:
            options = [
                "Your touch did not absorb the challenge, so the ball spilled into danger. Stay grounded, center your car behind the ball, and deaden the contact into space you can follow.",
                "The 50 popped away from you and became a dangerous second ball. Hit more through the middle and think about softening the exit instead of forcing it forward.",
                "You hit through the contest, but not into controllable space. Let the 50 die closer to your lane so the next touch belongs to you instead of the defense.",
                "The 50 exploded into a bad spot and your team had to scramble. Soften the contact and aim the exit into a lane your team can reach first.",
                "You flipped through the ball and gave away the exit. Stay grounded, settle the touch, and keep the rebound short and controllable.",
            ]
        elif "unsupported_contest" in issue_tags and not support:
            options = [
                "You took the 50 without enough cover behind you, so even a neutral outcome was risky. Make sure the ball stays killable before you commit this hard.",
                "This was a lonely contest without teammate support. If you cannot win it cleanly, absorb the ball and keep the exit shorter and safer.",
                "No backup meant this 50 had to be perfect, and it wasn't. Play it conservatively when you're the only one there and kill the ball instead of launching it.",
                "Without support, any loose exit off a 50 becomes a counter. Center your car, deaden the touch, and keep the ball close until help arrives.",
            ]
        elif bucket == "good":
            options = [
                "You absorbed the contact well and kept the ball playable after the 50. Keep centering your car and preparing your landing so you own the follow-up too.",
                "You controlled the exit of the contest instead of just surviving it. Repeat that same grounded contact and follow-through into the next touch.",
                "The 50 resolved in your favor — the ball stayed in reach and the next touch was yours. Lock in that grounded, centered approach as your default.",
                "Good hands on the 50: centered contact, controlled exit, clean recovery. Keep trusting that approach over the urge to flip through.",
            ]
        else:
            options = [
                "The contest did not fully hurt you, but it still bounced into a race instead of control. Soften the touch more and angle the 50 into your lane.",
                "You survived the contact, but the ball did not stay where you could follow it first. Center the car more cleanly behind the ball before impact.",
                "The 50 stayed alive, but it came out too loose to count as control. Aim to absorb the impact so the ball settles in space you can reach first.",
                "Neutral outcome, but the 50 still felt like a coin flip. Tighten the car angle and absorb instead of hitting through.",
                "You didn't lose the 50, but you didn't win it either. Softer contact into a chosen lane turns these into possessions instead of races.",
            ]
        return line(options)

    if mid == "kickoff":
        if "kickoff_lost" in issue_tags:
            options = [
                "You lost the center of the kickoff and gave the opponent the better exit. Drive through the middle sooner and land ready for the next bounce.",
                "The first touch did not stay neutral, so the kickoff handed away the better lane. Hit more through the center of the ball and recover faster after contact.",
                "Your kickoff contact came from the wrong side of the ball, so the exit favored the opponent. Line up straighter and recover with the second touch in mind.",
                "The opponent got the second ball because your kickoff contact leaked off-center. Square the nose of your car and drive through the middle.",
                "This kickoff tilted toward their side immediately. Fix the entry angle and hit with both wheels framing the ball, not just one.",
            ]
        elif "dangerous_exit" in issue_tags:
            options = [
                "The kickoff touch left a dangerous second ball behind you. Even if you cannot win it cleanly, angle the exit so the opponent does not get a free counter.",
                "You made contact, but the kickoff still leaked into a bad lane for your team. Protect the loss lane with your landing and keep the ball from escaping central danger.",
                "The ball came off the kickoff in a spot your team had to chase down. Aim the contact so the rebound favors cover, not the opponent's counter.",
                "Even touching the ball didn't save this kickoff — the exit was still dangerous. Land facing the next play so you can cover the bad bounce immediately.",
            ]
        elif bucket == "good":
            options = [
                "You arrived on time and turned the kickoff into a playable outcome for your team. Keep hitting through the middle and recovering immediately to own the next touch.",
                "Your entry and recovery gave the kickoff a stable exit. Repeat that same centered contact so the opponent cannot steal the second ball.",
                "Strong kickoff — clean contact, controlled exit, fast recovery. Keep that muscle memory and this becomes free possession every time.",
                "The kickoff favored your team and you landed ready to follow up. Lock in the centered approach and this consistency pays off every match.",
            ]
        else:
            options = [
                "The kickoff stayed playable, but it did not create enough advantage after contact. Tighten the approach angle and make the exit die where you can follow first.",
                "You reached the ball, but the first touch was still too loose. Drive straighter through the center and recover facing the second touch.",
                "You got to the kickoff, but the exit still turned into a scramble. Hit more centrally and land with momentum toward the next bounce.",
                "Neutral kickoff that didn't create an advantage for either side. Aim the exit into your half of the field so the second touch is yours.",
                "You made the kickoff but didn't control it. A straighter line into the ball and a faster recovery turns these into clean possessions.",
            ]
        return line(options)

    if mid == "aerial_offense":
        if "no_threat_created" in issue_tags:
            options = [
                "You reached the ball in the air, but the touch did not create enough threat afterward. Read the takeoff sooner and hit through the ball with more forward intent.",
                "The aerial made contact, but the defense did not have to respect the result. Attack the ball earlier so the touch carries pace or direction they have to answer.",
                "You got to the ball in the air but the defender wasn't in trouble. Commit to the takeoff sooner and hit with shot power, not just reach.",
                "The aerial connected without threatening the net. Read the setup one touch earlier and punch through the ball instead of cushioning it.",
            ]
        elif "gave_up_pressure" in issue_tags:
            options = [
                "You touched the ball, but the play lost pressure right after. Recover forward faster so the aerial leads to a second play instead of a reset.",
                "The first airborne touch happened, but it did not keep the attack alive. Hit with more intent and land ready to pressure the next bounce immediately.",
                "The aerial killed your own momentum. Recover toward the ball after contact so the second play is yours, not theirs.",
                "You went up for the hit but landed out of the play. Keep your trajectory forward through contact so you can double up on the follow-up touch.",
            ]
        elif bucket == "good":
            options = [
                "You met the ball with intent and turned the aerial into real attacking pressure. Keep attacking early and recovering forward so the play stays dangerous.",
                "This aerial created a useful attacking touch instead of empty contact. Keep meeting the ball sooner and carrying momentum through the play.",
                "Clean aerial — the defense had to respect it and your team kept the play alive. Keep committing to the takeoff that early.",
                "You turned airtime into pressure. Repeat that same early read and forward contact and these become scoring chances.",
            ]
        else:
            options = [
                "You made the aerial touch, but it still lacked enough threat to punish the defense. Attack a little earlier so the ball leaves your car with purpose.",
                "The contact was there, but the aerial did not tilt the play in your favor. Meet the ball sooner and hit through it instead of just reaching it.",
                "The aerial was fine, but not decisive. Go for the shot-making angle instead of the safe touch so the defense has to answer.",
                "You got the touch but not the threat. Attack the ball earlier in its arc so the contact has real pace behind it.",
            ]
        return line(options)

    if mid == "aerial_defense":
        if "failed_clear_distance" in issue_tags:
            options = [
                "You got the touch, but the clear did not move danger far enough from your half. Beat the ball a little earlier and focus on distance before anything fancy.",
                "The save happened, but the ball stayed too playable for the other team. Clear with more separation so the threat does not recycle immediately.",
                "You saved the ball but left the rebound inside your own half. Take off sooner and swing through for real distance on the clear.",
                "The clear was short and the opponent got another crack at it. Prioritize depth over style — get the ball past midfield first.",
            ]
        elif "double_commit" in issue_tags:
            options = [
                "You went for the defensive aerial with overlapping coverage, which made the clear less stable. Space the play out more so one touch fully removes the danger.",
                "This aerial came with a double-commit look, so even the touch carried extra risk. Respect the spacing first, then attack the ball from the cleaner angle.",
                "Two cars went for the same save and nobody cleaned up. Call off if your teammate is already committed and set up as the second-wave defender.",
                "The double-commit cost you the recovery. Trust the teammate who gets there first and prep the next touch from shadow instead.",
            ]
        elif bucket == "good":
            options = [
                "You removed danger well and sent the ball into a safer lane after the aerial. Keep prioritizing the safe clear first, then add distance once the threat is gone.",
                "The defensive aerial actually relieved pressure instead of recycling it. Keep winning the dangerous lane early and clearing to the wide side.",
                "Clean defensive aerial — danger gone, team reset. Lock in that early takeoff and wide-clear habit.",
                "You beat the ball to the dangerous spot and got real distance on the clear. Keep making that read early and the save stays routine.",
            ]
        else:
            options = [
                "You made the defensive touch, but the clear did not fully relieve pressure. Use a wider or earlier contact so the rebound stays harder to punish.",
                "The save helped for a moment, but the ball stayed too central afterward. Favor the safer wide clear so the defense can reset behind you.",
                "The touch prevented a goal but not the follow-up chance. Aim the ball wide toward the corners, not back into the slot.",
                "You got there, but the rebound was still dangerous. Take off a beat earlier so you can choose the clear direction instead of just reaching.",
            ]
        return line(options)

    if mid == "flicking":
        if "low_power" in issue_tags or "no_threat_created" in issue_tags:
            options = [
                "You had control, but the flick came late and without enough lift. Pop the ball earlier from a balanced dribble so the flick has more height and forces a harder save.",
                "The setup looked playable, but the release did not threaten the defender enough. Stabilize the carry first and snap the flick sooner so it launches with more pop.",
                "The flick fizzled — not enough power to force a save. Flip through the ball with the nose down, not the roof, so you transfer real pace.",
                "You released the flick too flat. Load it on the hood longer and pop up first so the flick gets altitude the defender can't ignore.",
            ]
        elif bucket == "good":
            options = [
                "You turned control into a threatening release with good timing and enough lift. Keep forcing the defender to respect the flick by popping early from a balanced carry.",
                "The flick converted dribble control into a real attacking touch. Repeat that same earlier pop and cleaner release through the ball.",
                "Clean flick — good lift, good timing, real threat. Keep popping from a stable carry and the defender has to commit every time.",
                "You caught the defender on their heels with that flick. Lock in the earlier release habit.",
            ]
        else:
            options = [
                "The setup was there, but the flick did not punish the defender strongly enough. Pop earlier and keep the dribble more centered before you release.",
                "You got to the release, but the ball left without enough threat. Carry more cleanly and flick before the defender gets comfortable under it.",
                "The flick existed but didn't force the save. Release when the defender is committed, not already set — timing over power.",
                "You flicked, but the defender read it. Disguise the release with a setup touch or carry angle change first.",
            ]
        return line(options)

    if mid == "carrying_dribbling":
        if "immediate_loss" in issue_tags:
            options = [
                "You had the ball briefly, but control broke down before the play turned into a threat. Keep the dribble tighter to your hood so the first challenge does not end it instantly.",
                "The carry started, but the ball got away from you too fast. Protect it with your car and keep it closer before trying to progress the play.",
                "The ball popped off on the first touch. Slow the initial scoop and balance the dribble before you try to move with it.",
                "The carry died as soon as pressure showed. Keep the first touch softer and hug the ball with the nose down to absorb contact.",
                "Control broke down the moment pressure arrived. Hug the ball with the nose of your car and treat the first challenge as something to absorb, not dodge.",
            ]
        elif "carry_under_low_pressure" in issue_tags:
            options = [
                "You had time and space, but the dribble still did not become a threatening next action. Turn that calm carry into a flick, cut, or low 50 before pressure arrives.",
                "This was a low-pressure carry that still stayed too passive. Use the extra space to choose the next move earlier instead of letting the defender reset.",
                "Free time on the carry and nothing came of it. Set up the flick or cut while the defender is still deciding.",
                "You held the ball too long with nobody on you. Turn that calm into a committed next touch before the defender recovers.",
                "The carry was controlled but the opportunity window closed before you did anything with it. Decide on the next action within the first second of control — flick, cut, or pass.",
            ]
        elif bucket == "good":
            options = [
                "You kept the ball close and turned the carry into a playable attacking option. Keep protecting the ball with your car and decide early whether the next touch is a flick, cut, or low 50.",
                "The dribble stayed controlled long enough to create a real option. Keep the ball tight and make the defender answer your next move instead of theirs.",
                "Strong carry — controlled, protected, threatening. Lock in that same close control as your default.",
                "You forced the defender to react to your choice instead of the other way around. Keep the ball tight like that and these become setups for goals.",
                "The carry created real forward pressure and the defender had to respect it. Commit to that same tight-hood approach and these turns into shot attempts more often.",
            ]
        else:
            options = [
                "You had control for a moment, but the dribble did not turn into enough of a threat afterward. Keep the ball tighter and choose the next action before the defender closes the gap.",
                "The carry stayed alive, but it still did not pressure the defense enough. Keep the ball closer and convert the dribble earlier into a decision touch.",
                "The dribble was fine, but the play never materialized. Commit to the next move earlier instead of carrying until the defender catches up.",
                "You held the ball but didn't make anything happen. Tighter control plus a decisive flick or pass turns these into real scoring chances.",
                "The carry existed, but without urgency the defense caught up. Decide within a second whether this carry is heading toward a flick, cut, or shot.",
            ]
        return line(options)

    return _coach_template(mid, score_0_1)


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _player_frame(frame: Dict[str, Any], player: str) -> Dict[str, Any] | None:
    for p in frame.get("players", []) or []:
        if str(p.get("name", "")) == player:
            return p
    return None


def _player_team(player: str, player_teams: Dict[str, Any]) -> int:
    try:
        t = int(player_teams.get(player, -1))
    except Exception:
        t = -1
    return t


def _own_goal_y(team: int) -> float:
    return -5120.0 if team == 0 else 5120.0


def _opp_goal_y(team: int) -> float:
    return 5120.0 if team == 0 else -5120.0


def _team_for_player_name(name: str, player_teams: Dict[str, Any], fallback_team: int) -> int:
    try:
        t = int(player_teams.get(name, fallback_team))
    except Exception:
        t = fallback_team
    return t if t in (0, 1) else fallback_team


def _player_ball_dist(frame: Dict[str, Any], player: str) -> float:
    p = _player_frame(frame, player)
    if not p:
        return 99999.0
    b = frame.get("ball", {}) or {}
    return _norm3(
        _safe_float(p.get("x", 0.0)) - _safe_float(b.get("x", 0.0)),
        _safe_float(p.get("y", 0.0)) - _safe_float(b.get("y", 0.0)),
        _safe_float(p.get("z", 0.0)) - _safe_float(b.get("z", 0.0)),
    )


def _ball_speed(frame: Dict[str, Any]) -> float:
    b = frame.get("ball", {}) or {}
    return _norm3(_safe_float(b.get("vx", 0.0)), _safe_float(b.get("vy", 0.0)), _safe_float(b.get("vz", 0.0)))


def _player_speed(frame: Dict[str, Any], player: str) -> float:
    p = _player_frame(frame, player)
    if not p:
        return 0.0
    return _norm3(_safe_float(p.get("vx", 0.0)), _safe_float(p.get("vy", 0.0)), _safe_float(p.get("vz", 0.0)))


def _rel_speed_player_ball(frame: Dict[str, Any], player: str) -> float:
    p = _player_frame(frame, player)
    if not p:
        return 99999.0
    b = frame.get("ball", {}) or {}
    return _norm3(
        _safe_float(p.get("vx", 0.0)) - _safe_float(b.get("vx", 0.0)),
        _safe_float(p.get("vy", 0.0)) - _safe_float(b.get("vy", 0.0)),
        _safe_float(p.get("vz", 0.0)) - _safe_float(b.get("vz", 0.0)),
    )


def _nearest_opponent_dist_ball(frame: Dict[str, Any], player: str, player_teams: Dict[str, Any], tracked_team: int) -> float:
    b = frame.get("ball", {}) or {}
    bx = _safe_float(b.get("x", 0.0))
    by = _safe_float(b.get("y", 0.0))
    bz = _safe_float(b.get("z", 0.0))
    best = 99999.0
    for op in frame.get("players", []) or []:
        name = str(op.get("name", ""))
        if name == player:
            continue
        if _team_for_player_name(name, player_teams, tracked_team) == tracked_team:
            continue
        d = _norm3(_safe_float(op.get("x", 0.0)) - bx, _safe_float(op.get("y", 0.0)) - by, _safe_float(op.get("z", 0.0)) - bz)
        if d < best:
            best = d
    return best


def _nearest_opponent_speed(frame: Dict[str, Any], player: str, player_teams: Dict[str, Any], tracked_team: int) -> float:
    pself = _player_frame(frame, player)
    if not pself:
        return 0.0
    sx = _safe_float(pself.get("x", 0.0))
    sy = _safe_float(pself.get("y", 0.0))
    sz = _safe_float(pself.get("z", 0.0))
    best_d = 99999.0
    best_speed = 0.0
    for op in frame.get("players", []) or []:
        name = str(op.get("name", ""))
        if name == player:
            continue
        if _team_for_player_name(name, player_teams, tracked_team) == tracked_team:
            continue
        d = _norm3(_safe_float(op.get("x", 0.0)) - sx, _safe_float(op.get("y", 0.0)) - sy, _safe_float(op.get("z", 0.0)) - sz)
        if d < best_d:
            best_d = d
            best_speed = _norm3(_safe_float(op.get("vx", 0.0)), _safe_float(op.get("vy", 0.0)), _safe_float(op.get("vz", 0.0)))
    return best_speed


def _best_team_ball_dist(frame: Dict[str, Any], player_teams: Dict[str, Any], team: int) -> float:
    b = frame.get("ball", {}) or {}
    bx = _safe_float(b.get("x", 0.0))
    by = _safe_float(b.get("y", 0.0))
    bz = _safe_float(b.get("z", 0.0))
    best = 99999.0
    for pl in frame.get("players", []) or []:
        name = str(pl.get("name", ""))
        if _team_for_player_name(name, player_teams, team) != team:
            continue
        d = _norm3(_safe_float(pl.get("x", 0.0)) - bx, _safe_float(pl.get("y", 0.0)) - by, _safe_float(pl.get("z", 0.0)) - bz)
        if d < best:
            best = d
    return best


def _teammate_double_commit(frame: Dict[str, Any], player: str, player_teams: Dict[str, Any], tracked_team: int, tracked_d_pb: float) -> bool:
    b = frame.get("ball", {}) or {}
    bx = _safe_float(b.get("x", 0.0))
    by = _safe_float(b.get("y", 0.0))
    bz = _safe_float(b.get("z", 0.0))
    for pl in frame.get("players", []) or []:
        name = str(pl.get("name", ""))
        if name == player:
            continue
        if _team_for_player_name(name, player_teams, tracked_team) != tracked_team:
            continue
        d = _norm3(_safe_float(pl.get("x", 0.0)) - bx, _safe_float(pl.get("y", 0.0)) - by, _safe_float(pl.get("z", 0.0)) - bz)
        if d <= 850.0 and d <= tracked_d_pb + 120.0:
            return True
    return False


def _find_next_idx_by_time(times: List[float], idx: int, dt: float) -> int:
    t = times[idx] + max(0.0, dt)
    j = idx
    while j + 1 < len(times) and times[j] < t:
        j += 1
    return j


def _ball_forward_speed_to_opp(frame: Dict[str, Any], team: int) -> float:
    vy = _safe_float((frame.get("ball", {}) or {}).get("vy", 0.0))
    return vy if team == 0 else -vy


def _ball_toward_own_goal_fast(f0: Dict[str, Any], f1: Dict[str, Any], team: int) -> bool:
    b0 = f0.get("ball", {}) or {}
    b1 = f1.get("ball", {}) or {}
    y0 = _safe_float(b0.get("y", 0.0))
    y1 = _safe_float(b1.get("y", 0.0))
    vy1 = _safe_float(b1.get("vy", 0.0))
    toward_own = (team == 0 and y1 < y0 - 100.0 and vy1 <= -900.0) or (team == 1 and y1 > y0 + 100.0 and vy1 >= 900.0)
    center_lane = abs(_safe_float(b1.get("x", 0.0))) < 1800.0
    return bool(toward_own and center_lane)


def _ball_dir_flip(frame0: Dict[str, Any], frame1: Dict[str, Any]) -> bool:
    b0 = frame0.get("ball", {}) or {}
    b1 = frame1.get("ball", {}) or {}
    vx0 = _safe_float(b0.get("vx", 0.0))
    vy0 = _safe_float(b0.get("vy", 0.0))
    vz0 = _safe_float(b0.get("vz", 0.0))
    vx1 = _safe_float(b1.get("vx", 0.0))
    vy1 = _safe_float(b1.get("vy", 0.0))
    vz1 = _safe_float(b1.get("vz", 0.0))
    s0 = _norm3(vx0, vy0, vz0)
    s1 = _norm3(vx1, vy1, vz1)
    if s0 < 250.0 or s1 < 250.0:
        return False
    cos_th = _dot3(vx0, vy0, vz0, vx1, vy1, vz1) / max(1e-6, s0 * s1)
    return cos_th < -0.2


def _touch_confidence(frame0: Dict[str, Any], frame1: Dict[str, Any], p: Dict[str, Any]) -> float:
    b0 = frame0.get("ball", {}) or {}
    b1 = frame1.get("ball", {}) or {}
    px = _safe_float(p.get("x", 0.0))
    py = _safe_float(p.get("y", 0.0))
    pz = _safe_float(p.get("z", 0.0))
    bx = _safe_float(b0.get("x", 0.0))
    by = _safe_float(b0.get("y", 0.0))
    bz = _safe_float(b0.get("z", 0.0))
    d = _norm3(px - bx, py - by, pz - bz)
    if d > 260.0:
        return 0.0
    dvx = _safe_float(b1.get("vx", 0.0)) - _safe_float(b0.get("vx", 0.0))
    dvy = _safe_float(b1.get("vy", 0.0)) - _safe_float(b0.get("vy", 0.0))
    dvz = _safe_float(b1.get("vz", 0.0)) - _safe_float(b0.get("vz", 0.0))
    to_ball_x = bx - px
    to_ball_y = by - py
    to_ball_z = bz - pz
    to_mag = max(1e-6, _norm3(to_ball_x, to_ball_y, to_ball_z))
    dv_mag = _norm3(dvx, dvy, dvz)
    align = 0.0 if dv_mag < 1e-6 else _dot3(to_ball_x / to_mag, to_ball_y / to_mag, to_ball_z / to_mag, dvx / dv_mag, dvy / dv_mag, dvz / dv_mag)
    prox = _clamp01((260.0 - d) / 260.0)
    align01 = _clamp01((align + 1.0) * 0.5)
    return _clamp01(0.65 * prox + 0.35 * align01)


def _add_event(events: List[Dict[str, Any]], mechanic: str, t: float, score: float, reason: str, **extra: Any) -> None:
    q = _clamp01(score)
    label = "good" if q >= 0.66 else ("bad" if q < 0.42 else "neutral")
    payload = {
        "mechanic_id": mechanic,
        "short": MECH_SHORT.get(mechanic, mechanic[:4].upper()),
        "time": float(t),
        "quality_score": round(float(q), 4),
        "quality_label": label,
        "reason": reason,
    }
    payload.update(dict(extra or {}))
    events.append(payload)


def _apply_event_context(
    event: Dict[str, Any],
    *,
    timeline: List[Dict[str, Any]],
    times: List[float],
    idx: int,
    player: str,
    player_teams: Dict[str, Any],
) -> Dict[str, Any]:
    ctx = frame_context(timeline[idx], player, player_teams or {})
    window = summarize_event_window(timeline, times, idx, player, player_teams or {})
    event["context"] = ctx
    event["window"] = window
    event["gamemode"] = str(ctx.get("gamemode", "2v2"))
    event["pressure_level"] = str(ctx.get("pressure_level", "medium"))
    event["event_confidence_0_1"] = round(
        _clamp01(
            0.42
            + 0.18 * (1.0 if ctx.get("player_ball_distance") is not None else 0.0)
            + 0.20 * (1.0 - abs(_safe_float(window.get("possession_delta", 0.0))))
            + 0.20 * (1.0 - abs(_safe_float(window.get("danger_delta", 0.0))))
        ),
        3,
    )
    _enrich_event_text(event)
    return event


def _merge_unique_strings(*groups: List[str] | None) -> List[str]:
    merged: List[str] = []
    seen = set()
    for group in groups:
        for item in group or []:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            merged.append(text)
    return merged


def _mechanic_tag_label(tag: str) -> str:
    mapping = {
        "flip_reset": "Flip reset in play",
        "ceiling_shot": "Ceiling play in use",
        "double_tap": "Double tap in play",
    }
    key = str(tag or "").strip()
    return mapping.get(key, key.replace("_", " ").title())


def _attach_mechanic_tags(event: Dict[str, Any], *tags: str) -> Dict[str, Any]:
    normalized = [str(tag or "").strip() for tag in tags if str(tag or "").strip()]
    if not normalized:
        return event
    merged_tags = _merge_unique_strings(list(event.get("mechanic_tags", []) or []), normalized)
    event["mechanic_tags"] = merged_tags
    labels = [_mechanic_tag_label(tag) for tag in merged_tags]
    event["mechanic_tag_labels"] = _merge_unique_strings(list(event.get("mechanic_tag_labels", []) or []), labels)
    return event


def _merge_event_payload(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    base["mechanic_tags"] = _merge_unique_strings(
        list(base.get("mechanic_tags", []) or []),
        list(extra.get("mechanic_tags", []) or []),
    )
    base["mechanic_tag_labels"] = _merge_unique_strings(
        list(base.get("mechanic_tag_labels", []) or []),
        list(extra.get("mechanic_tag_labels", []) or []),
    )
    base["issue_tags"] = _merge_unique_strings(
        list(base.get("issue_tags", []) or []),
        list(extra.get("issue_tags", []) or []),
    )
    base["improvement_tags"] = _merge_unique_strings(
        list(base.get("improvement_tags", []) or []),
        list(extra.get("improvement_tags", []) or []),
    )
    if not str(base.get("event_type", "")).strip() and str(extra.get("event_type", "")).strip():
        base["event_type"] = str(extra.get("event_type", ""))
    return base


def _enrich_event_text(event: Dict[str, Any]) -> None:
    """Populate template_title and template_body in-place using contextual data."""
    mid = _canonical_mid(str(event.get("mechanic_id", "") or ""))
    if not mid:
        return
    q = _clamp01(_safe_float(event.get("quality_score", 0.5)))
    title_label = MECH_TITLE.get(mid, mid)
    # Flag-only mechanics: label only, no coaching advice
    if mid in FLAG_MECHANICS:
        event["template_title"] = title_label
        event["template_body"] = ""
        return
    ctx = event.get("context", {}) or {}
    window = event.get("window", {}) or {}
    observed = {
        "pressure_level": str(event.get("pressure_level", ctx.get("pressure_level", "medium"))),
        "support_available": bool(ctx.get("support_available")),
        "last_man": bool(ctx.get("last_man")),
        "danger_delta": _safe_float(window.get("danger_delta", 0.0)),
        "possession_delta": _safe_float(window.get("possession_delta", 0.0)),
        "player_ball_distance": _safe_float(ctx.get("player_ball_distance", 0.0)),
    }
    issue_tags = list(event.get("issue_tags", []) or [])
    improvement_tags = list(event.get("improvement_tags", []) or [])
    title_prefix = "Strong" if q >= 0.7 else ("Mixed" if q >= 0.45 else "Needs Work")
    event["template_title"] = f"{title_prefix} {title_label}"
    event["template_body"] = _coach_sentence_bank(mid, q, event, observed, issue_tags, improvement_tags)


def _closing_speed_toward_ball(frame: Dict[str, Any], player: str) -> float:
    p = _player_frame(frame, player)
    if not p:
        return 0.0
    b = frame.get("ball", {}) or {}
    tx = _safe_float(b.get("x", 0.0)) - _safe_float(p.get("x", 0.0))
    ty = _safe_float(b.get("y", 0.0)) - _safe_float(p.get("y", 0.0))
    tz = _safe_float(b.get("z", 0.0)) - _safe_float(p.get("z", 0.0))
    mag = max(1e-6, _norm3(tx, ty, tz))
    ux, uy, uz = tx / mag, ty / mag, tz / mag
    vx = _safe_float(p.get("vx", 0.0))
    vy = _safe_float(p.get("vy", 0.0))
    vz = _safe_float(p.get("vz", 0.0))
    return _dot3(vx, vy, vz, ux, uy, uz)


def _ball_center_slow(frame: Dict[str, Any]) -> bool:
    b = frame.get("ball", {}) or {}
    bx = _safe_float(b.get("x", 0.0))
    by = _safe_float(b.get("y", 0.0))
    bz = _safe_float(b.get("z", 0.0))
    dist = _norm3(bx, by, bz - 93.0)
    return dist <= KICKOFF_CENTER_MAX_DIST and _ball_speed(frame) <= KICKOFF_BALL_SPEED_MAX


def _is_kickoff_spawn_position(x: float, y: float, z: float) -> bool:
    if abs(z) > KICKOFF_SPAWN_Z_MAX:
        return False
    ax = abs(x)
    ay = abs(y)
    for sx, sy in KICKOFF_SPAWN_POINTS:
        if abs(ax - sx) <= KICKOFF_SPAWN_XY_TOL and abs(ay - sy) <= KICKOFF_SPAWN_XY_TOL:
            return True
    return False


def _cars_in_kickoff_spawns(frame: Dict[str, Any]) -> bool:
    players = list(frame.get("players", []) or [])
    if not players:
        return False
    matches = 0
    for player in players:
        px = _safe_float(player.get("x", 0.0))
        py = _safe_float(player.get("y", 0.0))
        pz = _safe_float(player.get("z", 0.0))
        if _is_kickoff_spawn_position(px, py, pz):
            matches += 1
    return matches >= max(2, int(len(players) * 0.6))


# Broader "ball is still in the kickoff zone" check — used to suppress challenge/50-50
# even when formal kickoff-window detection misses (e.g. slow approach, rogue touch time).
_KICKOFF_ZONE_RADIUS = 700.0      # xy distance from centre
_KICKOFF_ZONE_BALL_SPD_MAX = 600.0  # ball hasn't been hit hard yet
_KICKOFF_TOUCH_ZONE_RADIUS = 900.0
_KICKOFF_TOUCH_MAX_BALL_Z = 300.0
_KICKOFF_CENTER_DECAY_S = 0.45
_CHALLENGE_APPROACH_LOOKBACK_S = 0.22
_CHALLENGE_MIN_APPROACH_ALIGNMENT = 0.58
_CHALLENGE_MIN_APPROACH_CLOSING = 260.0
_CHALLENGE_MIN_DISTANCE_GAIN = 120.0
_CHALLENGE_MAX_INTERCEPT_S = 1.35
_FIFTY_OPP_CONVERGE_SPEED = 220.0
_FIFTY_MAX_PRE_IMPACT_GAP = 0.18
_FLIP_RESET_MIN_BALL_Z = 220.0
_FLIP_RESET_MIN_PLAYER_Z = 140.0
_FLIP_RESET_MAX_DIST = 230.0
_FLIP_RESET_MAX_XY_GAP = 120.0
_FLIP_RESET_MAX_Z_GAP = 120.0
_FLIP_RESET_MAX_PLAYER_Z = 1650.0
_FLIP_RESET_MIN_AIRBORNE_S = 0.22
_FLIP_RESET_MIN_USE_DELAY_S = 0.08
_FLIP_RESET_MAX_USE_DELAY_S = 1.7
_FLIP_RESET_MIN_POST_SPEED = 1100.0
_FLICK_MIN_CARRY_S = 0.40
_FLICK_GROUNDED_LOOKBACK_S = 0.60
_FLICK_GROUNDED_PZ_MAX = 80.0
_FLICK_MAX_BALL_HEIGHT = 210.0
_FLICK_MAX_REL_SPEED = 520.0
_FLICK_MAX_BALL_X_OFFSET = 130.0
_FLICK_MAX_BALL_Y_OFFSET = 150.0
_FLICK_MIN_RELEASE_S = 0.05
_FLICK_MAX_RELEASE_S = 0.35
_FLICK_MIN_POST_FORWARD_GAIN = 260.0
_FLICK_MIN_POST_UP_GAIN = 120.0


def _ball_in_kickoff_zone(frame: Dict[str, Any]) -> bool:
    """Return True if ball is still close to centre-field at relatively low speed."""
    b = frame.get("ball", {}) or {}
    bx = _safe_float(b.get("x", 0.0))
    by = _safe_float(b.get("y", 0.0))
    dist_xy = (bx ** 2 + by ** 2) ** 0.5
    return dist_xy <= _KICKOFF_ZONE_RADIUS and _ball_speed(frame) <= _KICKOFF_ZONE_BALL_SPD_MAX


def _ball_near_kickoff_touch_zone(frame: Dict[str, Any]) -> bool:
    b = frame.get("ball", {}) or {}
    bx = _safe_float(b.get("x", 0.0))
    by = _safe_float(b.get("y", 0.0))
    bz = _safe_float(b.get("z", 0.0))
    dist_xy = (bx ** 2 + by ** 2) ** 0.5
    return dist_xy <= _KICKOFF_TOUCH_ZONE_RADIUS and 60.0 <= bz <= _KICKOFF_TOUCH_MAX_BALL_Z


def _approach_alignment_to_ball(frame: Dict[str, Any], player: str) -> float:
    p = _player_frame(frame, player)
    if not p:
        return 0.0
    b = frame.get("ball", {}) or {}
    tx = _safe_float(b.get("x", 0.0)) - _safe_float(p.get("x", 0.0))
    ty = _safe_float(b.get("y", 0.0)) - _safe_float(p.get("y", 0.0))
    tz = _safe_float(b.get("z", 0.0)) - _safe_float(p.get("z", 0.0))
    mag = max(1e-6, _norm3(tx, ty, tz))
    ux, uy, uz = tx / mag, ty / mag, tz / mag
    vx = _safe_float(p.get("vx", 0.0))
    vy = _safe_float(p.get("vy", 0.0))
    vz = _safe_float(p.get("vz", 0.0))
    speed = max(1e-6, _norm3(vx, vy, vz))
    return _dot3(vx / speed, vy / speed, vz / speed, ux, uy, uz)


def _time_to_intercept_estimate(frame: Dict[str, Any], player: str) -> float:
    dist = _player_ball_dist(frame, player)
    closing = _closing_speed_toward_ball(frame, player)
    if closing <= 1.0:
        return 999.0
    return dist / max(1.0, closing)


def _distance_gain_to_ball(
    timeline: List[Dict[str, Any]],
    player: str,
    start_idx: int,
    end_idx: int,
) -> float:
    if not timeline:
        return 0.0
    start_idx = max(0, min(start_idx, len(timeline) - 1))
    end_idx = max(0, min(end_idx, len(timeline) - 1))
    return _player_ball_dist(timeline[start_idx], player) - _player_ball_dist(timeline[end_idx], player)


def _approach_commitment_window(
    timeline: List[Dict[str, Any]],
    times: List[float],
    player: str,
    idx: int,
    *,
    lookback_s: float = _CHALLENGE_APPROACH_LOOKBACK_S,
) -> Dict[str, float | bool]:
    start_idx = idx
    while start_idx > 0 and (times[idx] - times[start_idx - 1]) <= lookback_s:
        start_idx -= 1

    alignments: List[float] = []
    closings: List[float] = []
    positive_samples = 0
    for j in range(start_idx, idx + 1):
        align = _approach_alignment_to_ball(timeline[j], player)
        closing = _closing_speed_toward_ball(timeline[j], player)
        alignments.append(align)
        closings.append(closing)
        if align >= _CHALLENGE_MIN_APPROACH_ALIGNMENT and closing >= _CHALLENGE_MIN_APPROACH_CLOSING:
            positive_samples += 1

    distance_gain = _distance_gain_to_ball(timeline, player, start_idx, idx)
    mean_alignment = mean(alignments) if alignments else 0.0
    mean_closing = mean(closings) if closings else 0.0
    time_to_intercept = _time_to_intercept_estimate(timeline[idx], player)
    committed = (
        positive_samples >= max(2, min(3, idx - start_idx + 1))
        and mean_alignment >= _CHALLENGE_MIN_APPROACH_ALIGNMENT
        and mean_closing >= _CHALLENGE_MIN_APPROACH_CLOSING
        and distance_gain >= _CHALLENGE_MIN_DISTANCE_GAIN
        and time_to_intercept <= _CHALLENGE_MAX_INTERCEPT_S
    )
    return {
        "committed": committed,
        "mean_alignment": round(mean_alignment, 3),
        "mean_closing": round(mean_closing, 2),
        "distance_gain": round(distance_gain, 2),
        "time_to_intercept": round(time_to_intercept, 3),
    }


def _nearest_opponent_to_ball(
    frame: Dict[str, Any],
    player: str,
    player_teams: Dict[str, Any],
    tracked_team: int,
) -> Tuple[str, float]:
    b = frame.get("ball", {}) or {}
    bx = _safe_float(b.get("x", 0.0))
    by = _safe_float(b.get("y", 0.0))
    bz = _safe_float(b.get("z", 0.0))
    best_name = ""
    best_dist = 99999.0
    for op in frame.get("players", []) or []:
        name = str(op.get("name", ""))
        if name == player:
            continue
        if _team_for_player_name(name, player_teams, tracked_team) == tracked_team:
            continue
        dist = _norm3(_safe_float(op.get("x", 0.0)) - bx, _safe_float(op.get("y", 0.0)) - by, _safe_float(op.get("z", 0.0)) - bz)
        if dist < best_dist:
            best_name = name
            best_dist = dist
    return best_name, best_dist


def _opponent_contest_ready(
    frame: Dict[str, Any],
    player: str,
    player_teams: Dict[str, Any],
    tracked_team: int,
) -> Tuple[bool, str, float]:
    opp_name, opp_dist = _nearest_opponent_to_ball(frame, player, player_teams, tracked_team)
    if not opp_name:
        return False, "", 99999.0
    opp_closing = _closing_speed_toward_ball(frame, opp_name)
    return opp_dist <= 420.0 and opp_closing >= _FIFTY_OPP_CONVERGE_SPEED, opp_name, opp_dist


def _frame_has_kickoff_context(
    frame: Dict[str, Any],
    t: float,
    kickoff_windows: List[Tuple[float, float]],
) -> bool:
    if any(start <= t <= end for start, end in kickoff_windows):
        return True
    if bool(frame.get("is_kickoff_pause")):
        return True
    if bool(frame.get("is_goal_pause")) and _ball_center_slow(frame) and _cars_in_kickoff_spawns(frame):
        return True
    if _ball_center_slow(frame) and not bool(frame.get("active_play", True)):
        return True
    if _ball_in_kickoff_zone(frame) and not bool(frame.get("active_play", True)):
        return True
    return False


def _frame_is_kickoff_reset_state(frame: Dict[str, Any]) -> bool:
    return _ball_center_slow(frame) and _cars_in_kickoff_spawns(frame)


def _collect_kickoff_reset_windows(
    timeline: List[Dict[str, Any]],
    times: List[float],
) -> List[Tuple[float, float]]:
    windows: List[Tuple[float, float]] = []
    i = 0
    while i < len(timeline):
        if not _frame_is_kickoff_reset_state(timeline[i]):
            i += 1
            continue
        start_t = times[i]
        end_t = start_t
        i += 1
        while i < len(timeline) and _frame_is_kickoff_reset_state(timeline[i]):
            end_t = times[i]
            i += 1
        windows.append((start_t, end_t))
    return windows


def _coerce_kickoff_windows(raw_windows: Any) -> List[Tuple[float, float]]:
    windows: List[Tuple[float, float]] = []
    for raw in raw_windows or []:
        start: Any = None
        end: Any = None
        if isinstance(raw, dict):
            start = raw.get("start_s", raw.get("start", raw.get("start_t")))
            end = raw.get("end_s", raw.get("first_touch_s", raw.get("end", raw.get("end_t"))))
        elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
            start, end = raw[0], raw[1]
        start_f = _safe_float(start, -1.0)
        end_f = _safe_float(end, start_f)
        if start_f < 0.0:
            continue
        if end_f < start_f:
            end_f = start_f
        windows.append((start_f, end_f))
    windows.sort(key=lambda item: (item[0], item[1]))
    return windows


def _merge_kickoff_windows(windows: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    if not windows:
        return []
    ordered = sorted(windows, key=lambda item: (item[0], item[1]))
    merged: List[Tuple[float, float]] = []
    for start, end in ordered:
        if not merged or start > merged[-1][1] + 0.25:
            merged.append((start, end))
        else:
            prev_start, prev_end = merged[-1]
            merged[-1] = (prev_start, max(prev_end, end))
    return merged


def _filter_kickoff_windows_with_reset_evidence(
    timeline: List[Dict[str, Any]],
    times: List[float],
    windows: List[Tuple[float, float]],
) -> List[Tuple[float, float]]:
    filtered: List[Tuple[float, float]] = []
    for start, end in windows:
        has_reset = False
        for i, fr in enumerate(timeline):
            t = times[i]
            if t < start - 0.25:
                continue
            if t > end + 0.25:
                break
            if _frame_is_kickoff_reset_state(fr):
                has_reset = True
                break
        if has_reset:
            filtered.append((start, end))
    return filtered


def _carry_control_offsets(frame: Dict[str, Any], player: str) -> Tuple[float, float, float]:
    p = _player_frame(frame, player)
    if not p:
        return 99999.0, 99999.0, 99999.0
    b = frame.get("ball", {}) or {}
    return (
        _safe_float(b.get("x", 0.0)) - _safe_float(p.get("x", 0.0)),
        _safe_float(b.get("y", 0.0)) - _safe_float(p.get("y", 0.0)),
        _safe_float(b.get("z", 0.0)) - _safe_float(p.get("z", 0.0)),
    )


def _ball_balanced_on_car(frame: Dict[str, Any], player: str) -> bool:
    rel_x, rel_y, rel_z = _carry_control_offsets(frame, player)
    rel_speed = _rel_speed_player_ball(frame, player)
    return (
        abs(rel_x) <= _FLICK_MAX_BALL_X_OFFSET
        and abs(rel_y) <= _FLICK_MAX_BALL_Y_OFFSET
        and 40.0 <= rel_z <= _FLICK_MAX_BALL_HEIGHT
        and rel_speed <= _FLICK_MAX_REL_SPEED
    )


def _first_touch_in_window(
    timeline: List[Dict[str, Any]],
    times: List[float],
    start_idx: int,
    end_t: float,
    min_conf: float = 0.55,
) -> Tuple[int, str, float]:
    pnames = [str(p.get("name", "")) for p in (timeline[start_idx].get("players", []) or [])]
    best_idx = -1
    best_player = ""
    best_time = 0.0
    best_score = -1.0
    for i in range(start_idx, len(timeline) - 1):
        if times[i] > end_t:
            break
        fr = timeline[i]
        fr2 = timeline[min(i + 1, len(timeline) - 1)]
        frame_best_player = ""
        frame_best_conf = 0.0
        for pn in pnames:
            p = _player_frame(fr, pn)
            if not p:
                continue
            conf = _touch_confidence(fr, fr2, p)
            if conf > frame_best_conf:
                frame_best_conf = conf
                frame_best_player = pn
        if frame_best_player and frame_best_conf >= min_conf:
            ball_speed_delta = abs(_ball_speed(fr2) - _ball_speed(fr))
            candidate_score = frame_best_conf + 0.0001 * ball_speed_delta + (0.08 if _ball_dir_flip(fr, fr2) else 0.0)
            if candidate_score > best_score:
                best_score = candidate_score
                best_idx = i
                best_player = frame_best_player
                best_time = times[i]
    if best_idx >= 0 and best_player:
        return best_idx, best_player, best_time
    return -1, "", 0.0


def _kickoff_touch_search_end(
    timeline: List[Dict[str, Any]],
    times: List[float],
    start_idx: int,
    start_t: float,
    reset_end_t: float,
) -> float:
    base_end = min(times[-1], max(reset_end_t + 0.75, start_t + KICKOFF_WINDOW_TIMEOUT))
    max_end = min(times[-1], start_t + KICKOFF_TOUCH_SEARCH_MAX_S)
    search_end = base_end
    for i in range(start_idx, len(timeline)):
        t = times[i]
        if t > max_end:
            break
        fr = timeline[i]
        search_end = t
        if t <= base_end:
            continue
        if not _ball_in_kickoff_zone(fr) or _ball_speed(fr) >= 900.0:
            return min(times[-1], t + 0.35)
    return max(search_end, base_end)


def _player_frame_is_placeholder(player_frame: Dict[str, Any] | None) -> bool:
    if not player_frame:
        return True
    fields = ("x", "y", "z", "vx", "vy", "vz")
    return all(abs(_safe_float(player_frame.get(field, 0.0))) <= 1e-3 for field in fields)


def _attempted_kickoff_before_touch(
    timeline: List[Dict[str, Any]],
    times: List[float],
    player: str,
    start_idx: int,
    touch_idx: int,
    reset_window: Tuple[float, float] | None = None,
) -> bool:
    start_frame = timeline[start_idx] if timeline else {}
    start_player = _player_frame(start_frame, player)
    if not start_player:
        return False
    start_is_spawn = _is_kickoff_spawn_position(
        _safe_float(start_player.get("x", 0.0)),
        _safe_float(start_player.get("y", 0.0)),
        _safe_float(start_player.get("z", 0.0)),
    )
    start_is_reset_pause = bool(start_frame.get("is_kickoff_pause")) or bool(start_frame.get("is_goal_pause"))
    if reset_window is not None:
        start_is_reset_pause = True
    if not start_is_spawn and not start_is_reset_pause:
        return False
    touch_t = times[max(start_idx, min(touch_idx, len(times) - 1))]
    valid_samples: List[Tuple[float, float, float, float]] = []
    positive_samples = 0
    kickoff_pause_samples = 0
    for i in range(start_idx, max(start_idx + 1, touch_idx + 1)):
        fr = timeline[i]
        t = times[i]
        in_explicit_reset = reset_window is not None and reset_window[0] <= t <= reset_window[1] + 0.75
        if in_explicit_reset or bool(fr.get("is_kickoff_pause")) or not bool(fr.get("active_play", True)):
            kickoff_pause_samples += 1
        player_frame = _player_frame(fr, player)
        if _player_frame_is_placeholder(player_frame):
            continue
        cs = _closing_speed_toward_ball(fr, player)
        align = _approach_alignment_to_ball(fr, player)
        dist = _player_ball_dist(fr, player)
        valid_samples.append((t, align, cs, dist))
        if align >= KICKOFF_DIRECT_ALIGNMENT_MIN and cs >= KICKOFF_ATTEMPT_CLOSING_SPEED:
            positive_samples += 1
    if not valid_samples:
        return False
    recent_cutoff = touch_t - KICKOFF_RECENT_LOOKBACK_S
    recent_samples = [sample for sample in valid_samples if sample[0] >= recent_cutoff]
    if not recent_samples:
        recent_samples = valid_samples[-min(3, len(valid_samples)) :]
    recent_alignments = [sample[1] for sample in recent_samples]
    recent_closings = [sample[2] for sample in recent_samples]
    recent_distances = [sample[3] for sample in recent_samples]
    recent_positive = sum(
        1
        for _, align, cs, _ in recent_samples
        if align >= KICKOFF_DIRECT_ALIGNMENT_MIN and cs >= KICKOFF_ATTEMPT_CLOSING_SPEED
    )
    recent_mean_alignment = mean(recent_alignments) if recent_alignments else 0.0
    recent_max_alignment = max(recent_alignments) if recent_alignments else 0.0
    recent_max_closing = max(recent_closings) if recent_closings else 0.0
    recent_min_distance = min(recent_distances) if recent_distances else 99999.0
    strong_recent_commit = (
        recent_positive >= 1
        and recent_mean_alignment >= KICKOFF_RECENT_MEAN_ALIGNMENT_MIN
        and recent_max_alignment >= KICKOFF_DIRECT_MAX_ALIGNMENT_MIN
        and recent_max_closing >= KICKOFF_DIRECT_MAX_CLOSING_MIN
        and recent_min_distance <= KICKOFF_RECENT_MIN_DISTANCE
    )
    sustained_commit = (
        positive_samples >= KICKOFF_DIRECT_MIN_POSITIVE_SAMPLES
        and recent_positive >= 1
        and recent_mean_alignment >= KICKOFF_DIRECT_ALIGNMENT_MIN
        and recent_max_closing >= KICKOFF_DIRECT_MAX_CLOSING_MIN
        and recent_min_distance <= KICKOFF_RECENT_MIN_DISTANCE
    )
    return (
        kickoff_pause_samples >= 1
        and (strong_recent_commit or sustained_commit)
    )


def _detect_kickoff_events(
    timeline: List[Dict[str, Any]],
    times: List[float],
    player: str,
    player_teams: Dict[str, Any],
    kickoff_reset_windows: List[Tuple[float, float]] | None = None,
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if not timeline:
        return events
    parser_windows = _filter_kickoff_windows_with_reset_evidence(timeline, times, list(kickoff_reset_windows or []))
    candidate_windows = _merge_kickoff_windows(
        _collect_kickoff_reset_windows(timeline, times) + parser_windows
    )
    last_kickoff_end_t = -999.0
    for start_t, reset_end_t in candidate_windows:
        if start_t < last_kickoff_end_t:
            continue
        start_idx = max(0, min(len(times) - 1, bisect_left(times, start_t)))
        end_t = _kickoff_touch_search_end(timeline, times, start_idx, start_t, reset_end_t)
        touch_idx, touch_player, touch_t = _first_touch_in_window(
            timeline,
            times,
            start_idx,
            end_t,
            min_conf=KICKOFF_TOUCH_CONF_MIN,
        )
        if touch_idx < 0:
            continue
        if not _ball_near_kickoff_touch_zone(timeline[touch_idx]):
            continue
        player_attempted = _attempted_kickoff_before_touch(
            timeline,
            times,
            player,
            start_idx,
            touch_idx,
            reset_window=(start_t, reset_end_t),
        )
        if not player_attempted:
            continue
        sustained_pause_window = any(
            bool((timeline[j] or {}).get("is_kickoff_pause"))
            for j in range(start_idx, min(touch_idx + 1, len(timeline)))
        ) or reset_end_t > start_t
        if (touch_t - start_t) > KICKOFF_TOUCH_MAX_S and not sustained_pause_window:
            continue
        team = _team_for_player_name(player, player_teams, 0)
        j_mid = _find_next_idx_by_time(times, touch_idx, 0.65)
        j_out = _find_next_idx_by_time(times, touch_idx, 1.20)
        fr_mid = timeline[j_mid]
        fr_out = timeline[j_out]
        our_mid = _best_team_ball_dist(fr_mid, player_teams, team)
        opp_mid = _best_team_ball_dist(fr_mid, player_teams, 1 - team)
        our_out = _best_team_ball_dist(fr_out, player_teams, team)
        opp_out = _best_team_ball_dist(fr_out, player_teams, 1 - team)
        win_possession = (our_out + 120.0 < opp_out) or (our_mid + 100.0 < opp_mid)
        safe_exit = not _ball_toward_own_goal_fast(timeline[touch_idx], fr_out, team)
        q = 0.35 + 0.4 * (1.0 if win_possession else 0.0) + 0.25 * (1.0 if safe_exit else 0.2)
        q = _clamp01(q)
        reason = "kickoff won with follow-up control" if win_possession else ("kickoff neutral but safe" if safe_exit else "kickoff lost into pressure")
        _add_event(
            events,
            "kickoff",
            touch_t,
            q,
            reason,
            execution_score_0_1=round(_clamp01(0.45 + 0.25 * _clamp01((KICKOFF_TOUCH_MAX_S - (touch_t - start_t)) / KICKOFF_TOUCH_MAX_S) + 0.30 * (1.0 if player_attempted else 0.0)), 3),
            decision_score_0_1=round(_clamp01(0.45 + 0.30 * (1.0 if safe_exit else 0.2) + 0.25 * (1.0 if win_possession else 0.35)), 3),
            outcome_score_0_1=round(q, 3),
            risk_score_0_1=round(_clamp01(0.85 if safe_exit else 0.22), 3),
            issue_tags=(["kickoff_lost"] if not win_possession else []) + (["dangerous_exit"] if not safe_exit else []),
            improvement_tags=(["hit_through_center"] if not win_possession else []) + (["cover_loss_lane"] if not safe_exit else []),
        )
        events[-1]["player"] = player
        events[-1]["kickoff_window_start"] = round(start_t, 3)
        events[-1]["kickoff_window_end"] = round(min(end_t, touch_t), 3)
        _apply_event_context(events[-1], timeline=timeline, times=times, idx=touch_idx, player=player, player_teams=player_teams)
        last_kickoff_end_t = touch_t
    return events


def _detect_ceiling_shot_events(
    timeline: List[Dict[str, Any]],
    times: List[float],
    player: str,
    player_teams: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Detect ceiling shots: player near ceiling, ball contact, shot directed at opponent goal."""
    events: List[Dict[str, Any]] = []
    team = _player_team(player, player_teams or {})
    opp_goal = _opp_goal_y(team)
    _CEILING_Z = 1780.0
    _CEILING_FRAMES = 3
    last_t = -9999.0
    ceiling_frame_count = 0
    for i, fr in enumerate(timeline):
        t = times[i]
        p = _player_frame(fr, player)
        if not p:
            ceiling_frame_count = 0
            continue
        pz = _safe_float(p.get("z", 0.0))
        b = fr.get("ball", {}) or {}
        bz = _safe_float(b.get("z", 0.0))
        by = _safe_float(b.get("y", 0.0))
        d_pb = _player_ball_dist(fr, player)
        if pz >= _CEILING_Z:
            ceiling_frame_count += 1
        else:
            ceiling_frame_count = 0
        if ceiling_frame_count < _CEILING_FRAMES:
            continue
        if d_pb > 500.0 or bz < 1200.0 or (t - last_t) < 2.0:
            continue
        fr_next = timeline[min(i + 1, len(timeline) - 1)]
        contact_made = _touch_confidence(fr, fr_next, p) >= 0.30 or d_pb < 220.0
        if not contact_made:
            continue
        j = _find_next_idx_by_time(times, i, 1.0)
        fr2 = timeline[j]
        b2 = fr2.get("ball", {}) or {}
        by2 = _safe_float(b2.get("y", 0.0))
        toward_goal = abs(by2 - opp_goal) < abs(by - opp_goal) - 80.0
        b_spd_after = _ball_speed(fr2)
        q = _clamp01(
            0.40
            + 0.30 * (1.0 if toward_goal else 0.15)
            + 0.20 * _clamp01(b_spd_after / 1800.0)
            + 0.10 * _clamp01(pz / 2028.0)
        )
        reason = "ceiling shot toward goal" if toward_goal else "ceiling contact without goal threat"
        _add_event(
            events,
            "aerial_offense",
            t,
            q,
            reason,
            event_type="ceiling_shot",
            execution_score_0_1=round(_clamp01(0.45 + 0.25 * _clamp01(pz / 2028.0) + 0.30 * (1.0 if toward_goal else 0.2)), 3),
            decision_score_0_1=round(_clamp01(0.50 + 0.30 * (1.0 if toward_goal else 0.2) + 0.20 * _clamp01(b_spd_after / 1800.0)), 3),
            outcome_score_0_1=round(_clamp01(0.35 + 0.45 * (1.0 if toward_goal else 0.0) + 0.20 * _clamp01(b_spd_after / 1800.0)), 3),
            risk_score_0_1=round(_clamp01(0.55 + 0.35 * (1.0 if toward_goal else 0.0)), 3),
            issue_tags=(["no_goal_threat"] if not toward_goal else []) + (["low_ball_speed"] if b_spd_after < 800.0 else []),
            improvement_tags=(["aim_ceiling_shot_at_goal"] if not toward_goal else []) + (["add_more_power"] if b_spd_after < 800.0 else ["hold_ceiling_longer"]),
        )
        events[-1]["player"] = player
        _attach_mechanic_tags(events[-1], "ceiling_shot")
        _apply_event_context(events[-1], timeline=timeline, times=times, idx=i, player=player, player_teams=player_teams)
        last_t = t
        ceiling_frame_count = 0
    return events


def _detect_double_tap_events(
    timeline: List[Dict[str, Any]],
    times: List[float],
    player: str,
    player_teams: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Detect double taps: ball hits back wall elevated, player tracks and second-touches from air."""
    events: List[Dict[str, Any]] = []
    team = _player_team(player, player_teams or {})
    opp_goal = _opp_goal_y(team)
    _BACKBOARD_Y = 4650.0
    last_t = -9999.0
    i = 0
    while i < len(timeline):
        fr = timeline[i]
        t = times[i]
        b = fr.get("ball", {}) or {}
        by_abs = abs(_safe_float(b.get("y", 0.0)))
        bz = _safe_float(b.get("z", 0.0))
        b_spd = _ball_speed(fr)
        if by_abs < _BACKBOARD_Y or bz < 300.0 or b_spd < 400.0 or (t - last_t) < 2.0:
            i += 1
            continue
        p = _player_frame(fr, player)
        if not p:
            i += 1
            continue
        pz = _safe_float(p.get("z", 0.0))
        d_pb = _player_ball_dist(fr, player)
        if pz < 80.0 or d_pb > 2200.0:
            i += 1
            continue
        # Look for second touch within 0.25–2.0 s
        j_start = _find_next_idx_by_time(times, i, 0.25)
        j_end = _find_next_idx_by_time(times, i, 2.0)
        found = False
        for j in range(j_start, min(j_end + 1, len(timeline) - 1)):
            fr_j = timeline[j]
            p_j = _player_frame(fr_j, player)
            if not p_j:
                continue
            d_pb_j = _player_ball_dist(fr_j, player)
            pz_j = _safe_float(p_j.get("z", 0.0))
            if d_pb_j > 320.0 or pz_j < 80.0:
                continue
            fr_j2 = timeline[min(j + 1, len(timeline) - 1)]
            b_j = fr_j.get("ball", {}) or {}
            b_j2 = fr_j2.get("ball", {}) or {}
            contact = (
                _touch_confidence(fr_j, fr_j2, p_j) >= 0.38
                or _ball_dir_flip(fr_j, fr_j2)
            )
            if not contact:
                continue
            by_j = _safe_float(b_j.get("y", 0.0))
            by_j2 = _safe_float(b_j2.get("y", 0.0))
            toward_goal = abs(by_j2 - opp_goal) < abs(by_j - opp_goal) - 80.0
            b_spd_after = _ball_speed(fr_j2)
            gap_s = times[j] - t
            q = _clamp01(
                0.45
                + 0.30 * (1.0 if toward_goal else 0.15)
                + 0.15 * _clamp01(b_spd_after / 2000.0)
                + 0.10 * _clamp01(1.0 - gap_s / 2.0)
            )
            reason = (
                "double tap rebound directed at goal" if toward_goal
                else "double tap contact without goal threat"
            )
            _add_event(
                events,
                "aerial_offense",
                t,
                q,
                reason,
                event_type="double_tap",
                execution_score_0_1=round(_clamp01(0.50 + 0.30 * (1.0 if toward_goal else 0.2) + 0.20 * _clamp01(1.0 - gap_s / 2.0)), 3),
                decision_score_0_1=round(_clamp01(0.55 + 0.25 * (1.0 if toward_goal else 0.2) + 0.20 * (1.0 if pz > 300.0 else 0.5)), 3),
                outcome_score_0_1=round(_clamp01(0.40 + 0.40 * (1.0 if toward_goal else 0.0) + 0.20 * _clamp01(b_spd_after / 2000.0)), 3),
                risk_score_0_1=round(_clamp01(0.60 + 0.30 * (1.0 if toward_goal else 0.0)), 3),
                issue_tags=(["no_goal_threat"] if not toward_goal else []) + (["slow_rebound_react"] if gap_s > 1.5 else []),
                improvement_tags=(["aim_double_tap_at_goal"] if not toward_goal else []) + (["track_rebound_earlier"] if gap_s > 1.5 else []),
            )
            events[-1]["player"] = player
            _attach_mechanic_tags(events[-1], "double_tap")
            _apply_event_context(events[-1], timeline=timeline, times=times, idx=i, player=player, player_teams=player_teams)
            last_t = t
            found = True
            break
        i += 1
    return events


def _detect_mechanic_events(
    timeline: List[Dict[str, Any]],
    player: str,
    player_teams: Dict[str, Any],
    replay_meta: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    if not timeline or not player:
        return []
    team = _player_team(player, player_teams or {})
    if team not in (0, 1):
        team = 0
    gamemode = infer_gamemode(timeline[0], player_teams or {}, player) if timeline else "2v2"
    own_goal = _own_goal_y(team)
    opp_goal = _opp_goal_y(team)
    events: List[Dict[str, Any]] = []
    times = [_safe_float(fr.get("t", 0.0)) for fr in timeline]

    last_t_by_mech: Dict[str, float] = {m: -9999.0 for m in MECHANICS + SPECIAL_AERIAL_TAGS}
    cooldown = {
        "shadow_defense": 1.2,
        "challenge": 0.9,
        "fifty_fifty_control": 1.0,
        "aerial_offense": 1.8,
        "aerial_defense": 1.8,
        "flicking": 1.3,
        "carrying_dribbling": 1.0,
        # Flag mechanic cooldowns (detection-only, not graded)
        "flip_reset": 2.5,
        "ceiling_shot": 2.0,
        "double_tap": 2.0,
    }

    carry_active = False
    carry_start_idx = 0
    carry_min_opp_dist = 99999.0
    flick_carry_active = False
    flick_carry_start_idx = 0

    # --- Flip reset state machine ---
    # Phase 1: double_jump goes 0→1 while airborne near ball  (counter reset by ball contact)
    # Phase 2: double_jump goes 1→0 while airborne (flip executed after reset)
    _fr_state: str = "idle"   # "idle" | "reset_obtained"
    _fr_t0: float = 0.0
    _fr_idx0: int = 0
    _fr_airborne_s: float = 0.0
    _last_ground_t: float = times[0] if timeline else 0.0

    parser_kickoff_windows = _filter_kickoff_windows_with_reset_evidence(
        timeline,
        times,
        _coerce_kickoff_windows((replay_meta or {}).get("kickoff_pause_windows", [])),
    )
    kickoff_events = _detect_kickoff_events(timeline, times, player, player_teams, parser_kickoff_windows)
    events.extend(kickoff_events)
    for k in kickoff_events:
        last_t_by_mech["kickoff"] = max(last_t_by_mech["kickoff"], _safe_float(k.get("time", -9999.0)))

    # Run specialized detectors (ceiling shots and double taps) before the main loop
    ceiling_shot_events = _detect_ceiling_shot_events(timeline, times, player, player_teams)
    events.extend(ceiling_shot_events)
    for cs in ceiling_shot_events:
        last_t_by_mech["aerial_offense"] = max(last_t_by_mech["aerial_offense"], _safe_float(cs.get("time", -9999.0)))
        last_t_by_mech["ceiling_shot"] = max(last_t_by_mech["ceiling_shot"], _safe_float(cs.get("time", -9999.0)))

    double_tap_events = _detect_double_tap_events(timeline, times, player, player_teams)
    events.extend(double_tap_events)
    for dt in double_tap_events:
        last_t_by_mech["aerial_offense"] = max(last_t_by_mech["aerial_offense"], _safe_float(dt.get("time", -9999.0)))
        last_t_by_mech["double_tap"] = max(last_t_by_mech["double_tap"], _safe_float(dt.get("time", -9999.0)))

    # Build kickoff exclusion windows so that a challenge/50-50 happening
    # during (and just after) a kickoff is not double-counted as a separate
    # mechanic — it's already scored as kickoff.
    _KICKOFF_TAIL_BUFFER_S = 3.0   # was 1.5 — cover post-kickoff recovery (shadow, challenge)
    _KICKOFF_PRE_BUFFER_S = 0.5
    _kickoff_windows: List[Tuple[float, float]] = [
        (max(0.0, start_t - _KICKOFF_PRE_BUFFER_S), end_t + _KICKOFF_TAIL_BUFFER_S)
        for start_t, end_t in _merge_kickoff_windows(
            _collect_kickoff_reset_windows(timeline, times) + parser_kickoff_windows
        )
    ]
    for k in kickoff_events:
        start_t = _safe_float(k.get("kickoff_window_start", k.get("time", 0.0)))
        end_t = _safe_float(k.get("kickoff_window_end", k.get("time", 0.0)))
        if end_t <= 0.0 and start_t <= 0.0:
            continue
        _kickoff_windows.append((max(0.0, start_t - _KICKOFF_PRE_BUFFER_S), end_t + _KICKOFF_TAIL_BUFFER_S))

    def _in_kickoff_window(ts: float) -> bool:
        for ws, we in _kickoff_windows:
            if ws <= ts <= we:
                return True
        return False

    for i, fr in enumerate(timeline):
        t = times[i]
        p = _player_frame(fr, player)
        if not p:
            continue
        kickoff_context = _frame_has_kickoff_context(fr, t, _kickoff_windows)
        ctx_now = frame_context(fr, player, player_teams or {}, team)
        b = fr.get("ball", {}) or {}
        bx = _safe_float(b.get("x", 0.0))
        px = _safe_float(p.get("x", 0.0))
        py = _safe_float(p.get("y", 0.0))
        pz = _safe_float(p.get("z", 0.0))
        if pz < 60.0 and abs(_safe_float(p.get("vz", 0.0))) < 220.0:
            _last_ground_t = t
        by = _safe_float(b.get("y", 0.0))
        bz = _safe_float(b.get("z", 0.0))
        d_pb = _player_ball_dist(fr, player)
        opp_db = _nearest_opponent_dist_ball(fr, player, player_teams, team)
        p_speed = _player_speed(fr, player)
        b_speed = _ball_speed(fr)
        attacking_half = (team == 0 and by > 200.0) or (team == 1 and by < -200.0)
        defending_half = (team == 0 and by < -300.0) or (team == 1 and by > 300.0)
        # True when player is near a wall/backboard surface — used to gate aerial mechanics
        on_wall_surface = abs(px) > 3600.0 or abs(py) > 4700.0

        own_goal_dist_player = abs(py - own_goal)
        own_goal_dist_ball = abs(by - own_goal)
        goal_side = own_goal_dist_player < own_goal_dist_ball
        opp_has_control = opp_db + 120.0 < d_pb
        spacing_band = 500.0 <= d_pb <= 1500.0
        opp_speed = _nearest_opponent_speed(fr, player, player_teams, team)
        speed_match = abs(p_speed - opp_speed) < 650.0
        # Suppress shadow_defense within 2.5 s of an aerial_defense event — after an aerial clear
        # the player is landing/recovering and their positioning looks like shadow but isn't.
        _post_aerial_shadow_suppression_s = 2.5
        if defending_half and opp_has_control and goal_side and spacing_band and speed_match and (t - last_t_by_mech["shadow_defense"]) >= cooldown["shadow_defense"] and (t - last_t_by_mech["aerial_defense"]) >= _post_aerial_shadow_suppression_s:
            j = _find_next_idx_by_time(times, i, 1.0)
            fr2 = timeline[j]
            b2 = fr2.get("ball", {}) or {}
            bx2 = _safe_float(b2.get("x", 0.0))
            wide = abs(bx2) > abs(bx) + 220.0
            deny_shot_lane = not _ball_toward_own_goal_fast(fr, fr2, team)
            support_bonus = 0.10 if bool(ctx_now.get("support_available")) else -0.06
            last_man_penalty = -0.10 if bool(ctx_now.get("last_man")) and not deny_shot_lane else 0.0
            q = _clamp01(0.30 + 0.25 * (1.0 if goal_side else 0.0) + 0.20 * (1.0 if wide else 0.35) + 0.25 * (1.0 if deny_shot_lane else 0.2) + support_bonus + last_man_penalty)
            _add_event(
                events,
                "shadow_defense",
                t,
                q,
                "goal-side shadow spacing and delay quality",
                execution_score_0_1=round(_clamp01(0.45 + 0.25 * (1.0 if goal_side else 0.0) + 0.30 * (1.0 if spacing_band else 0.3)), 3),
                decision_score_0_1=round(_clamp01(0.40 + 0.30 * (1.0 if bool(ctx_now.get("last_man")) else 0.7) + 0.30 * (1.0 if opp_has_control else 0.4)), 3),
                outcome_score_0_1=round(_clamp01(0.35 + 0.35 * (1.0 if deny_shot_lane else 0.0) + 0.30 * (1.0 if wide else 0.2)), 3),
                risk_score_0_1=round(_clamp01(1.0 - _safe_float(ctx_now.get("ball_danger_0_1", 0.0))), 3),
                issue_tags=(["lost_goal_side"] if not goal_side else []) + (["no_backing_cover"] if not bool(ctx_now.get("support_available")) else []),
                improvement_tags=(["stay_goal_side"] if not goal_side else []) + (["force_wide"] if not wide else []) + (["buy_time"] if not deny_shot_lane else []),
            )
            _apply_event_context(events[-1], timeline=timeline, times=times, idx=i, player=player, player_teams=player_teams)
            last_t_by_mech["shadow_defense"] = t

        approach_window = _approach_commitment_window(timeline, times, player, i)
        challenge_candidate = (
            d_pb <= 900.0
            and opp_db <= 900.0
            and bz <= 320.0
            and abs(d_pb - opp_db) <= 280.0
            and bool(approach_window.get("committed"))
        )
        if challenge_candidate and (t - last_t_by_mech["challenge"]) >= cooldown["challenge"] and not _in_kickoff_window(t) and not kickoff_context and not _ball_in_kickoff_zone(fr):
            j_touch = _find_next_idx_by_time(times, i, 0.35)
            j_mid = _find_next_idx_by_time(times, i, 0.60)
            j_out = _find_next_idx_by_time(times, i, 1.20)
            fr_touch = timeline[j_touch]
            fr_mid = timeline[j_mid]
            fr_out = timeline[j_out]
            p_touch = _player_frame(fr_touch, player) or p
            d_touch = _player_ball_dist(fr_touch, player)
            touch_conf = _touch_confidence(fr, fr_touch, p_touch)
            aligned_impact = _ball_dir_flip(fr, fr_touch) and d_touch <= 235.0 and _safe_float(approach_window.get("mean_alignment", 0.0)) >= 0.66
            contact_like = touch_conf >= 0.50 or aligned_impact
            if not contact_like:
                continue
            our_mid = _best_team_ball_dist(fr_mid, player_teams, team)
            opp_mid = _best_team_ball_dist(fr_mid, player_teams, 1 - team)
            our_out = _best_team_ball_dist(fr_out, player_teams, team)
            opp_out = _best_team_ball_dist(fr_out, player_teams, 1 - team)
            opp_had_control = opp_db + 80.0 < d_pb
            win_possession = (our_out + 120.0 < opp_out) or (our_mid + 120.0 < opp_mid)
            force_bad_touch = opp_had_control and ((opp_mid - opp_db) > 140.0 or (our_mid + 120.0 < opp_mid))
            easy_counter = _ball_toward_own_goal_fast(fr, fr_out, team) and (opp_out + 180.0 < our_out)
            double_commit = _teammate_double_commit(fr, player, player_teams, team, d_pb)
            close_gain = _clamp01((d_pb - d_touch) / max(1.0, d_pb))
            success = (win_possession or force_bad_touch) and (not easy_counter)
            teammate_cover = bool(ctx_now.get("support_available"))
            gamemode_mult = 0.75 if gamemode == "1v1" else (0.95 if gamemode == "2v2" else 1.0)
            q = 0.32 + 0.40 * (1.0 if success else 0.0) + 0.12 * (1.0 if win_possession else 0.0) + 0.10 * (1.0 if force_bad_touch else 0.0)
            q += 0.10 * close_gain
            if easy_counter:
                q -= 0.40 * gamemode_mult
            if double_commit:
                q -= 0.15
            if teammate_cover and gamemode != "1v1" and easy_counter:
                q += 0.10
            if bool(ctx_now.get("last_man")) and easy_counter:
                q -= 0.10
            if (opp_out + 150.0 < our_out) and (d_touch > d_pb):
                q -= 0.10
            q = _clamp01(q)
            if easy_counter:
                reason = "challenge conceded easy counter"
            elif win_possession:
                reason = "won possession after challenge"
            elif force_bad_touch:
                reason = "forced weak opponent touch"
            else:
                reason = "challenge failed to improve outcome"
            _add_event(
                events,
                "challenge",
                t,
                q,
                reason,
                execution_score_0_1=round(_clamp01(0.30 + 0.25 * close_gain + 0.20 * (1.0 if contact_like else 0.0) + 0.25 * _safe_float(approach_window.get("mean_alignment", 0.0))), 3),
                decision_score_0_1=round(_clamp01(0.35 + 0.35 * (1.0 if opp_had_control else 0.35) + 0.30 * (0.25 if bool(ctx_now.get("last_man")) and not teammate_cover else 1.0)), 3),
                outcome_score_0_1=round(_clamp01(0.30 + 0.40 * (1.0 if win_possession else 0.0) + 0.30 * (1.0 if force_bad_touch else 0.2)), 3),
                risk_score_0_1=round(_clamp01((1.0 - _safe_float(ctx_now.get("ball_danger_0_1", 0.0))) * (0.8 if bool(ctx_now.get("last_man")) else 1.0)), 3),
                issue_tags=(["easy_counter"] if easy_counter else []) + (["double_commit"] if double_commit else []) + (["last_man_risk"] if bool(ctx_now.get("last_man")) and not teammate_cover else []) + (["weak_commitment"] if _safe_float(approach_window.get("mean_alignment", 0.0)) < 0.68 else []),
                improvement_tags=(["stay_goal_side"] if easy_counter else []) + (["force_weak_touch"] if not force_bad_touch else []) + (["use_teammate_cover"] if teammate_cover else ["delay_challenge"]) + (["square_up_earlier"] if _safe_float(approach_window.get("mean_alignment", 0.0)) < 0.68 else []),
                commitment_score_0_1=round(_clamp01(0.45 * _safe_float(approach_window.get("mean_alignment", 0.0)) + 0.35 * _clamp01(_safe_float(approach_window.get("mean_closing", 0.0)) / 1200.0) + 0.20 * _clamp01(_safe_float(approach_window.get("distance_gain", 0.0)) / 450.0)), 3),
            )
            _apply_event_context(events[-1], timeline=timeline, times=times, idx=i, player=player, player_teams=player_teams)
            last_t_by_mech["challenge"] = t

        opp_ready, opp_name, opp_ball_dist = _opponent_contest_ready(fr, player, player_teams, team)
        if d_pb < 300.0 and opp_db < 300.0 and bz < 260.0 and (t - last_t_by_mech["fifty_fifty_control"]) >= cooldown["fifty_fifty_control"] and not _in_kickoff_window(t) and not kickoff_context and not _ball_in_kickoff_zone(fr) and opp_ready:
            j = _find_next_idx_by_time(times, i, 0.20)
            k = _find_next_idx_by_time(times, i, 0.80)
            frj = timeline[j]
            frk = timeline[k]
            impact = _ball_dir_flip(fr, frj) or abs(_ball_speed(frj) - b_speed) > 250.0
            pre_impact_gap = abs(_time_to_intercept_estimate(fr, player) - _time_to_intercept_estimate(fr, opp_name)) if opp_name else 999.0
            if impact and pre_impact_gap <= _FIFTY_MAX_PRE_IMPACT_GAP:
                our_k = _best_team_ball_dist(frk, player_teams, team)
                opp_k = _best_team_ball_dist(frk, player_teams, 1 - team)
                b_k = frk.get("ball", {}) or {}
                by_k = _safe_float(b_k.get("y", 0.0))
                own_d = abs(by_k - own_goal)
                opp_d = abs(by_k - opp_goal)
                teammate_cover = bool(ctx_now.get("support_available"))
                if our_k + 100.0 < opp_k and (opp_d < own_d or own_d > 2600.0):
                    q = 0.76
                    reason = "50/50 won to team control"
                elif opp_k + 100.0 < our_k and own_d < 2500.0 and (gamemode == "1v1" or not teammate_cover):
                    q = 0.24
                    reason = "50/50 lost into danger"
                else:
                    q = 0.50
                    reason = "50/50 neutral outcome"
                _add_event(
                    events,
                    "fifty_fifty_control",
                    t,
                    q,
                    reason,
                    execution_score_0_1=round(_clamp01(0.40 + 0.25 * (1.0 if impact else 0.0) + 0.35 * _clamp01((300.0 - abs(d_pb - opp_db)) / 300.0)), 3),
                    decision_score_0_1=round(_clamp01(0.40 + 0.30 * (0.25 if bool(ctx_now.get("last_man")) and not teammate_cover else 1.0) + 0.30 * (1.0 if ctx_now.get("pressure_level") == "high" else 0.6)), 3),
                    outcome_score_0_1=round(q, 3),
                    risk_score_0_1=round(_clamp01((1.0 - _safe_float(ctx_now.get("ball_danger_0_1", 0.0))) + (0.12 if teammate_cover else -0.10)), 3),
                    issue_tags=(["lost_into_danger"] if q < 0.35 else []) + (["unsupported_contest"] if not teammate_cover and gamemode != "1v1" else []) + (["late_to_contest"] if pre_impact_gap > 0.10 else []),
                    improvement_tags=(["angle_50_to_teammate"] if q < 0.55 else []) + (["avoid_dead_neutral"] if q == 0.50 else []) + (["match_arrival_time"] if pre_impact_gap > 0.10 else []),
                    commitment_score_0_1=round(_clamp01(0.40 * _safe_float(approach_window.get("mean_alignment", 0.0)) + 0.25 * _clamp01(_safe_float(approach_window.get("mean_closing", 0.0)) / 1200.0) + 0.20 * _clamp01((420.0 - opp_ball_dist) / 420.0) + 0.15 * _clamp01((0.20 - min(pre_impact_gap, 0.20)) / 0.20)), 3),
                )
                _apply_event_context(events[-1], timeline=timeline, times=times, idx=i, player=player, player_teams=player_teams)
                last_t_by_mech["fifty_fifty_control"] = t

        if attacking_half and pz > 150.0 and bz > 300.0 and d_pb < 950.0 and not on_wall_surface and (t - last_t_by_mech["aerial_offense"]) >= cooldown["aerial_offense"]:
            j = _find_next_idx_by_time(times, i, 0.90)
            fr2 = timeline[j]
            b2 = fr2.get("ball", {}) or {}
            by2 = _safe_float(b2.get("y", 0.0))
            toward_opp_goal = abs(by2 - opp_goal) < abs(by - opp_goal)
            our_out = _best_team_ball_dist(fr2, player_teams, team)
            opp_out = _best_team_ball_dist(fr2, player_teams, 1 - team)
            retain = our_out <= opp_out + 60.0
            q = _clamp01(0.35 + 0.30 * (1.0 if toward_opp_goal else 0.25) + 0.25 * (1.0 if retain else 0.3) + 0.10 * _clamp01(p_speed / 2100.0))
            reason = "air touch created attacking value" if q >= 0.5 else "aerial touch gave up pressure"
            # Shift event time to the frame of closest approach (actual contact), up to 0.6 s ahead
            j_contact = i
            min_dpb = d_pb
            for _ci in range(i, min(j, len(timeline))):
                _dpb_ci = _player_ball_dist(timeline[_ci], player)
                if _dpb_ci < min_dpb:
                    min_dpb = _dpb_ci
                    j_contact = _ci
            t_contact = times[j_contact]
            _add_event(
                events,
                "aerial_offense",
                t_contact,
                q,
                reason,
                execution_score_0_1=round(_clamp01(0.45 + 0.20 * _clamp01(p_speed / 2100.0) + 0.35 * (1.0 if toward_opp_goal else 0.25)), 3),
                decision_score_0_1=round(_clamp01(0.45 + 0.25 * (1.0 if attacking_half else 0.3) + 0.30 * (0.4 if bool(ctx_now.get("last_man")) else 1.0)), 3),
                outcome_score_0_1=round(_clamp01(0.40 + 0.30 * (1.0 if toward_opp_goal else 0.0) + 0.30 * (1.0 if retain else 0.2)), 3),
                risk_score_0_1=round(_clamp01(1.0 - _safe_float(ctx_now.get("ball_danger_0_1", 0.0))), 3),
                issue_tags=(["gave_up_pressure"] if q < 0.5 else []) + (["last_man_commit"] if bool(ctx_now.get("last_man")) else []),
                improvement_tags=(["hit_toward_target"] if not toward_opp_goal else []) + (["maintain_follow_up"] if not retain else []),
            )
            _apply_event_context(events[-1], timeline=timeline, times=times, idx=j_contact, player=player, player_teams=player_teams)
            last_t_by_mech["aerial_offense"] = t_contact

        threat_zone = abs(by - own_goal) < 2600.0
        # Exclude wall/backboard players — wall pinches and backboard waits are not aerial defense
        if defending_half and threat_zone and pz > 150.0 and bz > 260.0 and d_pb < 1200.0 and not on_wall_surface and (t - last_t_by_mech["aerial_defense"]) >= cooldown["aerial_defense"]:
            j = _find_next_idx_by_time(times, i, 1.00)
            fr2 = timeline[j]
            b2 = fr2.get("ball", {}) or {}
            by2 = _safe_float(b2.get("y", 0.0))
            bx2 = _safe_float(b2.get("x", 0.0))
            away = abs(by2 - own_goal) > abs(by - own_goal)
            center_clear = abs(bx2) > abs(bx) + 180.0
            double_commit = _teammate_double_commit(fr, player, player_teams, team, d_pb)
            # If the touch sent the ball into the opponent half AND we kept possession,
            # this is the start of an offensive transition, not a defensive clear.
            # Suppress aerial_defense in that case and let aerial_offense pick it up.
            into_opp_half = (team == 0 and by2 > 200.0) or (team == 1 and by2 < -200.0)
            adf_our_out = _best_team_ball_dist(fr2, player_teams, team)
            adf_opp_out = _best_team_ball_dist(fr2, player_teams, 1 - team)
            adf_retain = adf_our_out <= adf_opp_out + 60.0
            adf_offensive_transition = away and adf_retain and into_opp_half
            q = 0.35 + 0.35 * (1.0 if away else 0.2) + 0.20 * (1.0 if center_clear else 0.35) + 0.10 * (0.2 if double_commit else 1.0)
            # Shift event time to the frame of actual ball contact (min d_pb within next 0.7 s)
            j_contact = i
            min_dpb_adf = d_pb
            for _ci in range(i, min(j, len(timeline))):
                _dpb_ci = _player_ball_dist(timeline[_ci], player)
                if _dpb_ci < min_dpb_adf:
                    min_dpb_adf = _dpb_ci
                    j_contact = _ci
            t_contact_adf = times[j_contact]
            if not adf_offensive_transition:
                _add_event(
                    events,
                    "aerial_defense",
                    t_contact_adf,
                    _clamp01(q),
                    "aerial defensive clear quality",
                    execution_score_0_1=round(_clamp01(0.45 + 0.25 * (1.0 if away else 0.2) + 0.30 * (1.0 if center_clear else 0.35)), 3),
                    decision_score_0_1=round(_clamp01(0.45 + 0.30 * (1.0 if threat_zone else 0.3) + 0.25 * (1.0 if not double_commit else 0.2)), 3),
                    outcome_score_0_1=round(_clamp01(0.35 + 0.35 * (1.0 if away else 0.0) + 0.30 * (1.0 if center_clear else 0.2)), 3),
                    risk_score_0_1=round(_clamp01(1.0 - _safe_float(ctx_now.get("ball_danger_0_1", 0.0))), 3),
                    issue_tags=(["double_commit"] if double_commit else []) + (["failed_clear_distance"] if not away else []),
                    improvement_tags=(["clear_wide"] if not center_clear else []) + (["beat_ball_earlier"] if not away else []),
                )
                _apply_event_context(events[-1], timeline=timeline, times=times, idx=j_contact, player=player, player_teams=player_teams)
                last_t_by_mech["aerial_defense"] = t_contact_adf

        rel_v = _rel_speed_player_ball(fr, player)
        jump = int(_safe_float(p.get("jump", 0.0)))
        djump = int(_safe_float(p.get("double_jump", 0.0)))
        carry_like = d_pb <= 200.0 and bz < 250.0 and rel_v < 700.0
        ball_balanced = _ball_balanced_on_car(fr, player)
        had_flick_carry = flick_carry_active
        flick_carry_origin_idx = flick_carry_start_idx
        if ball_balanced:
            if not flick_carry_active:
                flick_carry_active = True
                flick_carry_start_idx = i
        else:
            flick_carry_active = False
            flick_carry_start_idx = 0

        prev_p_flick = _player_frame(timeline[max(0, i - 1)], player) if i > 0 else None
        prev_djump_flick = int(_safe_float(prev_p_flick.get("double_jump", 0.0))) if prev_p_flick else 0
        dodge_release = prev_djump_flick == 1 and djump == 0
        # Real flicks launch from a ground carry. Reject false positives where the ball
        # briefly settles near the car after an aerial or 50/50 and the player happens
        # to release a double-jump from the descent.
        grounded_recent = True
        if dodge_release and had_flick_carry:
            lookback_start_t = max(0.0, t - _FLICK_GROUNDED_LOOKBACK_S)
            for _k in range(i, -1, -1):
                if times[_k] < lookback_start_t:
                    break
                _pk = _player_frame(timeline[_k], player)
                if _pk and _safe_float(_pk.get("z", 0.0)) > _FLICK_GROUNDED_PZ_MAX:
                    grounded_recent = False
                    break
        if had_flick_carry and dodge_release and grounded_recent and (t - last_t_by_mech["flicking"]) >= cooldown["flicking"]:
            carry_duration = max(0.0, t - times[flick_carry_origin_idx])
            if carry_duration < _FLICK_MIN_CARRY_S:
                pass
            else:
                j = _find_next_idx_by_time(times, i, _FLICK_MAX_RELEASE_S)
                fr2 = timeline[j]
                b2 = fr2.get("ball", {}) or {}
                bz2 = _safe_float(b2.get("z", 0.0))
                up_gain = max((bz2 - bz), (_safe_float(b2.get("vz", 0.0)) - _safe_float(b.get("vz", 0.0))))
                fwd0 = _ball_forward_speed_to_opp(fr, team)
                fwd1 = _ball_forward_speed_to_opp(fr2, team)
                forward_gain = fwd1 - fwd0
                up_spike = up_gain >= _FLICK_MIN_POST_UP_GAIN
                forward_spike = forward_gain >= _FLICK_MIN_POST_FORWARD_GAIN
                power = _ball_speed(fr2) > b_speed + 300.0
                if up_spike or forward_spike:
                    q = _clamp01(
                        0.30
                        + 0.20 * _clamp01(carry_duration / 0.45)
                        + 0.20 * (1.0 if power else 0.35)
                        + 0.15 * _clamp01(max(0.0, forward_gain) / 900.0)
                        + 0.15 * _clamp01(max(0.0, up_gain) / 240.0)
                    )
                    reason = "flick generated threatening ball launch" if q >= 0.5 else "flick lacked threat or power"
                    _add_event(
                        events,
                        "flicking",
                        t,
                        q,
                        reason,
                        execution_score_0_1=round(_clamp01(0.35 + 0.20 * _clamp01(carry_duration / 0.45) + 0.20 * (1.0 if dodge_release else 0.0) + 0.25 * (1.0 if up_spike else 0.0)), 3),
                        decision_score_0_1=round(_clamp01(0.40 + 0.30 * (1.0 if attacking_half else 0.4) + 0.30 * (1.0 if ctx_now.get("pressure_level") != "low" else 0.5)), 3),
                        outcome_score_0_1=round(_clamp01(0.30 + 0.30 * (1.0 if power else 0.0) + 0.20 * (1.0 if up_spike else 0.0) + 0.20 * (1.0 if forward_spike else 0.0)), 3),
                        risk_score_0_1=round(_clamp01((1.0 - _safe_float(ctx_now.get("ball_danger_0_1", 0.0))) + (0.10 if bool(ctx_now.get("support_available")) else 0.0)), 3),
                        issue_tags=(["low_power"] if not power else []) + (["no_threat_created"] if q < 0.5 else []),
                        improvement_tags=(["balance_carry_first"] if carry_duration < 0.30 else []) + (["pop_ball_higher"] if not up_spike else []) + (["accelerate_flick_contact"] if not forward_spike else []),
                        controlled_carry_s=round(carry_duration, 3),
                    )
                    _apply_event_context(events[-1], timeline=timeline, times=times, idx=i, player=player, player_teams=player_teams)
                    last_t_by_mech["flicking"] = t
            flick_carry_active = False
            flick_carry_start_idx = 0

        in_carry_state = d_pb <= 200.0 and bz < 250.0 and rel_v < 700.0
        if in_carry_state:
            if not carry_active:
                carry_active = True
                carry_start_idx = i
                carry_min_opp_dist = opp_db
            else:
                carry_min_opp_dist = min(carry_min_opp_dist, opp_db)
        else:
            if carry_active:
                t0 = times[carry_start_idx]
                duration = max(0.0, t - t0)
                if duration >= 1.0 and (t - last_t_by_mech["carrying_dribbling"]) >= cooldown["carrying_dribbling"]:
                    end_idx = i
                    j = _find_next_idx_by_time(times, end_idx, 0.80)
                    fr_end = timeline[end_idx]
                    fr2 = timeline[j]
                    our_end = _best_team_ball_dist(fr_end, player_teams, team)
                    opp_end = _best_team_ball_dist(fr_end, player_teams, 1 - team)
                    our_after = _best_team_ball_dist(fr2, player_teams, team)
                    opp_after = _best_team_ball_dist(fr2, player_teams, 1 - team)
                    pressure_hold = carry_min_opp_dist < 900.0 and our_after <= opp_after + 80.0
                    immediate_loss = opp_after + 120.0 < our_after
                    b_end = fr_end.get("ball", {}) or {}
                    b_after = fr2.get("ball", {}) or {}
                    created_play = abs(_safe_float(b_after.get("y", 0.0)) - opp_goal) < abs(_safe_float(b_end.get("y", 0.0)) - opp_goal)
                    q = 0.35 + 0.25 * _clamp01(duration / 2.4) + 0.20 * (1.0 if pressure_hold else 0.35) + 0.20 * (1.0 if created_play else 0.30)
                    if immediate_loss:
                        q -= 0.30
                    q = _clamp01(q)
                    reason = "carry kept control and progressed play" if q >= 0.5 else "carry lost value before creating threat"
                    _add_event(
                        events,
                        "carrying_dribbling",
                        t0,
                        q,
                        reason,
                        execution_score_0_1=round(_clamp01(0.35 + 0.30 * _clamp01(duration / 2.4) + 0.35 * (1.0 if not immediate_loss else 0.2)), 3),
                        decision_score_0_1=round(_clamp01(0.40 + 0.30 * (1.0 if attacking_half else 0.4) + 0.30 * (1.0 if ctx_now.get("pressure_level") != "low" else 0.6)), 3),
                        outcome_score_0_1=round(_clamp01(0.35 + 0.30 * (1.0 if pressure_hold else 0.0) + 0.35 * (1.0 if created_play else 0.0)), 3),
                        risk_score_0_1=round(_clamp01(1.0 - _safe_float(ctx_now.get("ball_danger_0_1", 0.0))), 3),
                        issue_tags=(["immediate_loss"] if immediate_loss else []) + (["carry_under_low_pressure"] if ctx_now.get("pressure_level") == "low" else []),
                        improvement_tags=(["protect_ball_longer"] if not pressure_hold else []) + (["turn_control_into_threat"] if not created_play else []),
                    )
                    _apply_event_context(events[-1], timeline=timeline, times=times, idx=carry_start_idx, player=player, player_teams=player_teams)
                    last_t_by_mech["carrying_dribbling"] = t
                carry_active = False
                carry_start_idx = 0
                carry_min_opp_dist = 99999.0

        # --- Flip reset detection (state machine) ---
        # Look back one frame for the previous double_jump value (avoids state across continues)
        prev_p = _player_frame(timeline[max(0, i - 1)], player) if i > 0 else None
        prev_djump = int(_safe_float(prev_p.get("double_jump", 1.0))) if prev_p else 1
        djump = int(_safe_float(p.get("double_jump", 0.0)))
        airborne_for = max(0.0, t - _last_ground_t)
        xy_gap = ((px - bx) ** 2 + (py - by) ** 2) ** 0.5
        z_gap = pz - bz

        # Phase 1: flip counter reset detected (djump 0→1 while airborne near ball)
        if (
            prev_djump == 0 and djump == 1
            and pz >= _FLIP_RESET_MIN_PLAYER_Z
            and bz >= _FLIP_RESET_MIN_BALL_Z
            and d_pb <= _FLIP_RESET_MAX_DIST
            and xy_gap <= _FLIP_RESET_MAX_XY_GAP
            and -40.0 <= z_gap <= _FLIP_RESET_MAX_Z_GAP
            and pz <= _FLIP_RESET_MAX_PLAYER_Z
            and airborne_for >= _FLIP_RESET_MIN_AIRBORNE_S
            and not on_wall_surface
            and _fr_state == "idle"
        ):
            _fr_state = "reset_obtained"
            _fr_t0 = t
            _fr_idx0 = i
            _fr_airborne_s = airborne_for

        # Phase 1 timeout
        if _fr_state == "reset_obtained" and ((t - _fr_t0) > _FLIP_RESET_MAX_USE_DELAY_S or pz < 90.0):
            _fr_state = "idle"
            _fr_airborne_s = 0.0

        # Phase 2: flip executed after reset (djump 1→0 while airborne within window)
        if (
            _fr_state == "reset_obtained"
            and prev_djump == 1 and djump == 0
            and pz >= _FLIP_RESET_MIN_PLAYER_Z
            and (t - _fr_t0) >= _FLIP_RESET_MIN_USE_DELAY_S
            and (t - _fr_t0) <= _FLIP_RESET_MAX_USE_DELAY_S
            and not _in_kickoff_window(t)
            and (t - last_t_by_mech.get("flip_reset", -9999.0)) >= cooldown.get("flip_reset", 2.5)
        ):
            j_fr = _find_next_idx_by_time(times, i, 0.8)
            fr2_fr = timeline[j_fr]
            b2_fr = fr2_fr.get("ball", {}) or {}
            by2_fr = _safe_float(b2_fr.get("y", 0.0))
            bspd2_fr = _ball_speed(fr2_fr)
            toward_opp_fr = abs(by2_fr - opp_goal) < abs(by - opp_goal) - 80.0
            attacking_use = attacking_half or abs(by - opp_goal) < 2600.0
            threatening_use = toward_opp_fr and bspd2_fr >= _FLIP_RESET_MIN_POST_SPEED and attacking_use
            if not threatening_use:
                _fr_state = "idle"
                _fr_airborne_s = 0.0
                continue
            q_fr = _clamp01(
                0.50
                + 0.30 * (1.0 if toward_opp_fr else 0.10)
                + 0.20 * _clamp01(bspd2_fr / 2000.0)
            )
            reason_fr = "flip reset executed and directed toward goal"
            _add_event(
                events,
                "aerial_offense",
                _fr_t0,
                q_fr,
                reason_fr,
                event_type="flip_reset",
                execution_score_0_1=round(_clamp01(0.55 + 0.25 * (1.0 if toward_opp_fr else 0.2) + 0.20 * _clamp01(bspd2_fr / 2000.0)), 3),
                decision_score_0_1=round(_clamp01(0.55 + 0.25 * (1.0 if attacking_half else 0.4) + 0.20 * (0.5 if bool(ctx_now.get("last_man")) else 1.0)), 3),
                outcome_score_0_1=round(_clamp01(0.40 + 0.40 * (1.0 if toward_opp_fr else 0.0) + 0.20 * _clamp01(bspd2_fr / 2000.0)), 3),
                risk_score_0_1=round(_clamp01(0.60 + 0.30 * (1.0 if toward_opp_fr else 0.0)), 3),
                issue_tags=(["last_man_commit"] if bool(ctx_now.get("last_man")) else []),
                improvement_tags=(["add_more_power"] if bspd2_fr < 1300.0 else []),
                regained_flip_while_airborne_s=round(_fr_airborne_s, 3),
            )
            events[-1]["player"] = player
            _attach_mechanic_tags(events[-1], "flip_reset")
            _apply_event_context(events[-1], timeline=timeline, times=times, idx=_fr_idx0, player=player, player_teams=player_teams)
            last_t_by_mech["aerial_offense"] = max(last_t_by_mech["aerial_offense"], _fr_t0)
            last_t_by_mech["flip_reset"] = t
            _fr_state = "idle"
            _fr_airborne_s = 0.0

        # Expanded event coverage: missed open nets.
        open_net = attacking_half and d_pb < 1200.0 and abs(bx) < 950.0 and abs(by - opp_goal) < 2100.0 and bz < 260.0
        if open_net and (t - last_t_by_mech.get("open_net", -9999.0)) >= 1.2:
            j = _find_next_idx_by_time(times, i, 1.0)
            fr2 = timeline[j]
            b2 = fr2.get("ball", {}) or {}
            goal_progress = abs(_safe_float(b2.get("y", 0.0)) - opp_goal) < abs(by - opp_goal) - 260.0
            shot_like = _touch_confidence(fr, fr2, p) >= 0.40
            q = _clamp01(0.30 + 0.40 * (1.0 if goal_progress else 0.0) + 0.30 * (1.0 if shot_like else 0.1))
            reason = "open net chance converted into pressure" if q >= 0.55 else "missed open net opportunity"
            _add_event(
                events,
                "aerial_offense" if bz > 250.0 else "flicking",
                t,
                q,
                reason,
                event_type="open_net_chance",
                execution_score_0_1=round(_clamp01(0.40 + 0.30 * (1.0 if shot_like else 0.0) + 0.30 * (1.0 if goal_progress else 0.0)), 3),
                decision_score_0_1=round(_clamp01(0.65), 3),
                outcome_score_0_1=round(q, 3),
                risk_score_0_1=round(_clamp01(1.0 - _safe_float(ctx_now.get("ball_danger_0_1", 0.0))), 3),
                issue_tags=(["missed_open_net"] if q < 0.55 else []),
                improvement_tags=(["shoot_earlier"] if q < 0.55 else []),
            )
            _apply_event_context(events[-1], timeline=timeline, times=times, idx=i, player=player, player_teams=player_teams)
            last_t_by_mech["open_net"] = t

        # Expanded event coverage: overcommit / failed rotate out.
        overcommit = attacking_half and bool(ctx_now.get("last_man")) and _safe_float(ctx_now.get("ball_danger_0_1", 0.0)) > 0.58 and opp_has_control and d_pb > 900.0
        if overcommit and (t - last_t_by_mech.get("overcommit", -9999.0)) >= 1.4:
            q = 0.18 if gamemode == "1v1" else (0.24 if not bool(ctx_now.get("support_available")) else 0.36)
            _add_event(
                events,
                "shadow_defense",
                t,
                q,
                "overcommit left defensive coverage exposed",
                event_type="overcommit",
                execution_score_0_1=0.35,
                decision_score_0_1=0.12 if gamemode == "1v1" else 0.22,
                outcome_score_0_1=round(_clamp01(1.0 - _safe_float(ctx_now.get("ball_danger_0_1", 0.0))), 3),
                risk_score_0_1=0.05,
                issue_tags=["overcommit", "coverage_lost"],
                improvement_tags=["rotate_out_earlier", "respect_last_man_role"],
            )
            _apply_event_context(events[-1], timeline=timeline, times=times, idx=i, player=player, player_teams=player_teams)
            last_t_by_mech["overcommit"] = t

    events = _suppress_redundant_followup_events(events)
    return events


def _suppress_redundant_followup_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not events:
        return []
    ordered = sorted(events, key=lambda ev: (_safe_float(ev.get("time", 0.0)), str(ev.get("mechanic_id", ""))))
    kickoff_windows: List[tuple[float, float]] = []
    for ev in ordered:
        if _canonical_mid(str(ev.get("mechanic_id", ""))) != "kickoff":
            continue
        start_t = _safe_float(ev.get("kickoff_window_start", ev.get("time", 0.0)))
        end_t = _safe_float(ev.get("kickoff_window_end", ev.get("time", 0.0)))
        kickoff_windows.append((start_t, end_t + 1.0))

    filtered: List[Dict[str, Any]] = []
    for ev in ordered:
        mid = _canonical_mid(str(ev.get("mechanic_id", "")))
        t = _safe_float(ev.get("time", 0.0))
        if mid in {"challenge", "fifty_fifty_control"} and any(start <= t <= end for start, end in kickoff_windows):
            continue

        if filtered:
            prev = filtered[-1]
            prev_mid = _canonical_mid(str(prev.get("mechanic_id", "")))
            prev_t = _safe_float(prev.get("time", 0.0))
            close_in_time = abs(t - prev_t) <= 0.35

            if close_in_time and {mid, prev_mid} == {"challenge", "fifty_fifty_control"}:
                if mid == "fifty_fifty_control":
                    filtered[-1] = ev
                continue
            if close_in_time and mid == prev_mid:
                prev_score = _safe_float(prev.get("quality_score", prev.get("score", 0.0)))
                next_score = _safe_float(ev.get("quality_score", ev.get("score", 0.0)))
                if next_score < prev_score:
                    _merge_event_payload(prev, ev)
                else:
                    filtered[-1] = _merge_event_payload(ev, prev)
                continue
        filtered.append(ev)
    return filtered


def _grade_one(mechanic: str, evs: List[Dict[str, Any]]) -> Dict[str, Any]:
    qs = [_safe_float(e.get("quality_score", 0.5), 0.5) for e in evs]
    n = len(qs)
    if n == 0:
        return {
            "mechanic_id": mechanic,
            "title": MECH_TITLE.get(mechanic, mechanic),
            "score_0_100": 50.0,
            "confidence_0_1": 0.2,
            "event_count": 0,
            "good_count": 0,
            "neutral_count": 0,
            "bad_count": 0,
            "subscores": {
                "mean_quality": 0.5,
                "stability": 0.0,
                "execution": 0.5,
                "decision": 0.5,
                "outcome": 0.5,
                "risk_management": 0.5,
                "event_confidence": 0.2,
            },
            "evidence_events": [],
            "recommendation_hint": "insufficient_sample",
            "issue_tags": [],
            "improvement_tags": [],
            "confidence_reasons": ["small_sample"],
        }
    m = _clamp01(mean(qs))
    sigma = pstdev(qs) if n >= 2 else 0.0
    stability = _clamp01(1.0 - sigma / 0.35)
    exec_mean = _clamp01(mean([_safe_float(e.get("execution_score_0_1", m), m) for e in evs]))
    decision_mean = _clamp01(mean([_safe_float(e.get("decision_score_0_1", m), m) for e in evs]))
    outcome_mean = _clamp01(mean([_safe_float(e.get("outcome_score_0_1", m), m) for e in evs]))
    risk_mean = _clamp01(mean([_safe_float(e.get("risk_score_0_1", 0.5), 0.5) for e in evs]))
    event_conf_mean = _clamp01(mean([_safe_float(e.get("event_confidence_0_1", 0.65), 0.65) for e in evs]))
    score = _clamp(100.0 * (0.15 + 0.85 * m), 0.0, 100.0)
    conf_n = 1.0 - exp(-float(n) / 6.0)
    conf = _clamp(0.2 + 0.78 * conf_n * (0.55 + 0.20 * stability + 0.25 * event_conf_mean), 0.2, 0.98)
    good = sum(1 for q in qs if q >= 0.66)
    bad = sum(1 for q in qs if q < 0.42)
    neutral = max(0, n - good - bad)
    ev = sorted(evs, key=lambda x: _safe_float(x.get("quality_score", 0.5), 0.5))
    evidence = [
        {"time": round(_safe_float(e.get("time", 0.0)), 3), "quality": round(_safe_float(e.get("quality_score", 0.0)), 3), "reason": str(e.get("reason", ""))}
        for e in (ev[:2] + (ev[-1:] if len(ev) > 2 else []))
    ]
    hint = "good_progress" if score >= 75 else ("priority_improvement" if score < 60 else "keep_training")
    issue_tags = sorted({str(tag) for e in evs for tag in (e.get("issue_tags", []) or []) if str(tag).strip()})
    improvement_tags = sorted({str(tag) for e in evs for tag in (e.get("improvement_tags", []) or []) if str(tag).strip()})
    confidence_reasons: List[str] = []
    if n < 3:
        confidence_reasons.append("small_sample")
    if stability < 0.45:
        confidence_reasons.append("high_variance")
    if event_conf_mean < 0.6:
        confidence_reasons.append("weak_context_signal")
    if not confidence_reasons:
        confidence_reasons.append("stable_pattern")
    return {
        "mechanic_id": mechanic,
        "title": MECH_TITLE.get(mechanic, mechanic),
        "score_0_100": round(score, 2),
        "confidence_0_1": round(conf, 3),
        "event_count": n,
        "good_count": good,
        "neutral_count": neutral,
        "bad_count": bad,
        "subscores": {
            "mean_quality": round(m, 3),
            "stability": round(stability, 3),
            "execution": round(exec_mean, 3),
            "decision": round(decision_mean, 3),
            "outcome": round(outcome_mean, 3),
            "risk_management": round(risk_mean, 3),
            "event_confidence": round(event_conf_mean, 3),
        },
        "evidence_events": evidence,
        "recommendation_hint": hint,
        "issue_tags": issue_tags,
        "improvement_tags": improvement_tags,
        "confidence_reasons": confidence_reasons,
    }


def grade_game_mechanics(
    timeline: List[Dict[str, Any]],
    player: str,
    player_teams: Dict[str, Any] | None = None,
    replay_meta: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    mechanic_events = _detect_mechanic_events(timeline or [], str(player or ""), player_teams or {}, replay_meta or {})
    gamemode = infer_gamemode((timeline or [{}])[0], player_teams or {}, player) if timeline else "2v2"
    player_team = _player_team(player, player_teams or {})
    grades: List[Dict[str, Any]] = []
    for m in MECHANICS:
        evs = [e for e in mechanic_events if str(e.get("mechanic_id", "")) == m]
        grades.append(_grade_one(m, evs))
    grades.sort(key=lambda x: float(x.get("score_0_100", 50.0)))
    played_grades = [g for g in grades if float(g.get("confidence_0_1", 0.0) or 0.0) >= MIN_REPORTED_MECHANIC_CONFIDENCE]
    overall_source = played_grades if played_grades else grades
    overall = mean([float(g.get("score_0_100", 50.0)) for g in overall_source]) if overall_source else 50.0
    return {
        "grading_version": GRADING_VERSION,
        "context_version": "context_v1_gamemode_support",
        "player": str(player or ""),
        "overall_mechanics_score": round(float(overall), 2),
        "sample_size_meta": {"total_frames": len(timeline or []), "event_count": len(mechanic_events), "gamemode": gamemode},
        "match_context": {
            "gamemode": gamemode,
            "player_team": player_team if player_team in (0, 1) else 0,
        },
        "game_mechanics": grades,
        "mechanic_events": mechanic_events,
    }


def summarize_mechanic_scores(payload: Dict[str, Any]) -> Dict[str, Any]:
    out_scores: Dict[str, float] = {}
    out_conf: Dict[str, float] = {}
    out_tags: Dict[str, List[str]] = {}
    for g in payload.get("game_mechanics", []) or []:
        mid = _canonical_mid(str(g.get("mechanic_id", "")))
        confidence = float(g.get("confidence_0_1", 0.2))
        if confidence < MIN_REPORTED_MECHANIC_CONFIDENCE:
            continue
        out_scores[mid] = float(g.get("score_0_100", 50.0))
        out_conf[mid] = confidence
        tags = [str(tag) for tag in (g.get("issue_tags", []) or []) if str(tag).strip()]
        if tags:
            out_tags[mid] = tags[:6]
    return {
        "overall_mechanics_score": float(payload.get("overall_mechanics_score", 50.0)),
        "mechanic_scores": out_scores,
        "mechanic_confidence": out_conf,
        "mechanic_issue_tags": out_tags,
        "mechanic_grading_version": str(payload.get("grading_version", "legacy")),
    }


def _nearest_frame_idx(timeline: List[Dict[str, Any]], t: float) -> int:
    if not timeline:
        return 0
    best_i = 0
    best_dt = abs(_safe_float(timeline[0].get("t", 0.0)) - float(t))
    for i in range(1, len(timeline)):
        dt = abs(_safe_float(timeline[i].get("t", 0.0)) - float(t))
        if dt < best_dt:
            best_dt = dt
            best_i = i
    return best_i


def explain_mechanic_event(
    timeline: List[Dict[str, Any]],
    player: str,
    player_teams: Dict[str, Any] | None,
    event: Dict[str, Any],
    rank_tier: str = "",
) -> Dict[str, Any]:
    timeline = timeline or []
    if not timeline:
        return {
            "ok": False,
            "error": "empty_timeline",
            "deterministic_summary": "No timeline available for explanation.",
            "thresholds": [],
            "observed": {},
            "breakdown": [],
        }
    mid = _canonical_mid(str(event.get("mechanic_id", "") or ""))
    t = _safe_float(event.get("time", 0.0))
    i = _nearest_frame_idx(timeline, t)
    fr = timeline[i]
    team = _player_team(player, player_teams or {})
    if team not in (0, 1):
        team = 0
    own_goal = _own_goal_y(team)
    opp_goal = _opp_goal_y(team)
    p = _player_frame(fr, player) or {}
    b = fr.get("ball", {}) or {}
    j = _find_next_idx_by_time([_safe_float(x.get("t", 0.0)) for x in timeline], i, 1.0)
    fr2 = timeline[j]

    px = _safe_float(p.get("x", 0.0))
    py = _safe_float(p.get("y", 0.0))
    pz = _safe_float(p.get("z", 0.0))
    bx = _safe_float(b.get("x", 0.0))
    by = _safe_float(b.get("y", 0.0))
    bz = _safe_float(b.get("z", 0.0))
    d_pb = _player_ball_dist(fr, player)
    opp_db = _nearest_opponent_dist_ball(fr, player, player_teams or {}, team)
    p_speed = _player_speed(fr, player)
    b_speed = _ball_speed(fr)
    q = _safe_float(event.get("quality_score", 0.5))
    rank_group = rank_band(rank_tier)
    ctx = dict(event.get("context", {}) or {})
    window = dict(event.get("window", {}) or {})
    issue_tags = [str(tag) for tag in (event.get("issue_tags", []) or []) if str(tag).strip()]
    improvement_tags = [str(tag) for tag in (event.get("improvement_tags", []) or []) if str(tag).strip()]

    thresholds: List[Dict[str, Any]] = []
    observed: Dict[str, Any] = {
        "frame_time_s": round(_safe_float(fr.get("t", t)), 3),
        "player_ball_distance": round(d_pb, 2),
        "nearest_opp_ball_distance": round(opp_db, 2),
        "player_speed": round(p_speed, 2),
        "ball_speed": round(b_speed, 2),
        "player_pos": {"x": round(px, 1), "y": round(py, 1), "z": round(pz, 1)},
        "ball_pos": {"x": round(bx, 1), "y": round(by, 1), "z": round(bz, 1)},
        "gamemode": str(event.get("gamemode", ctx.get("gamemode", "2v2"))),
        "pressure_level": str(event.get("pressure_level", ctx.get("pressure_level", "medium"))),
        "support_available": bool(ctx.get("support_available")),
        "last_man": bool(ctx.get("last_man")),
        "danger_delta": round(_safe_float(window.get("danger_delta", 0.0)), 3),
        "possession_delta": round(_safe_float(window.get("possession_delta", 0.0)), 3),
    }
    breakdown: List[Dict[str, Any]] = []

    def add_thr(name: str, cond: str, val: Any, ok: bool) -> None:
        thresholds.append({"name": name, "condition": cond, "value": val, "met": bool(ok)})

    role = "neutral"
    if mid in {"shadow_defense", "aerial_defense", "challenge"}:
        role = "defense"
    elif mid in {"aerial_offense", "flicking", "carrying_dribbling"}:
        role = "offense"

    pressure_proxy = "high" if (d_pb < 900 and opp_db < 1200) else ("medium" if d_pb < 1700 else "low")
    distance_band = "close" if d_pb < 600 else ("mid" if d_pb < 1800 else "far")
    actionable_hints: List[str] = []

    if mid == "kickoff":
        start_t = _safe_float(event.get("kickoff_window_start", t))
        touch_dt = max(0.0, t - start_t)
        add_thr("kickoff_entry_time", "first touch arrives within kickoff window", round(touch_dt, 3), touch_dt <= KICKOFF_TOUCH_MAX_S)
        add_thr("attempt_requirements", "approach reached contest speed and range before touch", True, True)
        breakdown = [
            {"component": "first_touch_execution", "weight": 0.4},
            {"component": "post_touch_control", "weight": 0.4},
            {"component": "defensive_safety", "weight": 0.2},
        ]
        actionable_hints = [
            "Accelerate into the ball early enough to arrive in your first touch window.",
            "If you cannot win cleanly, angle your touch so the opponent cannot launch an instant counter.",
        ]
    elif mid == "challenge":
        fr_out = fr2
        our_out = _best_team_ball_dist(fr_out, player_teams or {}, team)
        opp_out = _best_team_ball_dist(fr_out, player_teams or {}, 1 - team)
        easy_counter = _ball_toward_own_goal_fast(fr, fr_out, team) and (opp_out + 180.0 < our_out)
        win_poss = our_out + 120.0 < opp_out
        add_thr("contest_proximity", "player and opponent both within challenge range", {"you": round(d_pb, 1), "opp": round(opp_db, 1)}, d_pb <= 900 and opp_db <= 900)
        add_thr("possession_outcome", "team gains first access after challenge", round(opp_out - our_out, 1), win_poss)
        add_thr("counterattack_risk", "no easy counter toward own net", easy_counter, not easy_counter)
        breakdown = [
            {"component": "possession_or_pressure_outcome", "weight": 0.5},
            {"component": "counterattack_safety", "weight": 0.4},
            {"component": "entry_execution", "weight": 0.1},
        ]
        actionable_hints = [
            "Challenge when you can still recover goal-side if the ball slips through.",
            "If you cannot win cleanly, angle contact so opponent loses control instead of breaking out.",
        ]
    elif mid == "fifty_fifty_control":
        our_out = _best_team_ball_dist(fr2, player_teams or {}, team)
        opp_out = _best_team_ball_dist(fr2, player_teams or {}, 1 - team)
        add_thr("simultaneous_contest", "both players in contact range", {"you": round(d_pb, 1), "opp": round(opp_db, 1)}, d_pb < 300 and opp_db < 300)
        add_thr("post_5050_access", "team exits with equal or better access", round(opp_out - our_out, 1), our_out <= opp_out + 80.0)
        breakdown = [
            {"component": "outcome_direction", "weight": 0.4},
            {"component": "followup_access", "weight": 0.35},
            {"component": "contact_quality_proxy", "weight": 0.25},
        ]
        actionable_hints = [
            "Drive through the center of the ball so the outcome stays neutral or favorable.",
            "Plan your landing to reach the next touch before the opponent.",
        ]
    elif mid == "aerial_offense":
        b2 = fr2.get("ball", {}) or {}
        by2 = _safe_float(b2.get("y", 0.0))
        toward_opp = abs(by2 - opp_goal) < abs(by - opp_goal)
        add_thr("airborne_setup", "player and ball are airborne in attack", {"player_z": round(pz, 1), "ball_z": round(bz, 1)}, pz > 150 and bz > 300)
        add_thr("threat_direction", "touch moves ball toward opponent goal", round(abs(by - opp_goal) - abs(by2 - opp_goal), 1), toward_opp)
        breakdown = [
            {"component": "attacking_touch_quality", "weight": 0.45},
            {"component": "followup_possession", "weight": 0.35},
            {"component": "execution_speed", "weight": 0.2},
        ]
        actionable_hints = [
            "Meet the ball earlier in the air so your touch has forward intent, not just contact.",
            "Recover quickly after the hit so your team keeps the next play.",
        ]
    elif mid == "aerial_defense":
        b2 = fr2.get("ball", {}) or {}
        by2 = _safe_float(b2.get("y", 0.0))
        away = abs(by2 - own_goal) > abs(by - own_goal)
        add_thr("defensive_air_context", "airborne defensive contest", {"player_z": round(pz, 1), "ball_z": round(bz, 1)}, pz > 150 and bz > 260)
        add_thr("clear_direction", "touch sends ball away from own net", round(abs(by2 - own_goal) - abs(by - own_goal), 1), away)
        breakdown = [
            {"component": "danger_reduction", "weight": 0.5},
            {"component": "center_lane_avoidance", "weight": 0.3},
            {"component": "recovery_and_spacing", "weight": 0.2},
        ]
        actionable_hints = [
            "Prioritize clears that remove danger first, then look for distance.",
            "Avoid centering the ball after the save; use side lanes when possible.",
        ]
    elif mid == "shadow_defense":
        goal_side = abs(py - own_goal) < abs(by - own_goal)
        add_thr("goal_side", "stay between ball and own net", round(abs(by - own_goal) - abs(py - own_goal), 1), goal_side)
        add_thr("distance_window", "controlled shadow spacing (500-1500)", round(d_pb, 1), 500 <= d_pb <= 1500)
        breakdown = [
            {"component": "goal_side_discipline", "weight": 0.45},
            {"component": "spacing_control", "weight": 0.35},
            {"component": "shot_delay_effect", "weight": 0.2},
        ]
        actionable_hints = [
            "Keep enough spacing to react to flicks without giving a free shot lane.",
            "Match attacker pace and wait for the safe challenge window.",
        ]
    elif mid == "flicking":
        b2 = fr2.get("ball", {}) or {}
        vz_gain = _safe_float(b2.get("vz", 0.0)) - _safe_float(b.get("vz", 0.0))
        fwd_gain = _ball_forward_speed_to_opp(fr2, team) - _ball_forward_speed_to_opp(fr, team)
        add_thr("dribble_control", "ball controlled near car before flick", {"distance": round(d_pb, 1), "ball_z": round(bz, 1)}, d_pb <= 200 and bz < 250)
        add_thr("launch_spike", "upward and forward velocity increase", {"up_gain": round(vz_gain, 1), "forward_gain": round(fwd_gain, 1)}, vz_gain > 200 and fwd_gain > 240)
        breakdown = [
            {"component": "launch_power", "weight": 0.4},
            {"component": "threat_direction", "weight": 0.35},
            {"component": "setup_control", "weight": 0.25},
        ]
        actionable_hints = [
            "Stabilize the dribble first, then flick with a sharper forward release.",
            "Use flick timing when the defender commits so the touch creates immediate threat.",
        ]
    elif mid == "carrying_dribbling":
        add_thr("carry_state", "close, low, controlled carry state", {"distance": round(d_pb, 1), "ball_z": round(bz, 1), "relative_speed": round(_rel_speed_player_ball(fr, player), 1)}, d_pb <= 200 and bz < 250)
        breakdown = [
            {"component": "control_duration", "weight": 0.35},
            {"component": "pressure_retention", "weight": 0.35},
            {"component": "transition_to_threat", "weight": 0.3},
        ]
        actionable_hints = [
            "Keep the ball close enough to react before the first challenge arrives.",
            "Transition carry into a flick, pass, or shot before pressure closes space.",
        ]
    else:
        breakdown = [{"component": "quality_score", "weight": 1.0}]
        actionable_hints = ["Review approach timing and spacing before committing."]

    mechanic_copy = _mechanic_copy(mid)
    summary = (
        f"{MECH_TITLE.get(mid, mid)} scored {round(q * 100.0, 1)}/100 "
        f"({str(event.get('quality_label', 'neutral'))}). "
        f"{sum(1 for x in thresholds if x.get('met'))}/{len(thresholds)} trigger checks matched."
    )
    title_prefix = "Strong" if q >= 0.7 else ("Mixed" if q >= 0.45 else "Needs Work")
    title = f"{title_prefix} {MECH_TITLE.get(mid, mid)}"
    template_body = _coach_sentence_bank(mid, q, event, observed, issue_tags, improvement_tags)
    confidence_note = "Confidence is higher when outcome and safety checks point in the same direction."
    return {
        "ok": True,
        "mechanic_id": mid,
        "title": MECH_TITLE.get(mid, mid),
        "short": str(event.get("short", MECH_SHORT.get(mid, "MECH"))),
        "event_time_s": round(t, 3),
        "quality_score_0_1": round(q, 4),
        "quality_score_0_100": round(q * 100.0, 2),
        "quality_label": str(event.get("quality_label", "neutral")),
        "reason": str(event.get("reason", "")),
        "event_type": str(event.get("event_type", "")),
        "thresholds": thresholds,
        "observed": observed,
        "breakdown": breakdown,
        "coaching_context": {
            "role": role,
            "pressure_proxy": pressure_proxy,
            "distance_band": distance_band,
            "rank_band": rank_group,
        },
        "mechanic_description": str(mechanic_copy.get("description", "")),
        "why_it_matters": str(mechanic_copy.get("why_it_matters", "")),
        "common_mistake": str(mechanic_copy.get("common_mistake", "")),
        "training_cue": str(mechanic_copy.get("training_cue", "")),
        "actionable_hints": actionable_hints[:2],
        "mechanic_tags": [str(tag) for tag in (event.get("mechanic_tags", []) or []) if str(tag).strip()][:6],
        "mechanic_tag_labels": [str(tag) for tag in (event.get("mechanic_tag_labels", []) or []) if str(tag).strip()][:6],
        "issue_tags": issue_tags[:6],
        "improvement_tags": improvement_tags[:6],
        "template_title": title,
        "template_body": template_body,
        "event_confidence_0_1": round(_safe_float(event.get("event_confidence_0_1", 0.65), 0.65), 3),
        "confidence_note": confidence_note,
        "deterministic_summary": summary,
    }
