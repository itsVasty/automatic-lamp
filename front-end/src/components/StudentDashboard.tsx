import React from 'react';
import {Nav} from './Nav/Nav';
import {Schedule} from './Schedule/Schedule';
import {Activity} from './Activity/Activity';
import {Skills} from './Skills/Skills';


export const ModuleStudentDashboard: React.FC = () => {
  return(
    <>
      <div>
        <Nav/>
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
    </>
  )
}