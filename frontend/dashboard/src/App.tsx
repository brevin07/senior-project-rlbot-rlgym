import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./app/AuthContext";
import LoginPage from "./pages/LoginPage";
import ProfileSetupPage from "./pages/ProfileSetupPage";
import DashboardPage from "./pages/DashboardPage";
import AccountPage from "./pages/AccountPage";

function RequireAuth({ children }: { children: JSX.Element }) {
  const { auth, loading } = useAuth();
  if (loading) {
    return <div className="loading-screen">Loading...</div>;
  }
  if (!auth) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

function RequireProfile({ children }: { children: JSX.Element }) {
  const { profile, loading } = useAuth();
  if (loading) {
    return <div className="loading-screen">Loading...</div>;
  }
  if (!profile || !profile.username) {
    return <Navigate to="/profile" replace />;
  }
  return children;
}

export default function App() {
  return (
    <div className="app app--hud">
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/profile"
          element={
            <RequireAuth>
              <ProfileSetupPage />
            </RequireAuth>
          }
        />
        <Route
          path="/dashboard"
          element={
            <RequireAuth>
              <RequireProfile>
                <DashboardPage />
              </RequireProfile>
            </RequireAuth>
          }
        />
        <Route
          path="/account"
          element={
            <RequireAuth>
              <RequireProfile>
                <AccountPage />
              </RequireProfile>
            </RequireAuth>
          }
        />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </div>
  );
}
