import './App.css'
import { useContext } from 'react';
import {BrowserRouter as Router, Routes, Route} from 'react-router-dom'
import { googleContext } from './auth';
import { Nav } from './components/Nav/Nav';
import Home from './components/Home/Home';
import Student from './components/Student/Student';

export default function App() {
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