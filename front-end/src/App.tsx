import './App.css'
import {ModuleStudentDashboard}  from './components/StudentDashboard'
import { Nav } from './components/Nav/Nav'
import { googleContext } from './auth';
import { useContext } from 'react';

export default function App() {
  //Handle Scuccesful AUthentication and get token
  const token = useContext(googleContext);

  return (
    //Create Google Login Button
    <>
      <ModuleStudentDashboard token={token}/>
    </>
  )
}