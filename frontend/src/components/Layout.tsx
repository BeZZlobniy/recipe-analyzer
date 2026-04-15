import { Link, NavLink } from "react-router-dom";
import { useAuth } from "../features/auth/AuthContext";

export function Layout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link to="/" className="brand">
          Анализатор Рецептов
        </Link>
        <nav className="nav">
          <NavLink to="/">Дашборд</NavLink>
          <NavLink to="/profiles">Профили</NavLink>
          <NavLink to="/analysis/new">Новый анализ</NavLink>
          <NavLink to="/history">История</NavLink>
        </nav>
        <div className="sidebarFooter">
          <div className="muted">Пользователь: {user?.username}</div>
          <button className="ghostButton" onClick={() => void logout()}>
            Выйти
          </button>
        </div>
      </aside>
      <main className="content">{children}</main>
    </div>
  );
}
