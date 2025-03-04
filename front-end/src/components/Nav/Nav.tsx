import React, { useContext } from 'react';
import { googleContext } from '../../auth';


export const Nav = () => {
  let { token } = useContext(googleContext) || { token: { email: "not logged in" } };
  return(
    <div>
      {token.email}
    </div>
  )
}
