import './App.css'
import {BrowserRouter as Router, Routes, Route} from 'react-router-dom'
import Home from './components/Home/Home';
import Student from './components/Student/Student';
import Sidebar from './components/Sidebar/Sidebar';

export default function App() {  
  return(
    <>
      <Router>
        <div className='app'>
          <Sidebar/>
          <main className='main-content'>
            <Routes>
              <Route path='/' Component={Home}/>
              <Route path='/student' Component={Student}/>
            </Routes>
          </main>
        </div>
      </Router>
    </>
  )
}