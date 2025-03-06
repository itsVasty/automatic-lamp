import { useContext } from 'react';
import { googleContext } from '../../auth';

const Student = () => {
  let { token } :any = useContext(googleContext) || { token: { email: "not logged in" } };
  return(
    <>
      <h1>Student Page</h1>
      {token.email}
    </>
  )
}

export default Student;
