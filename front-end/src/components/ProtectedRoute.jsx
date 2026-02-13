import { Navigate, useLocation } from "react-router-dom";
import { isAuthenticated } from "../auth";

export default function ProtectedRoute({ children }) {
    const location = useLocation();

    if (!isAuthenticated()) {
        const next = encodeURIComponent(`${location.pathname}${location.search}`);
        return <Navigate to={`/login?next=${next}`} replace />;
    }

    return children;
}
