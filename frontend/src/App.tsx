import { Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AnalysisDetailsPage } from "./pages/AnalysisDetailsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { HistoryPage } from "./pages/HistoryPage";
import { LoginPage } from "./pages/LoginPage";
import { NewAnalysisPage } from "./pages/NewAnalysisPage";
import { ProfilesPage } from "./pages/ProfilesPage";

function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <ProtectedRoute>
      <Layout>{children}</Layout>
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<AppShell><DashboardPage /></AppShell>} />
        <Route path="/profiles" element={<AppShell><ProfilesPage /></AppShell>} />
        <Route path="/analysis/new" element={<AppShell><NewAnalysisPage /></AppShell>} />
        <Route path="/history" element={<AppShell><HistoryPage /></AppShell>} />
        <Route path="/history/:analysisId" element={<AppShell><AnalysisDetailsPage /></AppShell>} />
      </Routes>
    </AuthProvider>
  );
}
