import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../app/AuthContext";
import { platformOptions, rankGroups, rankTierDivisionLabel, rankTierLabel } from "../app/profileOptions";

type SetupStep = "welcome" | "username" | "rank" | "platform" | "aliases";

const setupSteps: { id: SetupStep; label: string; eyebrow: string }[] = [
  { id: "welcome", label: "Welcome", eyebrow: "Kickoff" },
  { id: "username", label: "Main Username", eyebrow: "Match Player" },
  { id: "rank", label: "Rank", eyebrow: "MMR Range" },
  { id: "platform", label: "Platform", eyebrow: "Replay Path" },
  { id: "aliases", label: "Alt Usernames", eyebrow: "Replay Matching" },
];

function dedupeAliases(values: string[], username: string) {
  const seen = new Set<string>();
  const normalizedUsername = String(username || "").trim().toLowerCase();
  const out: string[] = [];
  for (const value of values) {
    const clean = String(value || "").trim();
    const key = clean.toLowerCase();
    if (!clean || key === normalizedUsername || seen.has(key)) continue;
    seen.add(key);
    out.push(clean);
  }
  return out;
}

export default function ProfileSetupPage() {
  const { profile, setupProfile } = useAuth();
  const navigate = useNavigate();
  const [stepIdx, setStepIdx] = useState(0);
  const [username, setUsername] = useState(profile?.username ?? "");
  const [rank, setRank] = useState(profile?.rank_tier ?? "diamond_1");
  const [platform, setPlatform] = useState(profile?.platform ?? "epic");
  const [aliases, setAliases] = useState((profile?.aliases ?? []).join(", "));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const step = setupSteps[stepIdx];
  const aliasList = useMemo(
    () => dedupeAliases(aliases.split(",").map((x) => x.trim()).filter(Boolean), username),
    [aliases, username]
  );
  const canAdvance =
    step.id === "welcome" ||
    step.id === "rank" ||
    step.id === "platform" ||
    (step.id === "username" && Boolean(username.trim())) ||
    step.id === "aliases";

  const goNext = async () => {
    if (busy) return;
    if (step.id === "username" && !username.trim()) {
      setError("Enter the main username that appears in your Rocket League replays.");
      return;
    }
    if (stepIdx < setupSteps.length - 1) {
      setError("");
      setStepIdx((idx) => Math.min(setupSteps.length - 1, idx + 1));
      return;
    }
    setError("");
    setBusy(true);
    try {
      await setupProfile({
        username: username.trim(),
        rank_tier: rank,
        platform,
        aliases: aliasList,
      });
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const goBack = () => {
    if (busy || stepIdx === 0) return;
    setError("");
    setStepIdx((idx) => Math.max(0, idx - 1));
  };

  return (
    <div className="profile profile--setup">
      <div className="profile__panel profile__panel--setup profile__panel--wizard">
        <div className="setup-shell">
          <div className="setup-stage">
            <div className="setup-stage-sky" />
            <div className="setup-stage-boost setup-stage-boost--left" />
            <div className="setup-stage-boost setup-stage-boost--right" />
            <div className="setup-stage-field">
              <div className="setup-stage-center-line" />
              <div className="setup-stage-center-circle" />
              <div className="setup-stage-ball"><i className="fa-solid fa-futbol" /></div>
              <div className="setup-stage-car setup-stage-car--blue"><i className="fa-solid fa-car-side" /></div>
              <div className="setup-stage-car setup-stage-car--orange"><i className="fa-solid fa-car-side" /></div>
            </div>
          </div>

          <div className="setup-progress">
            {setupSteps.map((item, idx) => (
              <div
                key={item.id}
                className={`setup-progress-step${idx === stepIdx ? " is-active" : ""}${idx < stepIdx ? " is-complete" : ""}`}
              >
                <span>{idx + 1}</span>
                <small>{item.label}</small>
              </div>
            ))}
          </div>

          <div className="setup-copy">
            <div className="setup-copy-eyebrow">{step.eyebrow}</div>
            <h1>{step.id === "welcome" ? "Welcome to RocketCoach" : step.label}</h1>
            {step.id === "welcome" && (
              <p>
                Let&apos;s get your profile dialed in so replay matching, mechanic grading, and training recommendations
                actually point at the right player.
              </p>
            )}
            {step.id === "username" && (
              <p>
                Start with the main in-game name that shows up in your Rocket League replays. This is the anchor for the
                rest of the analysis.
              </p>
            )}
            {step.id === "rank" && (
              <p>
                Pick the rank that best matches where you&apos;re playing right now. We use it to tune expectations and
                training difficulty.
              </p>
            )}
            {step.id === "platform" && (
              <p>
                This helps RocketCoach point new users toward the right replay folder and keep the upload flow less
                annoying.
              </p>
            )}
            {step.id === "aliases" && (
              <p>
                Add any other names you&apos;ve used in replays. This step is optional, but it saves a lot of missed
                player matches later.
              </p>
            )}
          </div>

          <div className="profile__form setup-wizard-form">
            {step.id === "welcome" && (
              <div className="setup-highlight-list">
                <div className="setup-highlight-item">
                  <i className="fa-solid fa-film" />
                  <span>Replay analysis locks onto the right player</span>
                </div>
                <div className="setup-highlight-item">
                  <i className="fa-solid fa-gauge-high" />
                  <span>Mechanic grades line up with your actual skill bracket</span>
                </div>
                <div className="setup-highlight-item">
                  <i className="fa-solid fa-dumbbell" />
                  <span>Training recommendations start in the right lane</span>
                </div>
              </div>
            )}

            {step.id === "username" && (
              <label>
                Main in-game username
                <input
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="hxzywassaved"
                  autoFocus
                />
              </label>
            )}

            {step.id === "rank" && (
              <label>
                Current rank
                <div className="rank-selector">
                  {rankGroups.map((group) => (
                    <div key={group.label} className="rank-group">
                      <div className="rank-group-label">{group.label}</div>
                      <div className="rank-options">
                        {group.values.map((tier) => (
                          <button
                            key={tier}
                            type="button"
                            className={`rank-option ${rank === tier ? "selected" : ""}`}
                            onClick={() => setRank(tier)}
                            title={rankTierLabel(tier)}
                          >
                            {rankTierDivisionLabel(tier)}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </label>
            )}

            {step.id === "platform" && (
              <div className="setup-platform-grid">
                {platformOptions.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    className={`setup-platform-card${platform === option.value ? " is-selected" : ""}`}
                    onClick={() => setPlatform(option.value)}
                  >
                    <div className="setup-platform-icon"><i className={`fa-solid ${option.icon}`} /></div>
                    <strong>{option.label}</strong>
                    <span>{option.hint}</span>
                  </button>
                ))}
              </div>
            )}

            {step.id === "aliases" && (
              <>
                <label>
                  Alternate usernames
                  <input
                    value={aliases}
                    onChange={(e) => setAliases(e.target.value)}
                    placeholder="Jones.RL, old alt, tournament account"
                  />
                </label>
                <div className="setup-alias-note">
                  Optional but recommended. Separate each name with a comma.
                </div>
                {!!aliasList.length && (
                  <div className="setup-alias-pills">
                    {aliasList.map((alias) => (
                      <span key={alias} className="setup-alias-pill">{alias}</span>
                    ))}
                  </div>
                )}
              </>
            )}

            {error && <div className="alert">{error}</div>}

            <div className="setup-footer">
              <button type="button" className="ghost" onClick={goBack} disabled={stepIdx === 0 || busy}>
                Back
              </button>
              <button type="button" onClick={() => void goNext()} disabled={!canAdvance || busy}>
                {busy ? "Saving..." : stepIdx === setupSteps.length - 1 ? "Start Coaching" : "Next"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
