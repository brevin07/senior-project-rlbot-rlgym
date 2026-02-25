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

export default function AccountPage() {
  const { profile, updateProfile, logout } = useAuth();
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
      await updateProfile({
        username,
        rank_tier: rank,
        platform,
        aliases: aliasList
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const doLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="profile">
      <div className="profile__panel">
        <h1>Account</h1>
        <p>Update your player profile and aliases.</p>
        <div className="profile__form">
          <label>
            In-game username
            <input value={username} onChange={(e) => setUsername(e.target.value)} />
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
            <input value={aliases} onChange={(e) => setAliases(e.target.value)} />
          </label>
          {error && <div className="alert">{error}</div>}
          <div className="profile__actions">
            <button disabled={busy} onClick={submit}>{busy ? "Saving..." : "Save Changes"}</button>
            <button className="ghost" onClick={doLogout}>Log out</button>
          </div>
        </div>
      </div>
    </div>
  );
}
