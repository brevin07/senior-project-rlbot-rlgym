import { useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../app/AuthContext";
import { rankOptions, rankTierLabel } from "../app/profileOptions";

export default function AccountPage() {
  const { auth, profile, updateProfile, logout, deleteAccount, devBypassAuth } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState(profile?.username ?? "");
  const [rank, setRank] = useState(profile?.rank_tier ?? "diamond_1");
  const [platform, setPlatform] = useState(profile?.platform ?? "epic");
  const [aliases, setAliases] = useState((profile?.aliases ?? []).join(", "));
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const aliasList = useMemo(
    () => aliases.split(",").map((x) => x.trim()).filter(Boolean),
    [aliases]
  );

  const submit = async () => {
    setError("");
    setSaving(true);
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
      setSaving(false);
    }
  };

  const doLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  const doDeleteAccount = async () => {
    setError("");
    if (deleteConfirm.trim().toLowerCase() !== String(auth?.email || "").trim().toLowerCase()) {
      setError("Type your account email to confirm deletion.");
      return;
    }
    setDeleting(true);
    try {
      await deleteAccount();
      setDeleteConfirm("");
      navigate("/login", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="profile">
      <div className="profile__panel">
        <div className="account-header">
          <Link className="back-link" to={(location.state as { from?: string } | null)?.from || "/dashboard"}>←</Link>
          <h1>Account</h1>
        </div>
        <p>Update your player profile and aliases.</p>
        <div className="profile__form">
          <label>
            In-game username
            <input value={username} onChange={(e) => setUsername(e.target.value)} />
          </label>
          <label>
            Rank tier
            <select value={rank} onChange={(e) => setRank(e.target.value)}>
              {rankOptions.map((r) => (
                <option key={r} value={r}>{rankTierLabel(r)}</option>
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
            <button disabled={saving} onClick={submit}>{saving ? "Saving..." : "Save Changes"}</button>
            <button className="ghost" onClick={doLogout}>Log out</button>
          </div>
          {auth?.email && !devBypassAuth ? (
            <div className="improvement-card" style={{ marginTop: 24, borderColor: "rgba(214, 84, 84, 0.35)" }}>
              <strong style={{ fontSize: 15 }}>Delete Account</strong>
              <p className="library-item-meta" style={{ marginTop: 8 }}>
                This permanently removes your replay history, recommendations, profile data, and account access.
              </p>
              <label>
                Type your email to confirm
                <input
                  value={deleteConfirm}
                  onChange={(e) => setDeleteConfirm(e.target.value)}
                  placeholder={auth.email}
                />
              </label>
              <div className="profile__actions">
                <button disabled={saving || deleting} onClick={doDeleteAccount}>
                  {deleting ? "Deleting..." : "Delete Account"}
                </button>
              </div>
            </div>
          ) : (
            <div className="improvement-card" style={{ marginTop: 24, borderColor: "rgba(214, 84, 84, 0.2)", opacity: 0.85 }}>
              <strong style={{ fontSize: 15 }}>Delete Account</strong>
              <p className="library-item-meta" style={{ marginTop: 8 }}>
                Account deletion is unavailable in dev no-login mode because there is no Cognito-backed user to remove.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
