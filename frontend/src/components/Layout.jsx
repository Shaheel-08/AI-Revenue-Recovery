import { NavLink } from 'react-router-dom';
import '../styles/layout.css';

const NAV_ITEMS = [
  { to: '/', icon: '📊', label: 'Dashboard' },
  { to: '/transactions', icon: '💳', label: 'Transactions' },
  { to: '/approvals', icon: '✅', label: 'Approvals' },
  { to: '/evaluate', icon: '⚡', label: 'Evaluate' },
  { to: '/settings', icon: '⚙️', label: 'Settings' },
];

export default function Layout({ children }) {
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <h1>RecoverOS</h1>
          <div className="subtitle">AI Revenue Recovery</div>
        </div>

        <nav className="sidebar-nav">
          {NAV_ITEMS.map(({ to, icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              <span className="nav-icon">{icon}</span>
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="status">
            <span className="status-dot pulse" />
            System Operational
          </div>
        </div>
      </aside>

      <main className="main-content">
        {children}
      </main>
    </div>
  );
}
