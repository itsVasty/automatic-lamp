import './App.css'
import {ModuleStudentDashboard}  from './components/StudentDashboard'
import { GoogleLogin } from "@react-oauth/google"
import {jwtDecode} from "jwt-decode"

export default function App() {
  //Handle Scuccesful AUthentication and get token
  const handleSuccess = (CredentialResponse: any) => {
    const token = CredentialResponse.credential
    const user = jwtDecode(token)
    console.log(`user info: ${user}`)
  }

  const handleFailure = () => {
    console.log(`Signin Failed`)
  }

  return (
    //Create Google Login Button
    <>
      <ModuleStudentDashboard/>
      <GoogleLogin onSuccess={handleSuccess} onError={handleFailure}/> 
    </>
  )
}