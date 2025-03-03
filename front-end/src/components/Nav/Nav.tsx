import React from 'react';
import { useLocalStorage } from '../../localstorage';

export const Nav: React.FC = () => {
  const [token, setToken] = useLocalStorage('token','')
  return(
    <div>
      {token.email}
    </div>
  )
}
