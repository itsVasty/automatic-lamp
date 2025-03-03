import React from 'react';
import {Nav} from './Nav/Nav';
import {Schedule} from './Schedule/Schedule';
import {Activity} from './Activity/Activity';
import {Skills} from './Skills/Skills';


export const ModuleStudentDashboard: React.FC<{token : any}> = ({token}) => {
  
  return(
    <>
      <div>
        <Nav token={token}/>
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
      <button onClick={() => {localStorage.removeItem('token')}}>Logout</button>
    </>
  )
}