import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./hooks/useAuth";
import { useEventStream } from "./hooks/useEventStream";
import { AppShell } from "./layout/AppShell";
import { ActivityPage } from "./pages/Activity";
import { Dashboard } from "./pages/Dashboard";
import { LibraryPage } from "./pages/Library";
import { Login } from "./pages/Login";
import { OriginsPage } from "./pages/Origins";
import { ReviewPage } from "./pages/Review";
import { SettingsPage } from "./pages/Settings";
import { Spinner } from "./components/ui";

export default function App() {
  const { status, loading } = useAuth();
  useEventStream(Boolean(status?.authenticated));

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  if (!status?.authenticated) {
    return <Login />;
  }

  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/review" element={<ReviewPage />} />
        <Route path="/review/:jobId" element={<ReviewPage />} />
        <Route path="/library" element={<LibraryPage />} />
        <Route path="/library/:albumId" element={<LibraryPage />} />
        <Route path="/origins" element={<OriginsPage />} />
        <Route path="/activity" element={<ActivityPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
