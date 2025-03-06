import React, { useContext } from 'react';
import { googleContext } from '../../auth';
import { NavLink } from 'react-router';
import styles from './Nav.module.css';


export const Nav = () => {
  let { token } :any = useContext(googleContext) || { token: { email: "not logged in" } };
  return(
    <div className={styles.Nav}>
      <nav>
        <NavLink to='/'>Home</NavLink>
        <NavLink to='/student'>{token.email}</NavLink>
      </nav>
    </div>
  )
}
