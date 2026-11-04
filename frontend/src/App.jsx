import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./layouts/AppLayout";
import { auth } from "./services/api";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Monitoring from "./pages/Monitoring";
import CarbonAnalytics from "./pages/CarbonAnalytics";
import Predictions from "./pages/Predictions";
import Optimization from "./pages/Optimization";
import CostAnalysis from "./pages/CostAnalysis";
import ExplainableAI from "./pages/ExplainableAI";
import Simulator from "./pages/Simulator";
import Anomalies from "./pages/Anomalies";
import Reports from "./pages/Reports";
import Settings from "./pages/Settings";

const Protected = ({ children }) => (auth.isLoggedIn() ? children : <Navigate to="/login" replace />);

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Protected><AppLayout /></Protected>}>
        <Route index element={<Dashboard />} />
        <Route path="monitoring" element={<Monitoring />} />
        <Route path="carbon" element={<CarbonAnalytics />} />
        <Route path="predictions" element={<Predictions />} />
        <Route path="optimization" element={<Optimization />} />
        <Route path="cost" element={<CostAnalysis />} />
        <Route path="explain" element={<ExplainableAI />} />
        <Route path="simulator" element={<Simulator />} />
        <Route path="anomalies" element={<Anomalies />} />
        <Route path="reports" element={<Reports />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
