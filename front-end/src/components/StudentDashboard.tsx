import { useContext } from 'react';
import {Nav} from './Nav/Nav';
import { googleContext } from '../auth';
import {BrowserRouter as Router, Routes, Route} from 'react-router-dom'
import Home from './Home/Home';
import Student from './Student/Student';


export const ModuleStudentDashboard = () => {
  let { signOut } : any = useContext(googleContext) || { signOut: () => {} };
  
  return(
    <>
      <Router>
        <Nav/>
        <Routes>
          <Route path='/' Component={Home}/>
          <Route path='/student' Component={Student}/>
        </Routes>
        <button onClick={() => {
          signOut()
        }}>Logout</button>
      </Router>
    </>
  )
}