import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../app/AuthContext";

const ranks = [
  "bronze_1","bronze_2","bronze_3",
  "silver_1","silver_2","silver_3",
  "gold_1","gold_2","gold_3",
  "platinum_1","platinum_2","platinum_3",
  "diamond_1","diamond_2","diamond_3",
  "champion_1","champion_2","champion_3",
  "grand_champion_1","grand_champion_2","grand_champion_3",
  "ssl"
];

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
    <div className="profile">
      <div className="profile__panel">
        <h1>Player Profile</h1>
        <p>Tell us who you are in Rocket League so we can match your replays and stats.</p>
        <div className="profile__form">
          <label>
            In-game username
            <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Your main username" />
          </label>
          <label>
            Rank tier
            <select value={rank} onChange={(e) => setRank(e.target.value)}>
              {ranks.map((r) => (
                <option key={r} value={r}>{r.replace(/_/g, " ")}</option>
              ))}
            </select>
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
