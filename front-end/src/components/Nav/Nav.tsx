import React from 'react';


export const Nav: React.FC<{token : any}> = ({token} : any) => {
  return(
    <div>
      {token.email}
    </div>
  )
}
