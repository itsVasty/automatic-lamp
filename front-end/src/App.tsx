import './App.css'
import {ModuleStudentDashboard}  from './components/StudentDashboard'
import { GoogleLogin } from "@react-oauth/google"
import {jwtDecode} from "jwt-decode"
import { useLocalStorage } from './localstorage'

export default function App() {
  const [token, setToken] = useLocalStorage('token', '')
  //Handle Scuccesful AUthentication and get token
  const handleSuccess = (CredentialResponse: any) => {
    const token = CredentialResponse.credential
    setToken(jwtDecode(token))
    console.log(`user info: ${token}`)
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