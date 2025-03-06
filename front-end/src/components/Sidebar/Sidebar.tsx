import { useContext } from 'react';
import { NavLink } from 'react-router-dom';
import { googleContext } from '../../auth';
import './sidebar.css';

import { 
  MdHome,
  // MdBook,
  // MdCalendarMonth,
  // MdEmojiEvents,
  // MdNotifications,
  MdSettings,
  MdLogout
} from 'react-icons/md';

const Sidebar = () => {
  let { signOut } : any = useContext(googleContext) || { signOut: () => {} };
  let { token } :any = useContext(googleContext) || { token: { email: "not logged in" } };

  return (
    <aside className='Sidebar'>
      <div className="logo">
        {token.given_name[0]}{token.family_name[0]}
      </div>
      <nav>
        <NavLink to="/" className="nav-button">
          <MdHome />
        </NavLink>
        <NavLink to="/student" className="nav-button">
          <MdSettings />
        </NavLink>
        <button onClick={() => signOut()} className="nav-button">
          <MdLogout />
        </button>
      </nav>
    </aside>
  );
}

export default Sidebar;