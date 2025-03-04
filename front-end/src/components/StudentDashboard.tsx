import { useContext } from 'react';
import {Nav} from './Nav/Nav';
import {Schedule} from './Schedule/Schedule';
import {Activity} from './Activity/Activity';
import {Skills} from './Skills/Skills';
import { googleContext } from '../auth';


export const ModuleStudentDashboard = () => {
  let { signOut } : any = useContext(googleContext) || { signOut: () => {} };
  
  return(
    <>
      <div>
        <Nav />
      </div>
      <div>
        <div>
          <Activity/>
          <Skills/>
        </div>
        <div>
          <Schedule/>
        </div>
      </div>
      <button onClick={() => {
        signOut()
      }}>Logout</button>
    </>
  )
}