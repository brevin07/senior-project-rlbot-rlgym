import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../app/AuthContext";

const rankGroups = [
  { label: "Bronze", values: ["bronze_1", "bronze_2", "bronze_3"] },
  { label: "Silver", values: ["silver_1", "silver_2", "silver_3"] },
  { label: "Gold", values: ["gold_1", "gold_2", "gold_3"] },
  { label: "Platinum", values: ["platinum_1", "platinum_2", "platinum_3"] },
  { label: "Diamond", values: ["diamond_1", "diamond_2", "diamond_3"] },
  { label: "Champion", values: ["champion_1", "champion_2", "champion_3"] },
  { label: "Grand Champion", values: ["grand_champion_1", "grand_champion_2", "grand_champion_3"] },
  { label: "Supersonic Legend", values: ["ssl"] },
];

function rankLabel(v: string) {
  return v.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

export default function ProfileSetupPage() {
  const { profile, setupProfile } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState(profile?.username ?? "");
  const [rank, setRank] = useState(profile?.rank_tier ?? "diamond_1");
  const [platform, setPlatform] = useState(profile?.platform ?? "epic");
  const [aliases, setAliases] = useState((profile?.aliases ?? []).join(", "));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const aliasList = useMemo(
    () => aliases.split(",").map((x) => x.trim()).filter(Boolean),
    [aliases]
  );

  const submit = async () => {
    setError("");
    setBusy(true);
    try {
      await setupProfile({
        username,
        rank_tier: rank,
        platform,
        aliases: aliasList
      });
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="profile profile--setup">
      <div className="profile__panel profile__panel--setup">
        <h1>Set Up Your Profile</h1>
        <p>Enter the in-game account shown in your replays so RocketCoach can match analysis to your player.</p>
        <div className="profile__form">
          <label>
            In-game username
            <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Your main username" />
          </label>
          <label>
            Rank tier
            <div className="rank-selector">
              {rankGroups.map((g) => (
                <div key={g.label} className="rank-group">
                  <div className="rank-group-label">{g.label}</div>
                  <div className="rank-options">
                    {g.values.map((r) => (
                      <button
                        key={r}
                        type="button"
                        className={`rank-option ${rank === r ? "selected" : ""}`}
                        onClick={() => setRank(r)}
                      >
                        {r.split("_")[1] ? r.split("_")[1].toUpperCase() : "SSL"}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </label>
          <label>
            Platform
            <select value={platform} onChange={(e) => setPlatform(e.target.value)}>
              <option value="epic">Epic</option>
              <option value="steam">Steam</option>
            </select>
          </label>
          <label>
            Alternate usernames (comma-separated)
            <input value={aliases} onChange={(e) => setAliases(e.target.value)} placeholder="alts, smurfs" />
          </label>
          {error && <div className="alert">{error}</div>}
          <button disabled={busy} onClick={submit}>{busy ? "Saving..." : "Continue to Dashboard"}</button>
        </div>
      </div>
    </div>
  );
}
